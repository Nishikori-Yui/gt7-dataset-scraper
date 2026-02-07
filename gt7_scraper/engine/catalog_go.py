from ..compat._warnings import warn_compat

warn_compat("gt7_scraper.engine.catalog_go", "gt7_scraper.backends.catalog.go_parser")

from ..backends.catalog.go_parser import (  # noqa: F401
    parse_chunk_with_go,
    parse_detail_with_go,
    parse_list_thumbs_with_go,
    resolve_catalog_binary,
)
