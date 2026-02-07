# GT7 Dataset Scraper

[English](README.md) | [简体中文](docs/README.zh-CN.md)

Scrape the Gran Turismo 7 official car list and store results in SQLite with local images.

## IMPORTANT LEGAL RISK NOTICE
- This repository only licenses its own source code; it does not grant rights to third-party site content, assets, trademarks, or brand materials.
- Before running the scraper, review the target website terms and your local laws. If terms disallow this use, do not proceed without permission.
- Do not publish or redistribute scraped datasets, images, logos, or raw payloads.

## Quick Start (Recommended: Prebuilt `gt7db` Release)
1. Download the latest `GT7DB_*_LITE_<OS>_<ARCH>` package from:
   - https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest
2. Extract the archive and run:

```bash
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db doctor --json
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db scrape --locale gb --db ./output/gt7.db --images ./output/images --skip-images
```

On Windows, use `bin\\gt7db.exe`.

## Source Setup (Optional, Development Only)
Use local source setup only when you need to develop or debug the repository itself.

### Pure Python environment
```bash
./scripts/bootstrap_python_env.sh
```

Optional Playwright:
```bash
./scripts/bootstrap_python_env.sh --with-playwright-browser
```

Common options:
- `--with-playwright`: install Playwright Python package only
- `--with-playwright-browser`: install package and Chromium browser
- `--python-bin PATH`: choose a specific Python executable

### Hybrid development environment
```bash
./scripts/bootstrap_hybrid_env.sh
```

Common options:
- `--no-system-install`: only set up `.venv` and build local engines
- `--skip-playwright-browser`: skip Chromium download for Playwright
- `--skip-build`: only install/check toolchain and Python dependencies
- `--skip-dotnet-build`: skip building local `gt7db` launcher

Manual setup details are in [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md). Pure Python usage is in [docs/DATASET_GENERATION.md](docs/DATASET_GENERATION.md).

## Manual Packaging (Optional)
Build local redistributable bundles only when prebuilt releases are not sufficient:
```bash
./scripts/package_gt7db.sh --flavor lite
```

Optional debug package:
```bash
./scripts/package_gt7db.sh --flavor full
```

Common options:
- `--runtime <rid>`: set runtime id manually (for example `osx-arm64`, `linux-amd64`)
- `--skip-build`: package current local artifacts only
- `--dist-dir <path>`: custom output directory

See [docs/RELEASE_PACKAGING.md](docs/RELEASE_PACKAGING.md) for release-first and manual packaging workflows.

## Recommended Mode
- Use `--engine hybrid` as the default mode for production runs.
- Validated smoke runs show `hybrid_no_pw_rust` is faster than pure Python (`81.417s` vs `150.456s` on the same 10-car sample), while keeping the same data quality baseline.
- Enable Playwright only when browser fallback is explicitly needed, because it is much slower.
- Keep `--engine python` as the minimal-dependency fallback mode.
- See [docs/MODE_MATRIX.md](docs/MODE_MATRIX.md) for measured comparisons and [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md) for dependency setup.
- This repository is also a learning/experiment codebase: pure Python is possible, but selected components intentionally use Go/Rust/Node/C++/SQL where they fit better (details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Documentation
- Dataset generation: [docs/DATASET_GENERATION.md](docs/DATASET_GENERATION.md)
- Architecture & data flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Hybrid engine guide: [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md)
- Mode matrix (tested): [docs/MODE_MATRIX.md](docs/MODE_MATRIX.md)
- Release packaging: [docs/RELEASE_PACKAGING.md](docs/RELEASE_PACKAGING.md)
- gt7db usage guide: [docs/GT7DB_USAGE.md](docs/GT7DB_USAGE.md)
- Query CLI/API usage: [docs/QUERY_CLI.md](docs/QUERY_CLI.md)
- Database schema: [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md)
- Legal & publishing: [docs/LEGAL_AND_PUBLISHING.md](docs/LEGAL_AND_PUBLISHING.md)
- Contributing: [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

Chinese translations use the `*.zh-CN.md` suffix in `docs/`.
Hero validation modes for `scripts/build_dbs.py` (`off|soft|strict`) are documented in [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md).

## Output
- SQLite database: `output/gt7.db`
- Images (optional): `output/images/`

## License
Apache-2.0. See `LICENSE`.

## Legal Notice (Short)
This project is provided for educational purposes only. Users are responsible for complying
with website terms and applicable laws. The repository does not include scraped data or
assets. All trademarks and copyrights belong to their respective owners.

See [docs/LEGAL_AND_PUBLISHING.md](docs/LEGAL_AND_PUBLISHING.md) for guidance.
