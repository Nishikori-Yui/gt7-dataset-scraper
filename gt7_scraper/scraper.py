"""Compatibility exports for scraper modules.

The implementation lives in `app/scrape_runner.py`.
"""

from .compat._warnings import warn_compat

warn_compat("gt7_scraper.scraper", "gt7_scraper.app.scrape_runner")

from .app.scrape_runner import run_scraper  # noqa: F401
from .domain.catalog.parsing import (  # noqa: F401
    build_session,
    extract_site_total_count,
    fetch_text,
    resolve_locales,
)
from .scrape.constants import BASE_URL  # noqa: F401
