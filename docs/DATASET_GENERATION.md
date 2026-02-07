# Dataset Generation

[English](DATASET_GENERATION.md) | [简体中文](DATASET_GENERATION.zh-CN.md)

This document describes how to generate a GT7 SQLite dataset using `gt7_scraper`.
For a conceptual overview (components + data flow), see [ARCHITECTURE.md](ARCHITECTURE.md).
For hybrid mode build/run details, see [HYBRID_ENGINE.md](HYBRID_ENGINE.md).

## What Gets Stored
By default, a run writes:
- Canonical (base-locale) cars and manufacturers into `cars` and `manufacturers`
- Per-locale text/specs into `car_texts` and `car_specs`
- Per-locale labels (specs, drivetrain, aspiration) into `spec_code_i18n`, `drivetrain_i18n`, `aspiration_i18n`
- Per-car status logs into `fetch_log` and run-wide counters into `meta`
- Optional images into `car_images` and `output/images/` (unless `--skip-images`)

## Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Bootstrap scripts:
```bash
# pure Python mode
./scripts/bootstrap_python_env.sh

# hybrid mode (Go + Node + Rust)
./scripts/bootstrap_hybrid_env.sh
```

Optional Playwright fallback (for detail page extraction and list thumbnails):
```bash
pip install playwright
python -m playwright install
```

## Locales
The scraper accepts a locale code and fetches language-specific data:
- `gb`, `us`, `cn`, `tw`, `jp`, `kr`
- `de`, `fr`, `it`, `nl`, `es`, `mx`, `pt`, `br`, `pl`, `ru`
- `cz`, `tr`, `gr`, `sa`, `th`

Notes:
- `--base-locale` controls which locale is considered canonical for `cars` and `manufacturers`.
- Other locales do not overwrite canonical fields in `cars` / `manufacturers`; they populate i18n tables.
- Some locales use different URL/path codes vs asset chunk codes; this is handled automatically.

## Recommended Workflow (Base + Extra Locales)
```mermaid
flowchart TB
  A["Start"] --> B{"Already have a DB?"}
  B -->|No| C["Run base locale once\n--locale gb --base-locale gb"]
  B -->|Yes| D["Update base locale (optional)\n--locale gb --base-locale gb --resume"]
  C --> E{"Need more locales?"}
  D --> E
  E -->|No| F["Done"]
  E -->|Yes| G["Run extra locales\n--locale <L> --base-locale gb --resume"]
  G --> F
```

Example (gb + cn):
```bash
python -m gt7_scraper --locale gb --base-locale gb --db ./output/gt7.db --images ./output/images --skip-images
python -m gt7_scraper --locale cn --base-locale gb --db ./output/gt7.db --images ./output/images --resume --skip-images
```

## Small Test Runs
Limit the number of cars while validating your environment:
```bash
python -m gt7_scraper --locale gb --base-locale gb --db ./output/gt7.db --images ./output/images --limit 3
```

Scrape a specific list of cars:
```bash
cat > /tmp/cars.txt <<'EOF'
# one carId per line
car31
car105
EOF

python -m gt7_scraper --locale gb --base-locale gb --db ./output/gt7.db --images ./output/images --car-list /tmp/cars.txt
```

## Flags (Practical Notes)
- `--engine python|hybrid`: choose execution mode (`hybrid` currently enables SQLite WAL + batched commits)
- `--commit-batch N`: commit every N cars (engine default: `python=1`, `hybrid=50`)
- `--sqlite-wal` / `--no-sqlite-wal`: explicitly enable or disable WAL mode
- `--engines-dir PATH`: directory where hybrid external binaries are resolved
- `--download-workers N`: downloader worker count for hybrid image downloads
- `--download-timeout SEC`: downloader timeout for hybrid image downloads
- `--download-retries N`: downloader retries for hybrid image downloads
- `--playwright-engine python|node`: Playwright backend selection
- `--spec-engine python|rust`: spec normalization backend selection
- `--resume`: skips cars whose latest `fetch_log` status is `success` for the locale you are running
- `--workers N`: parallelizes per-car processing using a thread pool (default: 1)
- `--rate SEC`: sleeps after each processed car (global throttling; default: `0.7`)
- `--timeout SEC`: request timeout used by HTTP fetches (and as an upper bound for Playwright waits)
- `--use-playwright`: enables the Playwright fallback extraction path
- `--playwright-workers N`: uses a dedicated Playwright pool (recommended only when `--use-playwright` is needed)
- `--skip-images`: does not download images and does not create the `car_images` table for new DBs
- `--hero-check off|soft|strict` (build_dbs): `strict` fails on any mismatch, `soft` reports diffs and fails only if both ratio and count exceed thresholds
- `--hero-soft-max-ratio` (build_dbs): soft mode ratio threshold (default `0.05`)
- `--hero-soft-max-count` (build_dbs): soft mode count threshold (default `20`)
- `--hero-manifest` (build_dbs): expected hero-count manifest (default `./gt7_scraper/mappings/hero_expected_counts.json`)
- `--reference-images-dir` (build_dbs): deprecated in build flow; use only with manifest generator script
- `--combined-mode rescrape|merge` (build_dbs): combined DB strategy (`rescrape` is default for backward compatibility)
- `--merge-engine python|cpp|go` (build_dbs): merge backend when `--combined-mode=merge` (default: `go`)
- `--merge-cpp-bin` (build_dbs): C++ merge binary path (default `./local/bin/gt7-db-merge`)
- `--merge-go-bin` (build_dbs): Go merge binary path (default `./local/bin/gt7-db-merge-go`)
- `--hero-check-engine python|rust` (build_dbs): hero validation backend (default `rust`)
- `--hero-check-rust-bin` (build_dbs): Rust hero-check binary path (default `./local/bin/gt7-hero-check`)

For `scripts/build_dbs.py`, global `Total` progress uses the final planned car count after `--limit`, `--car-list`, and `--resume` are applied.
If you build both per-locale and combined DBs in one command, the same locale may appear twice in progress (per-locale phase + combined phase), which is expected.

Generate/refresh hero manifest from a local reference dataset:
```bash
python scripts/generate_hero_manifest.py \
  --reference-images-dir ./output/reference/images \
  --out ./gt7_scraper/mappings/hero_expected_counts.json
```

## Image Handling
When enabled (default), images are downloaded into `--images` with a stable folder structure:
- manufacturer logo: `manufacturers/<manufacturer_id>/logo.<ext>`
- car images: `cars/<car_id>/<car_id>_hero_XX.<ext>` and `cars/<car_id>/<car_id>_thumb_XX.<ext>`

Notes:
- Downloads are idempotent: if a file already exists, it is not re-downloaded.
- Use `--skip-images` for faster runs and to reduce legal risk when publishing.

## Integrity Check and Exit Codes
If `--limit` is not used and no `--car-list` is provided, the scraper compares the scraped
car count to the site total (when available).

On mismatch:
- exit code is `2`
- `meta.status` is set to `count_mismatch`

On success:
- exit code is `0`
- `meta.status` is set to `ok`

## Troubleshooting
- `Failed to locate index JS bundle`: the car list HTML structure changed or the locale path is incorrect; retry later or try a different locale.
- Frequent timeouts: increase `--timeout`, reduce `--workers`, and consider keeping a non-zero `--rate`.
- Missing intro/detail/specs: enable `--use-playwright` (slower, but more robust).
- Count mismatch: re-run without `--resume` (to refresh failures) or inspect failures in `fetch_log`.
