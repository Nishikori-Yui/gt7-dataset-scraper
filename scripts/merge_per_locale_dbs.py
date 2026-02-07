import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gt7_scraper.app.merge_runner import add_cli_arguments, run_from_args


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge per-locale DBs (gt7.<locale>.db) into one combined gt7.db without re-scraping."
    )
    add_cli_arguments(parser)
    args = parser.parse_args()
    run_from_args(args)


if __name__ == "__main__":
    main()
