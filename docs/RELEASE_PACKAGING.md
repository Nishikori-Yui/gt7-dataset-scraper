# Release Packaging (gt7db)

[English](RELEASE_PACKAGING.md) | [简体中文](RELEASE_PACKAGING.zh-CN.md)

This document defines the release packaging system for GT7-Dataset.

## Goals
- Use `gt7db` (.NET launcher) as the single entrypoint.
- End users run common flows without installing Go/Rust/Node/Python locally.
- Release packages default to non-Python backends and default `fallback=off`.
- Default release artifacts exclude Python modules that are replaced by native backends.

## Package Flavors
- `lite`:
  - `gt7db` launcher
  - bundled Python runtime + minimal worker modules
  - required native binaries
  - no Playwright browser runtime
- `full`:
  - everything in `lite`
  - bundled Node runtime + Playwright worker + Chromium browser dependency

## Target Platforms
- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `linux-arm64`
- `win-x64`
- `win-arm64`

## Artifact Naming
Release package directory and archive names now use:
- `GT7DB_<version>_<FLAVOR>_<os>_<ARCH>`

Examples:
- `GT7DB_v1.2.3_LITE_macOS_ARM64`
- `GT7DB_v1.2.3_FULL_windows_AMD64.zip`
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

## Default Backend Profile (Release Package)
The packaged `gt7db` launcher injects these defaults when not explicitly provided:
- `scrape`: `--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`: `--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`: `--query-engine go --query-fallback off` (go-first)

`--engines-dir` / binary paths are also injected to `runtime/native` in packaged mode.

## Python Module Exclusion Policy
Default release package excludes modules that are replaceable by native backends, including:
- `gt7_query/backends/python_backend.py`
- compatibility-only legacy entry shims (`gt7_query/cli.py`, `gt7_query/queries.py`, `gt7_scraper/cli.py`, `gt7_scraper/scraper.py`)
- legacy engine bridge shims under `gt7_scraper/engine/*` for catalog/downloader/playwright/spec

For debugging, use `--include-full-python-backends` when building package.

## Manual Packaging (Local)
Prerequisites:
- Python 3.13+
- Go
- Rust/Cargo
- .NET 8 SDK
- Node 20+ (required for `full`)

### Lite
```bash
python scripts/release/build_release.py \
  --flavor lite \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### Full
```bash
python scripts/release/build_release.py \
  --flavor full \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### One-command matrix build (manual)
```bash
TAG=vX.Y.Z
for PLATFORM in darwin-arm64 darwin-x64 linux-x64 linux-arm64 win-x64 win-arm64; do
  python scripts/release/build_release.py \
    --flavor lite \
    --platform "${PLATFORM}" \
    --version "${TAG}" \
    --out-dir ./dist/release
  python scripts/release/build_release.py \
    --flavor full \
    --platform "${PLATFORM}" \
    --version "${TAG}" \
    --out-dir ./dist/release
done
```

### Smoke Check
```bash
python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_LITE_macOS_ARM64
```

## CI/CD Release Flow
Workflow file: `.github/workflows/release-packages.yml`

Triggers:
- Push tag: `v*`
- Manual dispatch with `tag` input

Pipeline:
1. Matrix build (`platform x flavor`) produces package archives.
2. Run smoke checks per artifact:
   - release defaults are active
   - `query-fallback=off` is enforced
3. Upload artifacts.
4. Publish GitHub Release and upload all artifacts + top-level checksums.

## Troubleshooting
- Missing native backend in package:
  - Run `bin/gt7db doctor --json`.
  - Check `runtime/native` and `manifest.json`.
- Worker startup failure:
  - Verify packaged Python exists under `runtime/python`.
  - Verify `runtime/python/worker` has `gt7_scraper`, `gt7_query`, and `scripts/build_dbs.py`.
- Platform mismatch:
  - Confirm package platform suffix matches host architecture.
  - Rebuild with correct `--platform`.
- Full package Playwright issues:
  - Check `runtime/playwright/browsers` exists.
  - Confirm `gt7db doctor --json` and runtime logs resolve `gt7-playwright` path.
