import argparse
import csv
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gt7_scraper import db as db_utils
from gt7_scraper.scraper import (
    BASE_URL,
    build_session,
    extract_site_total_count,
    fetch_text,
    resolve_locales,
    run_scraper,
)

DEFAULT_LOCALES = [
    "gb",
    "us",
    "cn",
    "tw",
    "jp",
    "kr",
    "de",
    "fr",
    "it",
    "nl",
    "es",
    "mx",
    "pt",
    "br",
    "pl",
    "ru",
    "cz",
    "tr",
    "gr",
    "sa",
    "th",
]
DEFAULT_HERO_MANIFEST = "./gt7_scraper/mappings/hero_expected_counts.json"


def get_site_total(locale: str, timeout: int) -> Optional[int]:
    session = build_session()
    path_locale, _ = resolve_locales(locale)
    html = fetch_text(session, f"{BASE_URL}/{path_locale}/gt7/carlist/", timeout)
    return extract_site_total_count(html)


def resolve_base_locale(locales: List[str], requested: str) -> str:
    if requested:
        return requested
    if len(locales) == 1:
        return locales[0]
    if "gb" in locales:
        return "gb"
    return locales[0]


def normalize_locale_order(locales: List[str], base_locale: str) -> List[str]:
    ordered: List[str] = []
    seen = set()
    if base_locale:
        ordered.append(base_locale)
        seen.add(base_locale)
    for item in locales:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def resolve_playwright_policy(
    engine: str,
    use_playwright_flag: bool,
    requested_policy: Optional[str],
    requested_engine: str,
) -> tuple[bool, str]:
    if requested_policy:
        policy = requested_policy
    elif use_playwright_flag:
        policy = "node" if engine == "hybrid" else "python"
    else:
        policy = "off"
    use_playwright = policy != "off"
    playwright_engine = requested_engine or ("node" if engine == "hybrid" else "python")
    if policy in {"node", "python"}:
        playwright_engine = policy
    return use_playwright, playwright_engine


def resolve_image_policy(
    requested_policy: str,
    images_all_flag: bool,
    skip_images_flag: bool,
) -> str:
    if skip_images_flag:
        return "none"
    if images_all_flag:
        return "all-locales"
    return requested_policy


def should_download_for_template(image_policy: str) -> bool:
    return image_policy in {"base-only", "all-locales"}


def should_download_for_overlay(image_policy: str) -> bool:
    return image_policy == "all-locales"


def should_download_for_combined(image_policy: str, locale: str, base_locale: str) -> bool:
    if image_policy == "none":
        return False
    if image_policy == "all-locales":
        return True
    return locale == base_locale


def count_list_total(path: str) -> Optional[int]:
    if not path:
        return None
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return len(
                [line for line in (item.strip() for item in f) if line and not line.startswith("#")]
            )
    except Exception:
        return None


def prune_texts_for_locale(db_path: Path, locale: str) -> None:
    conn = db_utils.connect_db(db_path)
    try:
        db_utils.prune_car_texts_except_locale(conn, locale)
    finally:
        conn.close()


def checkpoint_template_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.commit()
    finally:
        conn.close()


def load_hero_expected_counts(manifest_path: Path) -> Dict[str, int]:
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    source: Dict[str, object]
    if isinstance(payload, dict) and isinstance(payload.get("counts"), dict):
        source = payload["counts"]
    elif isinstance(payload, dict):
        source = payload
    else:
        return {}
    out: Dict[str, int] = {}
    for car_id, value in source.items():
        try:
            out[str(car_id)] = int(value)
        except Exception:
            continue
    return out


