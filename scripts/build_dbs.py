import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gt7_scraper.build import add_arguments, run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build per-locale DBs and a combined DB with a global progress bar."
    )
    add_arguments(parser)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
