"""Asset-focused compatibility exports.

This module keeps stable imports while asset logic is hosted in `scraper_run.py`.
"""

from .compat._warnings import warn_compat

warn_compat("gt7_scraper.scraper_assets", "gt7_scraper.domain.images.assets")

from .scraper_run import (  # noqa: F401
    build_assets_with_go_downloader,
    build_car_images,
    build_logo,
    merge_image_rows_preserve_non_regression,
)
