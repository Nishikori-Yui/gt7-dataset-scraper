# Runtime Refactor Mapping

This document tracks the business-first runtime layout migration.

## gt7_scraper

- `gt7_scraper/engine/*` -> `gt7_scraper/backends/*`
- `gt7_scraper/scrape/*` -> `gt7_scraper/domain/*` + `gt7_scraper/infra/*`
- `gt7_scraper/scraper_run.py` -> `gt7_scraper/app/scrape_runner.py`
- `gt7_scraper/build/runner.py` -> `gt7_scraper/app/build_runner.py`
- `gt7_scraper/db.py` facade -> `gt7_scraper/compat/db.py`
- `gt7_scraper/scraper.py` facade -> `gt7_scraper/compat/scraper.py`

## gt7_query

- `gt7_query/cli.py` -> `gt7_query/app/query_cli.py`
- `gt7_query/query_*.py` -> `gt7_query/domain/*_service.py` + `gt7_query/infra/db.py`
- Go backend invocation from `gt7_query/cli.py` -> `gt7_query/backends/go_backend.py`
- Python backend invocation from `gt7_query/query_*.py` -> `gt7_query/backends/python_backend.py`
- `gt7_query/queries.py` facade -> `gt7_query/compat/queries.py`

## constraints

- Keep top-level `engines/*` unchanged.
- Preserve current CLI behavior.
- Preserve compatibility import paths during migration.
