import argparse
import sqlite3
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from gt7_scraper import db as db_utils
from gt7_scraper.scraper import run_scraper

from .config import (
    DEFAULT_HERO_MANIFEST,
    DEFAULT_LOCALES,
    normalize_locale_order,
    resolve_base_locale,
    should_download_for_overlay,
    should_download_for_template,
)
from .hero_validate import run_hero_validation
from .merge_sql import merge_locale_dbs
from .progress import TotalProgress


def prune_locale_payload_for_locale(db_path: Path, locale: str) -> None:
    conn = db_utils.connect_db(db_path)
    try:
        db_utils.prune_locale_rows_except_locale(conn, locale)
    finally:
        conn.close()


def checkpoint_db(db_path: Path) -> None:
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
        "--commit-batch",
        type=int,
        default=50,
        help="Commit every N cars (default: 50)",
    )
    parser.add_argument(
        "--sqlite-wal",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable SQLite WAL mode (default: on)",
    )
    parser.add_argument("--download-workers", type=int, default=32, help="Image download worker count (default: 32)")
    parser.add_argument("--download-timeout", type=int, default=30, help="Image download timeout in seconds (default: 30)")
    parser.add_argument("--download-retries", type=int, default=2, help="Image download retries (default: 2)")
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
        help="Per-locale locale-scoped data retention policy",
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
        help="Enable optional Python Playwright fallback",
    )
    parser.add_argument("--resume", action="store_true", help="Resume mode")
    parser.add_argument("--per-locale", action=argparse.BooleanOptionalAction, default=True, help="Build per-locale DBs")
    parser.add_argument("--combined", action=argparse.BooleanOptionalAction, default=True, help="Merge per-locale DBs into gt7.db")


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

    build_per_locale = args.per_locale
    build_combined = args.combined
    if not (build_per_locale or build_combined):
        raise SystemExit("Enable at least one of --per-locale or --combined")

    image_policy = args.image_policy
    if args.hero_check in {"strict", "soft"} and image_policy == "none":
        raise SystemExit(f"hero-check {args.hero_check} requires image downloads; current image-policy is none")


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
            use_playwright=args.use_playwright,
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
            commit_batch=max(1, args.commit_batch),
            sqlite_wal=args.sqlite_wal,
            download_workers=args.download_workers,
            download_timeout=args.download_timeout,
            download_retries=args.download_retries,
        )
        if exit_code != 0:
            raise RuntimeError(f"run_scraper failed for locale={locale} db={db_path} exit_code={exit_code}")

    per_locale_dbs: List[Path] = []
    combined_db: Optional[Path] = None

    try:
        if build_per_locale:
            base_db = out_dir / f"gt7.{resolved_base}.db"
            if not args.resume:
                base_db.unlink(missing_ok=True)
            run_one(
                locale=resolved_base,
                db_path=base_db,
                download_images=should_download_for_template(image_policy),
                resume=args.resume,
            )
            checkpoint_db(base_db)
            for locale in locales:
                db_path = out_dir / f"gt7.{locale}.db"
                if locale != resolved_base:
                    if not (args.resume and db_path.exists()):
                        shutil.copy2(base_db, db_path)
                    run_one(
                        locale=locale,
                        db_path=db_path,
                        download_images=should_download_for_overlay(image_policy),
                        resume=args.resume,
                    )
                if args.text_policy == "target-only":
                    prune_locale_payload_for_locale(db_path, locale)
                per_locale_dbs.append(db_path)

        if build_combined:
            combined_db = out_dir / "gt7.db"
            if not build_per_locale:
                per_locale_dbs = [out_dir / f"gt7.{locale}.db" for locale in locales]
            merge_locale_dbs(
                out_dir=out_dir,
                base_locale=resolved_base,
                locales=locales,
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

    run_hero_validation(args=args, out_dir=out_dir, per_locale_dbs=per_locale_dbs, combined_db=combined_db)
