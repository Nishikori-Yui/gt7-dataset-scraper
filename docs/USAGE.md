# Usage

[简体中文](USAGE.zh-CN.md)

## Setup

For a source checkout, install Python 3.10+ and run:

```sh
./scripts/bootstrap.sh
source .venv/bin/activate
```

Go is optional. Use `./scripts/bootstrap.sh --build-go` to build the catalog parser and image downloader. The scraper detects them automatically; Python handles the same tasks when they are unavailable. Playwright is also optional; install it and Chromium only when browser fallback is needed.

On Windows, use `python -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`, and `.venv\Scripts\activate`.

## Scrape one locale

```sh
python -m gt7_scraper \
  --locale gb \
  --limit 10 \
  --car-list scripts/example_car_ids_10.txt \
  --skip-images
```

By default, the database is `output/gt7.db`. Remove `--limit` and `--car-list` to scrape the full catalog. Use `--resume` to skip cars already recorded as successful. Images go to `output/images/` unless `--skip-images` is set.

## Build multiple locales

```sh
python scripts/build_dbs.py --resume
```

This fetches all 21 locales, downloads shared images once in the base locale, and merges the locale databases into `gt7.db`. `--resume` retains existing locale databases and skips successful cars. Use `--locales gb,us,cn` or `--limit 10` for a smaller run.

Use `--no-combined` to keep only the locale databases, or `--no-per-locale` to merge existing ones. Hero image validation defaults to `strict`; use `--image-policy none --hero-check off` when building without images.

## Query a database

```sh
python -m gt7_query overview --db output/gt7.db
python -m gt7_query list --db output/gt7.db --locale gb --limit 10
python -m gt7_query car --db output/gt7.db --locale cn --car-id car31
python -m gt7_query stats --db output/gt7.db --by country
```

Queries use Python and SQLite. The same commands are available through the release launcher, for example `bin/gt7db query overview --db output/gt7.db`.

## Browser fallback

Install Playwright only when static page data does not provide enough detail:

```sh
python -m pip install playwright
python -m playwright install chromium
python -m gt7_scraper --locale gb --use-playwright
```

Use `python scripts/gt7db.py doctor --json` to inspect a source checkout or a release package.
