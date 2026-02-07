from ..compat._warnings import warn_compat

warn_compat("gt7_scraper.engine.playwright_node", "gt7_scraper.backends.playwright.node_pw")

from ..backends.playwright.node_pw import (  # noqa: F401
    extract_detail_with_node,
    extract_list_thumbs_with_node,
    resolve_node_playwright_script,
)
