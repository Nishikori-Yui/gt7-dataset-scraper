from ..compat._warnings import warn_compat

warn_compat("gt7_scraper.engine.downloader", "gt7_scraper.backends.images.go_downloader")

from ..backends.images.go_downloader import (  # noqa: F401
    resolve_downloader_binary,
    run_downloader_jobs,
)