def collect_db_hero_counts(db_path: Path) -> tuple[List[str], Dict[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        car_ids = [row[0] for row in cur.execute("SELECT id FROM cars")]
        table_exists = (
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1"
            ).fetchone()
            is not None
        )
        if not table_exists:
            return car_ids, {}
        hero_map: Dict[str, int] = {}
        for car_id, count in cur.execute(
            "SELECT car_id, COUNT(*) FROM car_images WHERE image_type='hero' GROUP BY car_id"
        ):
            hero_map[str(car_id)] = int(count)
        return car_ids, hero_map
    finally:
        conn.close()


def validate_hero_counts(
    db_path: Path,
    reference_counts: Dict[str, int],
    hero_min: int,
) -> tuple[int, List[Dict[str, object]]]:
    car_ids, hero_counts = collect_db_hero_counts(db_path)
    diffs: List[Dict[str, object]] = []
    for car_id in car_ids:
        actual = hero_counts.get(car_id, 0)
        expected = reference_counts.get(car_id)
        if expected is not None:
            if actual != expected:
                diffs.append(
                    {
                        "db": db_path.name,
                        "car_id": car_id,
                        "expected": expected,
                        "actual": actual,
                        "reason": "mismatch_with_reference",
                    }
                )
            continue
        if actual < hero_min:
            diffs.append(
                {
                    "db": db_path.name,
                    "car_id": car_id,
                    "expected": f">={hero_min}",
                    "actual": actual,
                    "reason": "below_min_without_reference",
                }
            )
    return len(car_ids), diffs


def evaluate_hero_check_outcome(
    mode: str,
    checked_rows: int,
    mismatch_rows: int,
    soft_max_ratio: float,
    soft_max_count: int,
) -> tuple[bool, str, float]:
    ratio = (float(mismatch_rows) / float(checked_rows)) if checked_rows > 0 else 0.0
    if mode == "strict":
        should_fail = mismatch_rows > 0
        threshold = "strict(any mismatch)"
        return should_fail, threshold, ratio
    if mode == "soft":
        should_fail = mismatch_rows > soft_max_count and ratio > soft_max_ratio
        threshold = f"soft(count>{soft_max_count} AND ratio>{soft_max_ratio:.6f})"
        return should_fail, threshold, ratio
    return False, "off", ratio


def write_hero_diff_reports(out_dir: Path, diffs: List[Dict[str, object]]) -> None:
    json_path = out_dir / "hero_diff.json"
    csv_path = out_dir / "hero_diff.csv"
    json_path.write_text(json.dumps(diffs, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["db", "car_id", "expected", "actual", "reason"],
        )
        writer.writeheader()
        for row in diffs:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build per-locale DBs and a combined DB with a global progress bar."
    )
    parser.add_argument(
        "--locales",
        default=",".join(DEFAULT_LOCALES),
        help="Comma-separated locale list",
    )
    parser.add_argument(
        "--base-locale",
        default="",
        help="Canonical locale. Empty = auto (single locale=self, multi locale prefers gb, else first locale)",
    )
    parser.add_argument(
        "--out-dir",
        default="./output",
        help="Output directory for DBs",
    )
    parser.add_argument(
        "--images",
        default="./output/images",
        help="Images directory",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--playwright-workers", type=int, default=4)
    parser.add_argument("--rate", type=float, default=0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--engine",
        choices=["python", "hybrid"],
        default="python",
        help="Execution engine for scraper runs",
    )
    parser.add_argument(
        "--commit-batch",
        type=int,
        default=0,
        help="Commit every N cars (0 = engine default)",
    )
    parser.add_argument(
        "--sqlite-wal",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable SQLite WAL mode (default: hybrid=true, python=false)",
    )
    parser.add_argument(
        "--engines-dir",
        default="./local/bin",
        help="Directory for external hybrid engine binaries",
    )
    parser.add_argument(
        "--download-workers",
        type=int,
        default=32,
        help="Downloader worker count for hybrid engine",
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=30,
        help="Downloader timeout seconds for hybrid engine",
    )
    parser.add_argument(
        "--download-retries",
        type=int,
        default=2,
        help="Downloader retries for hybrid engine",
    )
    parser.add_argument(
        "--playwright-engine",
        choices=["python", "node"],
        default="",
        help="Playwright backend for auto/use-playwright mode",
    )
    parser.add_argument(
        "--spec-engine",
        choices=["python", "rust"],
        default="",
        help="Spec normalization backend (default: python engine=python, rust engine=hybrid)",
    )
    parser.add_argument(
        "--playwright-policy",
        choices=["off", "node", "python"],
        default=None,
        help="Playwright policy: off/node/python. Overrides --use-playwright.",
    )
    parser.add_argument(
        "--image-policy",
        choices=["base-only", "all-locales", "none"],
        default="base-only",
        help="Image download policy for build_dbs workflow",
    )
    parser.add_argument(
        "--text-policy",
        choices=["target-only", "keep-base-and-target"],
        default="target-only",
        help="Per-locale car_texts retention policy",
    )
    parser.add_argument(
        "--hero-check",
        choices=["off", "soft", "strict"],
        default="strict",
        help="Hero image validation mode",
    )
    parser.add_argument(
        "--hero-soft-max-ratio",
        type=float,
        default=0.05,
        help="Soft mode failure threshold for mismatch ratio (strictly greater than this value)",
    )
    parser.add_argument(
        "--hero-soft-max-count",
        type=int,
        default=20,
        help="Soft mode failure threshold for mismatch row count (strictly greater than this value)",
    )
    parser.add_argument(
        "--hero-manifest",
        default=DEFAULT_HERO_MANIFEST,
        help="Path to hero expected-count manifest JSON",
    )
    parser.add_argument(
        "--reference-images-dir",
        default="./output/reference/images",
        help="Deprecated in build flow (kept for compatibility); use scripts/generate_hero_manifest.py",
    )
    parser.add_argument(
        "--hero-min",
        type=int,
        default=3,
        help="Minimum hero image count for cars missing from reference set",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit cars per locale (0 = all)")
    parser.add_argument("--car-list", default="", help="Path to car id list file")
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Enable Playwright fallback (legacy flag; overridden by --playwright-policy)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume mode",
    )
    parser.add_argument(
        "--images-all",
        action="store_true",
        help="Legacy alias for image-policy=all-locales",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip downloading logos and car images for all runs",
    )
    parser.add_argument(
        "--per-locale",
        action="store_true",
        help="Build per-locale DBs (default: on)",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Build combined DB (default: on)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = Path(args.images)
    images_dir.mkdir(parents=True, exist_ok=True)

    raw_locales = [item.strip() for item in args.locales.split(",") if item.strip()]
    if not raw_locales:
        raise SystemExit("No locales provided")

    resolved_base = resolve_base_locale(raw_locales, args.base_locale.strip())
    locales = normalize_locale_order(raw_locales, resolved_base)
    build_per_locale = args.per_locale or not (args.per_locale or args.combined)
    build_combined = args.combined or not (args.per_locale or args.combined)

    image_policy = resolve_image_policy(args.image_policy, args.images_all, args.skip_images)
    if args.hero_check in {"strict", "soft"} and image_policy == "none":
        raise SystemExit(f"hero-check {args.hero_check} requires image downloads; current image-policy is none")

    use_playwright, playwright_engine = resolve_playwright_policy(
        engine=args.engine,
        use_playwright_flag=args.use_playwright,
        requested_policy=args.playwright_policy,
        requested_engine=args.playwright_engine,
    )
    spec_engine = args.spec_engine or ("rust" if args.engine == "hybrid" else "python")
    commit_batch = args.commit_batch if args.commit_batch > 0 else (50 if args.engine == "hybrid" else 1)
    sqlite_wal = args.sqlite_wal if args.sqlite_wal is not None else (args.engine == "hybrid")

    site_total = get_site_total(resolved_base, args.timeout)
    list_total = count_list_total(args.car_list)
    total_runs = (len(locales) if build_per_locale else 0) + (len(locales) if build_combined else 0)
    per_run_total = None
    if list_total is not None and args.limit and args.limit > 0:
        per_run_total = min(list_total, args.limit)
    elif list_total is not None:
        per_run_total = list_total
    elif args.limit and args.limit > 0:
        per_run_total = args.limit
    elif site_total is not None:
        per_run_total = site_total
    total_steps = per_run_total * total_runs if per_run_total is not None else None

    total_bar = tqdm(total=total_steps, desc="Total", position=0, leave=True)

    def progress_cb() -> None:
        total_bar.update(1)

    def run_one(locale: str, db_path: Path, download_images: bool, resume: bool) -> None:
        exit_code = run_scraper(
            locale=locale,
            db_path=db_path,
            image_dir=images_dir,
            limit=args.limit,
            resume=resume,
            use_playwright=use_playwright,
            rate=args.rate,
            timeout=args.timeout,
            workers=args.workers,
            base_locale=resolved_base,
            playwright_workers=args.playwright_workers,
            car_list_path=Path(args.car_list) if args.car_list else None,
            download_images=download_images,
            show_progress=True,
            progress_callback=progress_cb,
            progress_desc=f"Locale {locale}",
            progress_position=1,
            commit_batch=commit_batch,
            sqlite_wal=sqlite_wal,
            engines_dir=Path(args.engines_dir),
            downloader_engine=("go" if args.engine == "hybrid" else "python"),
            download_workers=args.download_workers,
            download_timeout=args.download_timeout,
            download_retries=args.download_retries,
            playwright_engine=playwright_engine,
            spec_engine=spec_engine,
        )
        if exit_code != 0:
            raise RuntimeError(f"run_scraper failed for locale={locale} db={db_path} exit_code={exit_code}")

    per_locale_dbs: List[Path] = []
    combined_db: Optional[Path] = None

    try:
        if build_per_locale:
            template_db = out_dir / ".base_template.db"
            template_db.unlink(missing_ok=True)
            run_one(
                locale=resolved_base,
                db_path=template_db,
                download_images=should_download_for_template(image_policy),
                resume=False,
            )
            checkpoint_template_db(template_db)
            for locale in locales:
                db_path = out_dir / f"gt7.{locale}.db"
                shutil.copy2(template_db, db_path)
                if locale != resolved_base:
                    run_one(
                        locale=locale,
                        db_path=db_path,
                        download_images=should_download_for_overlay(image_policy),
                        resume=args.resume,
                    )
                if args.text_policy == "target-only":
                    prune_texts_for_locale(db_path, locale)
                per_locale_dbs.append(db_path)
            template_db.unlink(missing_ok=True)

        if build_combined:
            combined_db = out_dir / "gt7.db"
            if combined_db.exists() and not args.resume:
                combined_db.unlink()
            for index, locale in enumerate(locales):
                run_one(
                    locale=locale,
                    db_path=combined_db,
                    download_images=should_download_for_combined(image_policy, locale, resolved_base),
                    resume=(args.resume or index > 0),
                )
    except Exception as exc:
        total_bar.close()
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)

    total_bar.close()

    if args.hero_check in {"strict", "soft"}:
        manifest_path = Path(args.hero_manifest)
        ref_counts = load_hero_expected_counts(manifest_path)
        if not ref_counts:
            raise SystemExit(
                f"hero-check {args.hero_check}: hero manifest missing/empty at {manifest_path}. "
                "Generate it via scripts/generate_hero_manifest.py."
            )
        db_targets: List[Path] = []
        db_targets.extend(per_locale_dbs)
        if combined_db is not None:
            db_targets.append(combined_db)
        checked_rows = 0
        all_diffs: List[Dict[str, object]] = []
        for path in db_targets:
            checked, diffs = validate_hero_counts(path, ref_counts, max(1, int(args.hero_min)))
            checked_rows += checked
            all_diffs.extend(diffs)
        write_hero_diff_reports(out_dir, all_diffs)
        mismatch_rows = len(all_diffs)
        should_fail, threshold_desc, mismatch_ratio = evaluate_hero_check_outcome(
            mode=args.hero_check,
            checked_rows=checked_rows,
            mismatch_rows=mismatch_rows,
            soft_max_ratio=float(args.hero_soft_max_ratio),
            soft_max_count=int(args.hero_soft_max_count),
        )
        result_text = "failed" if should_fail else ("warning" if mismatch_rows > 0 else "ok")
        stream = sys.stderr if should_fail or mismatch_rows > 0 else sys.stdout
        print(
            "hero-check summary: "
            f"mode={args.hero_check} "
            f"checked_rows={checked_rows} "
            f"mismatch_rows={mismatch_rows} "
            f"mismatch_ratio={mismatch_ratio:.6f} "
            f"threshold={threshold_desc} "
            f"result={result_text} "
            f"reports=({out_dir / 'hero_diff.csv'}, {out_dir / 'hero_diff.json'})",
            file=stream,
        )
        if should_fail:
            if args.hero_check == "strict":
                raise SystemExit(3)
            raise SystemExit(4)


if __name__ == "__main__":
    main()
