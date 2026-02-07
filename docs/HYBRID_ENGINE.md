# Hybrid Engine Guide

[English](HYBRID_ENGINE.md) | [简体中文](HYBRID_ENGINE.zh-CN.md)

This guide explains how to build and run the hybrid engine path (`--engine hybrid`).
For validated smoke-test commands and results across modes, see [MODE_MATRIX.md](MODE_MATRIX.md).

## Recommendation
- Use hybrid as the primary mode: `--engine hybrid --playwright-policy off`.
- On validated smoke runs, `hybrid_no_pw_rust` is faster than pure Python baseline while keeping the same quality checks.
- Use Playwright only as a fallback path when a specific locale/page needs browser extraction.

## What Hybrid Uses
- Go downloader: `engines/gt7_downloader`
- Node/Playwright worker: `engines/gt7_playwright`
- Rust spec normalizer: `engines/gt7_spec_normalizer`
- C++ merge engine (optional): `engines/gt7_db_merge_cpp`

The Python scraper remains the orchestrator and keeps the same SQLite schema.

## Dependency Environment
Minimum recommended toolchain:
- Python `3.10+`
- Go `1.21+`
- Node.js `18+` and `npm`
- Rust stable (`cargo`)

One-command bootstrap (recommended):
```bash
./scripts/bootstrap_hybrid_env.sh
```

Options:
- `--no-system-install`: only set up venv + build local components
- `--skip-playwright-browser`: skip `npx playwright install chromium`
- `--skip-build`: only install/check toolchain and Python dependencies
- `--skip-cpp-merge-build`: skip building `local/bin/gt7-db-merge`

macOS (Homebrew):
```bash
brew install python go node rustup-init
rustup-init -y
source "$HOME/.cargo/env"
```

Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip golang-go nodejs npm curl build-essential
curl https://sh.rustup.rs -sSf | sh -s -- -y
source "$HOME/.cargo/env"
```

Create Python env:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify toolchain:
```bash
python --version
go version
node --version
npm --version
cargo --version
```

## Build Binaries

### 1) Go downloader
```bash
cd engines/gt7_downloader
go build -o ../../local/bin/gt7-downloader .
```

### 2) Node Playwright worker
```bash
cd engines/gt7_playwright
npm install
npx playwright install
npm run build
```

Run strategy:
- If `./local/bin/gt7-playwright` exists, it is preferred.
- Otherwise, scraper uses `engines/gt7_playwright/dist/cli.js`.

Optional wrapper:
```bash
cat > local/bin/gt7-playwright <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
node "$(cd "$(dirname "$0")/../.." && pwd)/engines/gt7_playwright/dist/cli.js" "$@"
EOF
chmod +x local/bin/gt7-playwright
```

### 3) Rust spec normalizer
```bash
cd engines/gt7_spec_normalizer
cargo build --release
cp target/release/gt7-spec-normalizer ../../local/bin/
```

### 4) C++ merge engine (optional)
```bash
cd engines/gt7_db_merge_cpp
./build.sh
```

## Run Hybrid
```bash
python -m gt7_scraper \
  --engine hybrid \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.db \
  --images ./output/images \
  --skip-images \
  --workers 4 \
  --commit-batch 50 \
  --sqlite-wal \
  --engines-dir ./local/bin
```

`scripts/build_dbs.py` hero check modes:
- `--hero-check off`: disable hero validation
- `--hero-check strict`: fail on any mismatch (exit code `3`)
- `--hero-check soft`: always write diff reports; fail only when both conditions are exceeded:
  - `mismatch_ratio > --hero-soft-max-ratio` (default `0.05`)
  - `mismatch_rows > --hero-soft-max-count` (default `20`)
  - soft failure exit code: `4`

Example (`soft` mode):
```bash
python scripts/build_dbs.py \
  --engine hybrid \
  --locales gb,us,cn,jp \
  --base-locale gb \
  --out-dir ./output \
  --images ./output/images \
  --image-policy all-locales \
  --playwright-policy off \
  --hero-check soft \
  --hero-soft-max-ratio 0.05 \
  --hero-soft-max-count 20 \
  --hero-manifest ./gt7_scraper/mappings/hero_expected_counts.json \
  --engines-dir ./local/bin
```

`scripts/build_dbs.py` combined DB strategies:
- `--combined-mode rescrape` (default): legacy behavior, run all locales directly into `gt7.db`
- `--combined-mode merge`: build `gt7.<locale>.db` first, then merge
- `--merge-engine python|cpp|go`: merge backend when `combined-mode=merge` (default: `go`)
- `--merge-cpp-bin`: C++ merge binary path (default `./local/bin/gt7-db-merge`)
- `--merge-go-bin`: Go merge binary path (default `./local/bin/gt7-db-merge-go`)
- `--hero-check-engine python|rust`: hero-check backend (default: `rust`)

Example (`merge + cpp`, auto-fallback to Python SQL merge on failure):
```bash
python scripts/build_dbs.py \
  --engine hybrid \
  --locales gb,us,cn,jp \
  --base-locale gb \
  --combined-mode merge \
  --merge-engine cpp \
  --merge-cpp-bin ./local/bin/gt7-db-merge \
  --playwright-policy off \
  --engines-dir ./local/bin
```

Build flow uses a hero manifest by default. To regenerate it from local reference images:
```bash
python scripts/generate_hero_manifest.py \
  --reference-images-dir ./output/reference/images \
  --out ./gt7_scraper/mappings/hero_expected_counts.json
```

With Playwright detail fallback:
```bash
python -m gt7_scraper \
  --engine hybrid \
  --use-playwright \
  --playwright-engine node \
  --playwright-workers 4 \
  --engines-dir ./local/bin
```

## Engine Resolution and Fallback
- Downloader:
  - `--engine hybrid` uses Go downloader when found.
  - If `gt7-downloader` is missing, scraper falls back to Python downloader.
- Playwright:
  - `--playwright-engine node` uses Node worker when script/binary is found.
  - If missing, scraper falls back to Python Playwright path.
- Spec normalization:
  - `--spec-engine rust` uses Rust binary when found.
  - If missing or failed, scraper falls back to Python normalization.
- Combined merge:
  - `--combined-mode merge --merge-engine cpp` uses C++ merge binary when found.
  - `--combined-mode merge --merge-engine go` uses Go merge binary when found.
  - If missing or failed, build flow falls back to Python SQL merge.
- Hero validation:
  - `--hero-check-engine rust` uses Rust hero-check binary when found (default behavior).
  - If missing or failed, build flow falls back to Python hero-check.

## Validation Checklist
- CLI flags:
```bash
python -m gt7_scraper --help
python scripts/build_dbs.py --help
```
- Python compile check:
```bash
python -m compileall gt7_scraper gt7_query scripts
```
- Node syntax check:
```bash
node --check engines/gt7_playwright/dist/cli.js
```
- Rust build check:
```bash
cd engines/gt7_spec_normalizer && cargo build --release
cd engines/gt7_hero_check_rust && cargo build --release
cd engines/gt7_query_go && go build -o ../../local/bin/gt7-query-go .
cd engines/gt7_db_merge_go && go build -o ../../local/bin/gt7-db-merge-go .
```

## Optional Bundling
For normal usage, prefer downloading prebuilt release packages first.
Use local bundling only for development/debugging:
```bash
./scripts/package_gt7db.sh --flavor lite
```

Optional debug bundle with browser runtime:
```bash
./scripts/package_gt7db.sh --flavor full
```
