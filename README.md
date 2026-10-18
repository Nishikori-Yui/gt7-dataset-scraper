# GT7 Dataset Scraper

[简体中文](README.zh-CN.md)

Scrape the official Gran Turismo 7 car catalog into SQLite, with optional local images.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), download the package for your platform from [GitHub Releases](https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest), and extract it:

```sh
cd GT7DB_vX.Y.Z_linux_AMD64
./scripts/bootstrap.sh
uv run --locked bin/gt7db doctor
uv run --locked bin/gt7db scrape --locale gb --limit 10 --skip-images
uv run --locked bin/gt7db query overview --db output/gt7.db
```

On Windows, run `uv sync --locked`, then `bin\gt7db.cmd`.

## Develop from source

Use uv to manage the Python environment and dependencies (Python 3.10+). uv downloads a compatible Python if needed. Go is optional and only used for the catalog parser and image downloader.

```sh
uv sync --locked
uv run --locked python -m gt7_scraper --help
```

Build the optional Go tools with `./scripts/bootstrap.sh --build-go` (Go 1.23+). The scraper uses them automatically when available and works with Python alone. For browser fallback, run `uv sync --locked --extra browser` and `uv run --locked --extra browser python -m playwright install chromium`.

See [Usage](docs/USAGE.md), [database schema](docs/DB_SCHEMA.md), and [release packaging](docs/RELEASE_PACKAGING.md).

## Legal and license

The Apache-2.0 license covers this repository's code only. It does not grant rights to the website, data, images, trademarks, or other third-party material. Review applicable terms and laws before scraping. Do not redistribute scraped data or assets. See [legal guidance](docs/LEGAL_AND_PUBLISHING.md).
