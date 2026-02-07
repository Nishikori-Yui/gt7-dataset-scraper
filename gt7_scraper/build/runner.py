import argparse
import sqlite3
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

from gt7_scraper import db as db_utils
from gt7_scraper.scraper import run_scraper

from .config import (
    DEFAULT_HERO_MANIFEST,
    DEFAULT_LOCALES,
    normalize_locale_order,
    resolve_base_locale,
    resolve_image_policy,
    resolve_playwright_policy,
    should_download_for_combined,
    should_download_for_overlay,
    should_download_for_template,
)
from .hero_check import (
    evaluate_hero_check_outcome,
    load_hero_expected_counts,
    validate_hero_counts,
    write_hero_diff_reports,
)
from .hero_check_rust import run_rust_hero_check
from .merge_cpp import run_cpp_merge
from .merge_go import run_go_merge
from .merge_sql import merge_locale_dbs
from .progress import TotalProgress


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


def add_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--out-dir", default="./output", help="Output directory for DBs")
    parser.add_argument("--images", default="./output/images", help="Images directory")
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
    parser.add_argument("--engines-dir", default="./local/bin", help="Directory for external hybrid binaries")
    parser.add_argument("--download-workers", type=int, default=32, help="Downloader worker count for hybrid")
    parser.add_argument("--download-timeout", type=int, default=30, help="Downloader timeout seconds")
    parser.add_argument("--download-retries", type=int, default=2, help="Downloader retries")
    parser.add_argument(
        "--catalog-engine",
        choices=["python", "go"],
        default="",
        help="Catalog/detail parser backend (default: python engine=python, go engine=hybrid)",
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
        help="Image download policy for build workflow",
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
    parser.add_argument("--resume", action="store_true", help="Resume mode")
    parser.add_argument("--images-all", action="store_true", help="Legacy alias for image-policy=all-locales")
    parser.add_argument("--skip-images", action="store_true", help="Skip downloading all images")
    parser.add_argument("--per-locale", action="store_true", help="Build per-locale DBs (default: on)")
    parser.add_argument("--combined", action="store_true", help="Build combined DB (default: on)")
    parser.add_argument(
        "--combined-mode",
        choices=["rescrape", "merge"],
        default="rescrape",
        help="Combined DB build mode. rescrape keeps legacy behavior; merge merges per-locale DBs.",
    )
    parser.add_argument(
        "--merge-engine",
        choices=["python", "cpp", "go"],
        default="go",
        help="Merge backend when --combined-mode=merge",
    )
    parser.add_argument(
        "--merge-cpp-bin",
        default="./local/bin/gt7-db-merge",
        help="C++ merge binary path used when --merge-engine=cpp",
    )
    parser.add_argument(
        "--merge-go-bin",
        default="./local/bin/gt7-db-merge-go",
        help="Go merge binary path used when --merge-engine=go",
    )
    parser.add_argument(
        "--hero-check-engine",
        choices=["python", "rust"],
        default="rust",
        help="Hero validation backend",
    )
    parser.add_argument(
        "--hero-check-rust-bin",
        default="./local/bin/gt7-hero-check",
        help="Rust hero-check binary path",
    )
    parser.add_argument(
        "--backend-fallback",
        choices=["on", "off"],
        default="on",
        help="Allow fallback to python backends when native backend fails",
    )


def run(args: argparse.Namespace) -> None:
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
    catalog_engine = args.catalog_engine or ("go" if args.engine == "hybrid" else "python")
    spec_engine = args.spec_engine or ("rust" if args.engine == "hybrid" else "python")
    commit_batch = args.commit_batch if args.commit_batch > 0 else (50 if args.engine == "hybrid" else 1)
    sqlite_wal = args.sqlite_wal if args.sqlite_wal is not None else (args.engine == "hybrid")

    tracker = TotalProgress(desc="Total")

    def progress_cb() -> None:
        tracker.tick(1)

    def run_one(locale: str, db_path: Path, download_images: bool, resume: bool) -> None:
        planned_reported = {"done": False}

        def plan_cb(planned_total: int, site_total: Optional[int], current_locale: str) -> None:
            if planned_reported["done"]:
                return
            tracker.add_plan(current_locale, planned_total, site_total)
            planned_reported["done"] = True

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
            plan_callback=plan_cb,
            progress_desc=f"Locale {locale}",
            progress_position=1,
            commit_batch=commit_batch,
            sqlite_wal=sqlite_wal,
            engines_dir=Path(args.engines_dir),
            downloader_engine=("go" if args.engine == "hybrid" else "python"),
            download_workers=args.download_workers,
            download_timeout=args.download_timeout,
            download_retries=args.download_retries,
            catalog_engine=catalog_engine,
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
                if db_path.exists() and not args.resume:
                    db_path.unlink()
                if locale == resolved_base:
                    shutil.copy2(template_db, db_path)
                else:
                    shutil.copy2(template_db, db_path)
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
            if args.combined_mode == "rescrape":
                if combined_db.exists() and not args.resume:
                    combined_db.unlink()
                for index, locale in enumerate(locales):
                    run_one(
                        locale=locale,
                        db_path=combined_db,
                        download_images=should_download_for_combined(image_policy, locale, resolved_base),
                        resume=(args.resume or index > 0),
                    )
            else:
                merge_locales = locales
                if not build_per_locale:
                    per_locale_dbs = [out_dir / f"gt7.{locale}.db" for locale in merge_locales]
                    missing = [path for path in per_locale_dbs if not path.exists()]
                    if missing:
                        missing_text = ", ".join(str(path) for path in missing)
                        raise SystemExit(
                            f"combined-mode=merge requires existing per-locale DBs when --no-per-locale. Missing: {missing_text}"
                        )

                did_native_merge = False
                if args.merge_engine == "cpp":
                    ok, msg = run_cpp_merge(
                        binary=Path(args.merge_cpp_bin),
                        out_dir=out_dir,
                        base_locale=resolved_base,
                        locales=merge_locales,
                        combined_db=combined_db,
                        include_fetch_log=True,
                        checkpoint=True,
                    )
                    if ok:
                        did_native_merge = True
                        if msg:
                            print(msg)
                    else:
                        if args.backend_fallback == "off":
                            raise SystemExit(f"merge-engine=cpp failed and backend-fallback=off: {msg}")
                        print(f"warning: {msg}; falling back to python merge engine", file=sys.stderr)
                elif args.merge_engine == "go":
                    ok, msg = run_go_merge(
                        binary=Path(args.merge_go_bin),
                        out_dir=out_dir,
                        base_locale=resolved_base,
                        locales=merge_locales,
                        combined_db=combined_db,
                        include_fetch_log=True,
                        checkpoint=True,
                    )
                    if ok:
                        did_native_merge = True
                        if msg:
                            print(msg)
                    else:
                        if args.backend_fallback == "off":
                            raise SystemExit(f"merge-engine=go failed and backend-fallback=off: {msg}")
                        print(f"warning: {msg}; falling back to python merge engine", file=sys.stderr)

                if not did_native_merge:
                    merge_locale_dbs(
                        out_dir=out_dir,
                        base_locale=resolved_base,
                        locales=merge_locales,
                        combined_db=combined_db,
                        overwrite=True,
                        include_fetch_log=True,
                        checkpoint=True,
                        emit=print,
                    )
    except Exception as exc:
        tracker.close()
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)

    tracker.close()

    if args.hero_check in {"strict", "soft"}:
        manifest_path = Path(args.hero_manifest)
        ref_counts: Dict[str, int] = load_hero_expected_counts(manifest_path)
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
        if args.hero_check_engine == "rust":
            ok, msg, checked_rows, all_diffs = run_rust_hero_check(
                binary=Path(args.hero_check_rust_bin),
                db_paths=db_targets,
                manifest_path=manifest_path,
                hero_min=max(1, int(args.hero_min)),
            )
            if ok:
                if msg:
                    print(msg)
            else:
                if args.backend_fallback == "off":
                    raise SystemExit(f"hero-check-engine=rust failed and backend-fallback=off: {msg}")
                print(f"warning: {msg}; falling back to python hero-check", file=sys.stderr)
                checked_rows = 0
                all_diffs = []

        if checked_rows == 0 and not all_diffs:
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
