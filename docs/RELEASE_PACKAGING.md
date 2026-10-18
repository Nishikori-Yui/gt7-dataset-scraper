# Release packages

[简体中文](RELEASE_PACKAGING.zh-CN.md)

Download a package from [GitHub Releases](https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest). Each archive contains the source, guides, requirements, and two prebuilt Go tools for its target platform. Install Python 3.10+ locally, then run `./scripts/bootstrap.sh` inside the extracted directory. On Windows, run `python -m venv .venv` and `.venv\Scripts\python -m pip install -r requirements.txt`.

Run `bin/gt7db` on macOS/Linux or `bin/gt7db.cmd` on Windows. The launcher uses `.venv` when present, otherwise Python from `PATH` (overridable with `PYTHON_BIN`). It provides `scrape`, `build-dbs`, `query`, and `doctor`. Both source and release runs detect the optional tools in `local/bin` automatically; Python handles their tasks when unavailable. Merge, validation, and queries use Python and SQLite. Python runtimes, installed dependencies, and browsers are installed separately.

Packages are built for macOS arm64/amd64, Linux arm64/amd64, and Windows arm64/amd64. Names follow `GT7DB_<version>_<os>_<ARCH>`.

## Build locally

Use Python 3.10+ and Go 1.23+. Go cross-compiles for the selected target; run the resulting package on that target to verify it:

```sh
python scripts/release/build_release.py \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

Add `--skip-build` to reuse Go binaries already present in `local/bin`. The resulting package directory and archive are written under `dist/release`.

Run the package smoke check on the target platform:

```sh
python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_macOS_ARM64
```

The smoke check requires the Python dependencies in `requirements.txt`. It verifies file checksums, launcher paths, command entrypoints, and a SQLite query. The GitHub Actions workflow builds all six targets and publishes archives when a `v*` tag is pushed, or when run manually with a release tag.
