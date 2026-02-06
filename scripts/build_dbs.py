import argparse
import sys
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def get_site_total(locale: str, timeout: int) -> Optional[int]:
    session = build_session()
    path_locale, _ = resolve_locales(locale)
    html = fetch_text(session, f"{BASE_URL}/{path_locale}/gt7/carlist/", timeout)
    return extract_site_total_count(html)


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
        default="gb",
        help="Canonical locale for combined DB",
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
    parser.add_argument("--limit", type=int, default=0, help="Limit cars per locale (0 = all)")
    parser.add_argument("--car-list", default="", help="Path to car id list file")
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Enable Playwright fallback",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume mode",
    )
    parser.add_argument(
        "--images-all",
        action="store_true",
        help="Download images for every locale DB (default: only base locale)",
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

    locales = [l.strip() for l in args.locales.split(",") if l.strip()]
    if args.base_locale not in locales:
        locales.insert(0, args.base_locale)

    build_per_locale = args.per_locale or not (args.per_locale or args.combined)
    build_combined = args.combined or not (args.per_locale or args.combined)

    site_total = get_site_total(args.base_locale, args.timeout)
    list_total = None
    if args.car_list:
        try:
            with Path(args.car_list).open("r", encoding="utf-8") as f:
                list_total = len([ln for ln in (line.strip() for line in f) if ln and not ln.startswith("#")])
        except Exception:
            list_total = None
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

    if build_per_locale:
        for locale in locales:
            db_path = out_dir / f"gt7.{locale}.db"
            download_images = args.images_all or (locale == args.base_locale)
            run_scraper(
                locale=locale,
                db_path=db_path,
                image_dir=images_dir,
                limit=args.limit,
                resume=args.resume,
                use_playwright=args.use_playwright,
                rate=args.rate,
                timeout=args.timeout,
                workers=args.workers,
                base_locale=args.base_locale,
                playwright_workers=args.playwright_workers,
                car_list_path=Path(args.car_list) if args.car_list else None,
                download_images=download_images,
                show_progress=True,
                progress_callback=progress_cb,
                progress_desc=f"Locale {locale}",
                progress_position=1,
            )

    if build_combined:
        combined_db = out_dir / "gt7.db"
        for i, locale in enumerate(locales):
            download_images = args.images_all or (locale == args.base_locale)
            run_scraper(
                locale=locale,
                db_path=combined_db,
                image_dir=images_dir,
                limit=args.limit,
                resume=(args.resume or i > 0),
                use_playwright=args.use_playwright,
                rate=args.rate,
                timeout=args.timeout,
                workers=args.workers,
                base_locale=args.base_locale,
                playwright_workers=args.playwright_workers,
                car_list_path=Path(args.car_list) if args.car_list else None,
                download_images=download_images,
                show_progress=True,
                progress_callback=progress_cb,
                progress_desc=f"Locale {locale}",
                progress_position=1,
            )

    total_bar.close()


if __name__ == "__main__":
    main()
