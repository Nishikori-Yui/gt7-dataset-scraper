import sqlite3
import sys
import re
from pathlib import Path
from threading import Lock, local as thread_local
from typing import Any, Callable, Dict, List, Optional

from . import db
from .engine.catalog_go import parse_detail_with_go, resolve_catalog_binary
from .engine.downloader import resolve_downloader_binary
from .engine.playwright_node import (
    extract_detail_with_node,
    extract_list_thumbs_with_node,
    resolve_node_playwright_script,
)
from .engine.spec_rust import resolve_rust_spec_binary
from .parser import parse_descriptions
from .utils import slugify
from .scrape.catalog_parse import (
    ScraperError,
    build_session,
    extract_chunk_name,
    extract_index_js_url,
    extract_site_total_count,
    extract_specs_from_data,
    fetch_text,
    parse_car_data,
    parse_id_list,
    parse_tuner_data,
    pick_first,
    resolve_asset_url,
    resolve_locales,
)
from .scrape.constants import BASE_URL
from .scrape.detail_fetch import (
    PlaywrightPool,
    extract_list_thumbs_with_playwright,
    parse_detail_html,
    resolve_hero_urls_from_asset_modules,
)
from .scrape.executor import run_car_processing
from .scrape.normalize import (
    build_tc_sc_label,
    load_country_i18n_map,
    load_country_iso_map,
    load_spec_label_map,
    parse_car_list,
)

