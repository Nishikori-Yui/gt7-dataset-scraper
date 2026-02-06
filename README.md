# GT7 Dataset Scraper

[English](README.md) | [简体中文](docs/README.zh-CN.md)

Scrape the Gran Turismo 7 official car list and store results in SQLite with local images.

## Quick Start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m gt7_scraper --locale gb --db ./output/gt7.db --images ./output/images
```

## Documentation
- Dataset generation: `docs/DATASET_GENERATION.md`
- Architecture & data flow: `docs/ARCHITECTURE.md`
- Query CLI/API usage: `docs/QUERY_CLI.md`
- Database schema: `docs/DB_SCHEMA.md`
- Legal & publishing: `docs/LEGAL_AND_PUBLISHING.md`
- Contributing: `docs/CONTRIBUTING.md`

Chinese translations use the `*.zh-CN.md` suffix in `docs/`.

## Output
- SQLite database: `output/gt7.db`
- Images (optional): `output/images/`

## License
Apache-2.0. See `LICENSE`.

## Legal Notice (Short)
This project is provided for educational purposes only. Users are responsible for complying
with website terms and applicable laws. The repository does not include scraped data or
assets. All trademarks and copyrights belong to their respective owners.

See `docs/LEGAL_AND_PUBLISHING.md` for guidance.
