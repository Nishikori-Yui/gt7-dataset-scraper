# Release Packaging (gt7db)

[English](RELEASE_PACKAGING.md) | [简体中文](RELEASE_PACKAGING.zh-CN.md)

This document defines how GT7-Dataset is distributed and consumed in production.

## Preferred Consumption Path
Use the prebuilt GitHub Release package first.

- Download from: https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest
- Choose `GT7DB_*_LITE_<OS>_<ARCH>` for your host platform.
- Run `bin/gt7db` (`bin/gt7db.exe` on Windows) directly.

Manual local build is intended for development, debugging, or custom packaging needs.
For command-level operations, see `GT7DB_USAGE.md`.

## Distribution Goals
- `gt7db` (.NET launcher) is the unified entrypoint.
- Common workflows run without local Go/Rust/Node/Python toolchains.
- Packaged runtime uses native-first defaults and deterministic fallback policy (`fallback=off`).
- Release artifacts exclude Python backend modules that are replaced by native implementations.

## Package Types
- `lite` (default release artifact):
  - `gt7db` launcher
  - bundled Python runtime + minimal worker/orchestration modules
  - required native binaries
  - no Playwright browser runtime
- `full` (optional, local/manual only):
  - `lite` + Node runtime + Playwright worker + browser dependencies
  - intended for debugging environments that explicitly require browser fallback

## Target Platforms
- `darwin-arm64`
- `darwin-amd64`
- `linux-amd64`
- `linux-arm64`
- `win-amd64`
- `win-arm64`

## Artifact Naming
Release package directory and archives use:
- `GT7DB_<version>_<FLAVOR>_<os>_<ARCH>`

Examples:
- `GT7DB_v1.2.3_LITE_macOS_ARM64`
- `GT7DB_v1.2.3_LITE_windows_AMD64.zip`
- `GT7DB_v1.2.3_LITE_linux_ARM64.tar.gz`

## Package Layout
```text
<package-root>/
  bin/
    gt7db            # or gt7db.exe on Windows
  runtime/
    python/
      ...            # bundled Python runtime
      worker/
        gt7_scraper/
        gt7_query/
        scripts/build_dbs.py
    native/
      gt7-catalog-go
      gt7-downloader
      gt7-spec-normalizer
      gt7-db-merge-go
      gt7-hero-check
      gt7-query-go
      ...
  manifest.json
  SHA256SUMS
```

## Runtime Defaults in Package
The packaged `gt7db` launcher injects these defaults when not explicitly provided:
- `scrape`: `--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`: `--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`: `--query-engine go --query-fallback off` (go-first)

`--engines-dir` / binary paths are injected to `runtime/native` in packaged mode.

## Excluded Python Modules
Default release artifacts exclude replaceable Python backend modules, including:
- `gt7_query/backends/python_backend.py`
- legacy entry compatibility shims (`gt7_query/cli.py`, `gt7_query/queries.py`, `gt7_scraper/cli.py`, `gt7_scraper/scraper.py`)
- legacy engine bridge shims under `gt7_scraper/engine/*` for catalog/downloader/playwright/spec

For diagnostics, use `--include-full-python-backends` in manual packaging.

## Quick Run (From Downloaded Release)
```bash
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db doctor --json
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db scrape --locale gb --db ./output/gt7.db --images ./output/images --skip-images
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db query overview --db ./output/gt7.db
```

## Manual Packaging (Optional)
Prerequisites:
- Python 3.13+
- Go
- Rust/Cargo
- .NET 8 SDK
- Node 20+ (only when building `full`)

### Lite (recommended manual path)
```bash
python scripts/release/build_release.py \
  --flavor lite \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### Full (debug-only optional)
```bash
python scripts/release/build_release.py \
  --flavor full \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### Manual matrix build (lite-first)
```bash
TAG=vX.Y.Z
for PLATFORM in darwin-arm64 darwin-amd64 linux-amd64 linux-arm64 win-amd64 win-arm64; do
  python scripts/release/build_release.py \
    --flavor lite \
    --platform "${PLATFORM}" \
    --version "${TAG}" \
    --out-dir ./dist/release
done
```

### Smoke check
```bash
python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_LITE_macOS_ARM64
```

## CI/CD Release Flow
Workflow: `.github/workflows/release-packages.yml`

Triggers:
- Push tag: `v*`
- Manual dispatch with `tag` input

Pipeline (default release path):
1. Matrix build by platform (lite-only) produces package archives.
2. Smoke checks validate runtime defaults and `query-fallback=off` behavior.
3. Artifacts are uploaded.
4. GitHub Release is published/updated with artifacts and checksums.

## Troubleshooting
- Missing native backend in package:
  - Run `bin/gt7db doctor --json`.
  - Check `runtime/native` and `manifest.json`.
- Worker startup failure:
  - Verify `runtime/python` exists.
  - Verify `runtime/python/worker` includes `gt7_scraper`, `gt7_query`, `scripts/build_dbs.py`.
- Platform mismatch:
  - Verify package suffix matches host architecture.
  - Rebuild with the correct `--platform` when using manual packaging.
- Browser fallback required:
  - Use manual `full` package build.