def run_scraper(
    locale: str,
    db_path: Path,
    image_dir: Path,
    limit: int,
    resume: bool,
    use_playwright: bool,
    rate: float,
    timeout: int,
    workers: int,
    base_locale: str = "gb",
    playwright_workers: int = 0,
    car_list_path: Optional[Path] = None,
    download_images: bool = True,
    show_progress: bool = True,
    progress_callback: Optional[Callable[[], None]] = None,
    plan_callback: Optional[Callable[[int, Optional[int], str], None]] = None,
    progress_desc: str = "Cars",
    progress_position: int = 0,
    commit_batch: int = 1,
    sqlite_wal: bool = False,
    engines_dir: Optional[Path] = None,
    downloader_engine: str = "python",
    download_workers: int = 32,
    download_timeout: int = 30,
    download_retries: int = 2,
    catalog_engine: str = "python",
    playwright_engine: str = "python",
    spec_engine: str = "python",
) -> int:
    session = build_session()
    path_locale, asset_locale = resolve_locales(locale)
    base_path_locale, _ = resolve_locales(base_locale)
    locale = path_locale
    conn = db.connect_db(db_path)
    db.configure_sqlite(conn, use_wal=sqlite_wal)
    db.init_db(conn, create_images=download_images)
    db.cleanup_descriptions(conn)
    db.cleanup_spec_labels(conn, locale)
    db.cleanup_aspiration_drivetrain(conn, locale)
    db.backfill_manufacturer_country_from_raw_json(conn)
    go_downloader_bin: Optional[str] = None
    if download_images and downloader_engine == "go":
        go_downloader_bin = resolve_downloader_binary(engines_dir)
        if go_downloader_bin is None:
            print("warning: gt7-downloader not found; falling back to python downloader", file=sys.stderr)
    node_playwright_script: Optional[str] = None
    if use_playwright and playwright_engine == "node":
        node_playwright_script = resolve_node_playwright_script(engines_dir)
        if node_playwright_script is None:
            print("warning: gt7-playwright not found; falling back to python playwright", file=sys.stderr)
    rust_spec_bin: Optional[str] = None
    go_catalog_bin: Optional[str] = None
    if catalog_engine == "go":
        go_catalog_bin = resolve_catalog_binary(engines_dir)
        if go_catalog_bin is None:
            print("warning: gt7-catalog-go not found; falling back to python catalog parser", file=sys.stderr)
    if spec_engine == "rust":
        rust_spec_bin = resolve_rust_spec_binary(engines_dir)
        if rust_spec_bin is None:
            print("warning: gt7-spec-normalizer not found; falling back to python spec normalization", file=sys.stderr)
    spec_mappings_dir = Path(__file__).resolve().parent / "mappings" / "spec_labels"

    carlist_url = f"{BASE_URL}/{path_locale}/gt7/carlist/"
    html = fetch_text(session, carlist_url, timeout)
    site_total_count = extract_site_total_count(html)

    index_js_url = extract_index_js_url(html)
    index_js = fetch_text(session, index_js_url, timeout)

    car_chunk_name = extract_chunk_name(
        index_js, rf"cars\.{re.escape(asset_locale)}-[A-Za-z0-9_-]+\.js"
    )
    if not car_chunk_name:
        raise ScraperError("Failed to locate car data chunk name")
    car_chunk_url = resolve_asset_url(car_chunk_name)
    car_chunk_js = fetch_text(session, car_chunk_url, timeout)
    car_data = parse_car_data(car_chunk_js)

    tuner_map: Dict[str, str] = {}
    tuner_chunk_name = extract_chunk_name(
        index_js, rf"tuners\.{re.escape(asset_locale)}-[A-Za-z0-9_-]+\.js"
    )
    if tuner_chunk_name:
        tuner_chunk_url = resolve_asset_url(tuner_chunk_name)
        tuner_chunk_js = fetch_text(session, tuner_chunk_url, timeout)
        tuners = parse_tuner_data(tuner_chunk_js)
        for key, val in tuners.items():
            if isinstance(val, dict) and "name" in val:
                tuner_map[key] = str(val["name"])

    id_list = None
    id_list_name = extract_chunk_name(
        index_js, rf"cars-id-list\.{re.escape(asset_locale)}-[A-Za-z0-9_-]+\.js"
    )
    if id_list_name:
        id_list_url = resolve_asset_url(id_list_name)
        id_list_js = fetch_text(session, id_list_url, timeout)
        id_list = parse_id_list(id_list_js)

    car_ids: List[str] = []
    thumb_map: Dict[str, List[str]] = {}

    if id_list:
        if id_list and isinstance(id_list[0], dict):
            for item in id_list:
                car_id = item.get("id") or item.get("carId") or item.get("car_id")
                if car_id:
                    car_ids.append(str(car_id))
                    images = split_images(item)
                    if images["thumbs"]:
                        thumb_map[str(car_id)] = images["thumbs"]
        else:
            car_ids = [str(x) for x in id_list]

    if not car_ids:
        car_ids = list(car_data.keys())

    description_map: Dict[str, Dict[str, Any]] = {}
    desc_chunk_name = extract_chunk_name(
        index_js, rf"descriptions\.{re.escape(asset_locale)}-[A-Za-z0-9_-]+\.js"
    )
    should_parse_descriptions = not use_playwright
    if desc_chunk_name and should_parse_descriptions:
        try:
            desc_chunk_url = resolve_asset_url(desc_chunk_name)
            desc_chunk_js = fetch_text(session, desc_chunk_url, timeout)
            parsed_desc = parse_descriptions(desc_chunk_js)
            if isinstance(parsed_desc, dict):
                description_map = {str(k): v for k, v in parsed_desc.items()}
        except Exception:
            description_map = {}

    if use_playwright:
        pw_thumbs: Dict[str, List[str]] = {}
        if node_playwright_script is not None:
            try:
                pw_thumbs = extract_list_thumbs_with_node(
                    script=node_playwright_script,
                    locale=path_locale,
                    timeout=timeout,
                    workers=max(1, playwright_workers or workers or 1),
                )
            except Exception:
                pw_thumbs = {}
            if not pw_thumbs:
                pw_thumbs = extract_list_thumbs_with_playwright(path_locale, timeout=timeout)
        else:
            pw_thumbs = extract_list_thumbs_with_playwright(path_locale, timeout=timeout)
        for key, urls in pw_thumbs.items():
            if urls:
                thumb_map.setdefault(key, []).extend(urls)

    if id_list is not None:
        site_total_count = len(id_list)

    if site_total_count is not None:
        db.set_meta(conn, "site_total_count", str(site_total_count))

    # Seed spec label i18n from mapping file to avoid English-only labels
    seeded_codes: set[str] = set()
    label_map = load_spec_label_map(locale)
    if label_map:
        for label, code in label_map.items():
            if code in seeded_codes:
                continue
            db.set_spec_label(conn, code, locale, label)
            seeded_codes.add(code)

    country_iso_map = load_country_iso_map()
    if country_iso_map:
        db.replace_country_iso_map(conn, country_iso_map)
    country_i18n_map = load_country_i18n_map()
    if country_i18n_map:
        for iso3, locales in list(country_i18n_map.items()):
            if locale not in locales and "gb" in locales:
                locales[locale] = locales["gb"]
        db.replace_country_i18n(conn, country_i18n_map)

    if limit > 0:
        car_ids = car_ids[:limit]
    if car_list_path:
        list_ids = parse_car_list(car_list_path)
        if list_ids:
            car_ids = list_ids
            if limit > 0:
                car_ids = car_ids[:limit]

    session_local = thread_local()
    pw_local = thread_local()
    pw_contexts: List[Dict[str, Any]] = []
    pw_lock = Lock()
    pw_pool: Optional[PlaywrightPool] = None
    if use_playwright and node_playwright_script is None and playwright_workers > 0:
        pw_pool = PlaywrightPool(path_locale, timeout, playwright_workers)

    def get_session():
        if not hasattr(session_local, "session"):
            session_local.session = build_session()
        return session_local.session

    catalog_warning = {"shown": False}

    def parse_detail_payload(detail_html: str, car_id: str) -> Dict[str, Any]:
        if go_catalog_bin:
            try:
                return parse_detail_with_go(go_catalog_bin, detail_html, car_id)
            except Exception as exc:
                if not catalog_warning["shown"]:
                    print(f"warning: gt7-catalog-go failed ({exc}); using python parser", file=sys.stderr)
                    catalog_warning["shown"] = True
        return parse_detail_html(detail_html, car_id)

    def get_playwright_page():
        if hasattr(pw_local, "page"):
            return pw_local.page
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
        page = browser.new_page()
        pw_local.pw = pw
        pw_local.browser = browser
        pw_local.page = page
        with pw_lock:
            pw_contexts.append({"pw": pw, "browser": browser, "page": page})
        return page

    # Filter cars to process
    if resume:
        car_ids = [cid for cid in car_ids if db.latest_status(conn, cid, locale) != "success"]
    if plan_callback:
        try:
            plan_callback(len(car_ids), site_total_count, locale)
        except Exception:
            pass

    run_car_processing(
        conn,
        car_ids,
        {
            "car_data": car_data,
            "tuner_map": tuner_map,
            "thumb_map": thumb_map,
            "description_map": description_map,
            "index_js": index_js,
            "timeout": timeout,
            "path_locale": path_locale,
            "base_path_locale": base_path_locale,
            "locale": locale,
            "download_images": download_images,
            "go_downloader_bin": go_downloader_bin,
            "node_playwright_script": node_playwright_script,
            "playwright_workers": playwright_workers,
            "workers": workers,
            "pw_pool": pw_pool,
            "get_playwright_page": get_playwright_page,
            "get_session": get_session,
            "image_dir": image_dir,
            "download_workers": download_workers,
            "download_timeout": download_timeout,
            "download_retries": download_retries,
            "extract_specs_from_data": extract_specs_from_data,
            "pick_first": pick_first,
            "slugify": slugify,
            "resolve_hero_urls_from_asset_modules": resolve_hero_urls_from_asset_modules,
            "fetch_text": fetch_text,
            "parse_detail_payload": parse_detail_payload,
            "extract_detail_with_node": extract_detail_with_node,
            "use_playwright": use_playwright,
            "rust_spec_bin": rust_spec_bin,
            "spec_mappings_dir": spec_mappings_dir,
            "seeded_codes": seeded_codes,
            "show_progress": show_progress,
            "progress_desc": progress_desc,
            "progress_position": progress_position,
            "progress_callback": progress_callback,
            "rate": rate,
            "commit_batch": commit_batch,
        },
    )

    # ensure TC+SC label uses TC/SC i18n if available
    existing_tc_sc = db.get_aspiration_label(conn, "TC+SC", locale)
    combined_tc_sc = build_tc_sc_label(conn, locale)
    if combined_tc_sc and (existing_tc_sc is None or existing_tc_sc in {"TC+SC", "TC + SC"}):
        db.upsert_aspiration(conn, "TC+SC", locale, combined_tc_sc, default_name="TC+SC")

    # sync manufacturers to base locale if available
    db.sync_manufacturers_from_i18n(conn, base_path_locale)

    scraped_count = db.count_cars(conn)
    db.set_meta(conn, "scraped_total_count", str(scraped_count))

    # Close playwright contexts (if any)
    if pw_pool is not None:
        pw_pool.close()
    else:
        for ctx in pw_contexts:
            try:
                ctx["page"].close()
            except Exception:
                pass
            try:
                ctx["browser"].close()
            except Exception:
                pass
            try:
                ctx["pw"].stop()
            except Exception:
                pass

    if (
        limit == 0
        and not car_list_path
        and site_total_count is not None
        and scraped_count != site_total_count
    ):
        db.set_meta(conn, "status", "count_mismatch")
        conn.close()
        return 2

    db.set_meta(conn, "status", "ok")
    conn.close()
    return 0
