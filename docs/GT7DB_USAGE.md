# gt7db Usage Guide

[English](GT7DB_USAGE.md) | [简体中文](GT7DB_USAGE.zh-CN.md)

This guide explains how to use `gt7db`, the unified launcher for scrape/build/query workflows.

## Recommended Start
Use a prebuilt release package first:
- https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest
- choose `GT7DB_*_LITE_<OS>_<ARCH>`

Then run:
```bash
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db doctor --json
```

## Command Surface
`gt7db` supports these commands:
- `scrape`: run `python -m gt7_scraper`
- `build-dbs`: run `python scripts/build_dbs.py`
- `query`: run `python -m gt7_query`
- `doctor`: show runtime layout and default backend profile

## Packaged vs Source Mode
In packaged mode (release archives), `gt7db` injects defaults when missing:
- `scrape`: `--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`: `--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`: `--query-engine go --query-fallback off`

In source mode (repo checkout), no packaged-default injection is applied.

If you explicitly pass a flag (for example `--query-engine python`), your value is respected.

## Common Workflows
### 1) Health check
```bash
./bin/gt7db doctor --json
```

### 2) Scrape one locale
```bash
./bin/gt7db scrape \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.gb.db \
  --images ./output/images \
  --skip-images
```

### 3) Build multiple locale DBs + combined DB
```bash
./bin/gt7db build-dbs \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --out-dir ./output/release-run \
  --combined-mode merge \
  --skip-images \
  --car-list scripts/example_car_ids_10.txt
```

### 4) Query
```bash
./bin/gt7db query overview --db ./output/release-run/gt7.db
./bin/gt7db query list --db ./output/release-run/gt7.db --locale gb --limit 10
```

For detailed query output formats and filters, see `QUERY_CLI.md`.

## Environment Variables
- `GT7DB_ROOT`: force runtime root discovery.
- `GT7DB_PYTHON`: force a Python executable path used by launcher.

`GT7DB_NATIVE_DIR` is set by launcher for child processes in packaged mode.

## Troubleshooting
- `error: no Python runtime found`:
  - in packaged mode, check `runtime/python/`
  - in source mode, check `.venv` or system `python3/python`
- backend binary missing:
  - run `gt7db doctor --json`
  - verify `runtime/native/` has required binaries
- command fails without fallback:
  - packaged defaults use `fallback=off`
  - pass explicit fallback flags only if you intentionally need fallback behavior

## Related Docs
- Release packaging: `RELEASE_PACKAGING.md`
- Dataset generation: `DATASET_GENERATION.md`
- Query CLI details: `QUERY_CLI.md`
- Hybrid backend behavior: `HYBRID_ENGINE.md`
