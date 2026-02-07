# Contributing

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

Thank you for contributing. Please keep this repository clean and compliant.

## Rules
- Do not commit any scraped data, images, logos, or databases.
- Do not commit files under `output/`.
- Do not commit any third-party assets or copyrighted content.
- Keep code comments in English.
- Documentation should be written in English, and optional translations may be added under `docs/` (for example `*.zh-CN.md`).

## File Placement Rules
- Runtime orchestration goes to `gt7_scraper/app/` and `gt7_query/app/`.
- Business logic goes to `gt7_scraper/domain/` and `gt7_query/domain/`.
- Backend adapters (python/native bridge) go to `gt7_scraper/backends/` and `gt7_query/backends/`.
- Infrastructure helpers (DB/HTTP/IO) go to `gt7_scraper/infra/` and `gt7_query/infra/`.
- Compatibility-only forwarding modules go to `gt7_scraper/compat/` and `gt7_query/compat/`.
- Native toolchain source stays in top-level `engines/`; do not move it under runtime packages.

## Pull Request Checklist
- [ ] No data or assets included
- [ ] No `output/` files included
- [ ] No `.db` files included
- [ ] Code builds and runs

## Security
- Do not commit API keys or credentials.

## License
- Contributions are licensed under the project LICENSE (Apache-2.0).
