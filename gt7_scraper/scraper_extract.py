"""Extraction-focused compatibility exports.

This module keeps stable imports while extraction logic is hosted in `scraper_run.py`.
"""

from .compat._warnings import warn_compat

warn_compat("gt7_scraper.scraper_extract", "gt7_scraper.domain.catalog + gt7_scraper.domain.images")

from .scraper_run import (  # noqa: F401
    extract_chunk_name,
    extract_detail_with_node,
    extract_detail_with_playwright,
    extract_detail_with_playwright_on_page,
    extract_exported_literal,
    extract_hero_module_files,
    extract_hero_urls_from_module_js,
    extract_index_js_url,
    extract_list_thumbs_with_node,
    extract_list_thumbs_with_playwright,
    extract_site_total_count,
    parse_car_data,
    parse_descriptions,
    parse_detail_html,
    parse_id_list,
    parse_list_html_for_thumbs,
    parse_tuner_data,
    resolve_hero_urls_from_asset_modules,
)
