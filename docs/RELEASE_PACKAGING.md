# Release packages

[简体中文](RELEASE_PACKAGING.zh-CN.md)

Download a package from [GitHub Releases](https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest). Each archive contains the source, guides, `pyproject.toml`, `uv.lock`, and two prebuilt Go tools for its target platform. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run `uv sync --locked` inside the extracted directory on any platform.

Run `uv run --locked bin/gt7db` on macOS/Linux or Windows. The launcher uses the packaged project and its `.venv`. It provides `scrape`, `build-dbs`, `query`, and `doctor`. Both source and release runs detect the optional tools in `local/bin` automatically; Python handles their tasks when unavailable. Merge, validation, and queries use Python and SQLite. uv installs Python and dependencies as needed; browser binaries are installed separately.

Packages are built for macOS arm64/amd64, Linux arm64/amd64, and Windows arm64/amd64. Names follow `GT7DB_<version>_<os>_<ARCH>`.

## Build locally

Use uv and Go 1.23+. Go cross-compiles for the selected target; run the resulting package on that target to verify it:

```sh
uv run --locked python scripts/release/build_release.py \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

Add `--skip-build` to reuse Go binaries already present in `local/bin`. The resulting package directory and archive are written under `dist/release`.

Run the package smoke check on the target platform:

```sh
uv run --locked python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_macOS_ARM64
```

The smoke check uses the dependencies locked in `uv.lock`. It verifies file checksums, launcher paths, command entrypoints, and a SQLite query. The GitHub Actions workflow builds all six targets and publishes archives when a `v*` tag is pushed, or when run manually with a release tag.
