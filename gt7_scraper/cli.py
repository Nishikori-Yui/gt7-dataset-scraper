import argparse
import sys
from pathlib import Path

from .scraper import run_scraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape GT7 car catalog and store into SQLite."
    )
    parser.add_argument("--locale", default="us", help="Locale code, default: us")
    parser.add_argument("--out", default="./output", help="Base output directory")
    parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    parser.add_argument(
        "--images",
        default="./output/images",
        help="Image output directory",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of cars (0 = all)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip cars already marked as success",
    )
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Use Playwright fallback for missing fields (optional)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.7,
        help="Delay between cars in seconds",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent workers (default: 1)",
    )
    parser.add_argument(
        "--base-locale",
        default="gb",
        help="Locale used as canonical values in cars table (default: gb)",
    )
    parser.add_argument(
        "--playwright-workers",
        type=int,
        default=0,
        help="Playwright worker pool size (0 = reuse per thread, default: 0)",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip downloading logos and car images",
    )
    parser.add_argument(
        "--car-list",
        default="",
        help="Path to car id list file (one carId per line)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    out_dir = Path(args.out)
    db_path = Path(args.db)
    image_dir = Path(args.images)

    out_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    exit_code = run_scraper(
        locale=args.locale,
        db_path=db_path,
        image_dir=image_dir,
        limit=args.limit,
        resume=args.resume,
        use_playwright=args.use_playwright,
        rate=args.rate,
        timeout=args.timeout,
        workers=args.workers,
        base_locale=args.base_locale,
        playwright_workers=args.playwright_workers,
        car_list_path=Path(args.car_list) if args.car_list else None,
        download_images=not args.skip_images,
    )
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
