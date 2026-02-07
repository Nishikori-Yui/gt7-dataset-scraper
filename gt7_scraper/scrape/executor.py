import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List

from tqdm import tqdm

from .. import db
from ..engine.spec_rust import normalize_codes_with_rust, normalize_specs_with_rust
from ..parser import json_dumps, map_spec_label, normalize_specs as normalize_specs_py
from .constants import BASE_URL
from .detail_fetch import extract_detail_with_playwright, extract_detail_with_playwright_on_page
from .image_ops import (
    build_assets_with_go_downloader,
    build_car_images,
    build_logo,
    merge_image_rows_preserve_non_regression,
    split_images,
)
from .normalize import (
    build_tc_sc_label,
    derive_year_from_name,
    extract_aspiration_label,
    normalize_aspiration_code,
    normalize_drivetrain_code,
)


def process_car(car_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    car = ctx["car_data"].get(car_id, {})
    images = split_images(car)
    manufacturer_id = car.get("manufacturerId")
    manufacturer_name = None
    if manufacturer_id and manufacturer_id in ctx["tuner_map"]:
        manufacturer_name = ctx["tuner_map"].get(manufacturer_id)
    if not manufacturer_name:
        manufacturer_name = ctx["pick_first"](
            car,
            [
                "maker",
                "makerName",
                "manufacturer",
                "manufacturerName",
                "brand",
                "brandName",
            ],
        )
    car_name = ctx["pick_first"](car, ["nameShort", "name", "carName", "model"]) or car_id
    if not car_name:
        car_name = ctx["pick_first"](car, ["nameLong", "carNameLong"]) or car_id
    year = ctx["pick_first"](car, ["year", "productionYear"])
    if not year:
        name_long = ctx["pick_first"](car, ["nameLong", "carNameLong"])
        year = derive_year_from_name(name_long or car_name)
    country_id = car.get("countryId")
    aspiration_raw = ctx["pick_first"](car, ["aspirationLong", "aspiration"])
    aspiration_code = ctx["pick_first"](car, ["aspirationShort"])
    drivetrain_code = normalize_drivetrain_code(ctx["pick_first"](car, ["driveTrain"]), ctx["locale"])
    intro = None
    detail = None
    car_class = ctx["pick_first"](car, ["carClass", "class"])
    pp = ctx["pick_first"](car, ["pp", "performance", "performancePoint"])
    logo_url = images["logos"][0] if images["logos"] else None
    if manufacturer_id and not logo_url:
        logo_url = f"/common/dist/gt7/carlist/tuner_logos/light/{manufacturer_id}.png"
    specs = ctx["extract_specs_from_data"](car)
    hero_urls = images["heroes"]
    thumb_urls = ctx["thumb_map"].get(car_id) or images["thumbs"]
    desc_item = ctx["description_map"].get(car_id)
    if isinstance(desc_item, dict):
        intro = desc_item.get("hero") or intro
        detail = desc_item.get("desc") or detail
    if ctx["download_images"] and len(hero_urls) <= 1:
        try:
            hero_from_assets = ctx["resolve_hero_urls_from_asset_modules"](
                session=ctx["get_session"](),
                index_js=ctx["index_js"],
                car_id=car_id,
                timeout=ctx["timeout"],
            )
        except Exception:
            hero_from_assets = []
        if hero_from_assets:
            hero_urls = hero_from_assets
    need_detail_fetch = (
        ctx["download_images"] or not intro or not detail or not specs or len(hero_urls) <= 1
    )
    if need_detail_fetch:
        try:
            detail_url = f"{BASE_URL}/{ctx['path_locale']}/gt7/carlist/id/{car_id}"
            detail_html = ctx["fetch_text"](ctx["get_session"](), detail_url, ctx["timeout"])
            detail_data = ctx["parse_detail_payload"](detail_html, car_id)
        except Exception:
            detail_data = {}
        if detail_data:
            car_name = detail_data.get("name") or car_name
            manufacturer_name = detail_data.get("manufacturer_name") or manufacturer_name
            intro = intro or detail_data.get("intro")
            detail = detail or detail_data.get("detail")
            if detail_data.get("specs"):
                specs = detail_data.get("specs")
            detail_heroes = detail_data.get("hero_images") or []
            if len(detail_heroes) > len(hero_urls):
                hero_urls = detail_heroes
    if ctx["use_playwright"]:
        try:
            detail_data: Dict[str, Any] = {}
            if ctx["node_playwright_script"] is not None:
                try:
                    detail_data = ctx["extract_detail_with_node"](
                        script=ctx["node_playwright_script"],
                        car_id=car_id,
                        locale=ctx["path_locale"],
                        timeout=ctx["timeout"],
                        workers=max(1, ctx["playwright_workers"] or ctx["workers"] or 1),
                    )
                except Exception:
                    detail_data = {}
                node_heroes = detail_data.get("hero_images") if isinstance(detail_data, dict) else None
                node_hero_count = len(node_heroes) if isinstance(node_heroes, list) else 0
                node_low_quality = (not detail_data) or (not detail_data.get("detail")) or (node_hero_count <= 1)
                if node_low_quality:
                    try:
                        if ctx["pw_pool"] is not None:
                            fallback_detail = ctx["pw_pool"].fetch(car_id)
                        else:
                            page = ctx["get_playwright_page"]()
                            if page is not None:
                                fallback_detail = extract_detail_with_playwright_on_page(
                                    page, car_id, ctx["path_locale"], ctx["timeout"]
                                )
                            else:
                                fallback_detail = extract_detail_with_playwright(
                                    car_id, ctx["path_locale"], ctx["timeout"]
                                )
                    except Exception:
                        fallback_detail = {}
                    if fallback_detail:
                        for key in ["name", "manufacturer_name", "intro", "detail", "specs"]:
                            value = fallback_detail.get(key)
                            if value and not detail_data.get(key):
                                detail_data[key] = value
                        fb_heroes = fallback_detail.get("hero_images")
                        if isinstance(fb_heroes, list) and len(fb_heroes) > node_hero_count:
                            detail_data["hero_images"] = fb_heroes
                        fb_thumbs = fallback_detail.get("thumb_images")
                        if isinstance(fb_thumbs, list) and fb_thumbs:
                            detail_data["thumb_images"] = fb_thumbs
            elif ctx["pw_pool"] is not None:
                detail_data = ctx["pw_pool"].fetch(car_id)
            else:
                page = ctx["get_playwright_page"]()
                if page is not None:
                    detail_data = extract_detail_with_playwright_on_page(
                        page, car_id, ctx["path_locale"], ctx["timeout"]
                    )
                else:
                    detail_data = extract_detail_with_playwright(car_id, ctx["path_locale"], ctx["timeout"])
        except Exception:
            detail_data = {}
        if detail_data:
            car_name = detail_data.get("name") or car_name
            manufacturer_name = detail_data.get("manufacturer_name") or manufacturer_name
            intro = intro or detail_data.get("intro")
            detail = detail or detail_data.get("detail")
            if detail_data.get("specs"):
                specs = detail_data.get("specs")
            detail_heroes = detail_data.get("hero_images") or []
            if len(detail_heroes) > len(hero_urls):
                hero_urls = detail_heroes
    hero_urls = [u for u in hero_urls if u and not u.startswith("data:")]
    thumb_urls = [u for u in thumb_urls if u and not u.startswith("data:")]
    if not thumb_urls:
        thumb_urls = [f"/common/dist/gt7/carlist/car_thumbnails/{car_id}.png"]
    if not hero_urls:
        hero_urls = [f"/common/dist/gt7/carlist/og_images/{car_id}_1_01.jpg"]
    if not manufacturer_name:
        manufacturer_name = "Unknown"
    if not manufacturer_id:
        manufacturer_id = ctx["slugify"](manufacturer_name)
    aspiration_code = normalize_aspiration_code(aspiration_code or aspiration_raw, ctx["locale"])
    aspiration_label = extract_aspiration_label(aspiration_raw)
    logo_path = None
    image_rows: List[Dict[str, str]] = []
    if ctx["download_images"] and ctx["go_downloader_bin"]:
        try:
            logo_path, image_rows = build_assets_with_go_downloader(
                car_id=car_id,
                manufacturer_id=manufacturer_id,
                logo_url=logo_url,
                hero_urls=hero_urls or [],
                thumb_urls=thumb_urls or [],
                image_dir=ctx["image_dir"],
                go_binary=ctx["go_downloader_bin"],
                workers=ctx["download_workers"],
                timeout=ctx["download_timeout"],
                retries=ctx["download_retries"],
            )
        except Exception:
            session = ctx["get_session"]()
            logo_path = build_logo(manufacturer_id, logo_url, ctx["image_dir"], session, ctx["timeout"])
            image_rows = build_car_images(
                car_id, ctx["image_dir"], hero_urls or [], thumb_urls or [], session, ctx["timeout"]
            )
    elif ctx["download_images"]:
        session = ctx["get_session"]()
        logo_path = build_logo(manufacturer_id, logo_url, ctx["image_dir"], session, ctx["timeout"])
        image_rows = build_car_images(
            car_id, ctx["image_dir"], hero_urls or [], thumb_urls or [], session, ctx["timeout"]
        )
    spec_pairs: List[Any] = []
    if isinstance(specs, list):
        for item in specs:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                spec_pairs.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict) and "spec_key" in item and "spec_raw" in item:
                spec_pairs.append((str(item["spec_key"]), str(item["spec_raw"])))
    elif isinstance(specs, dict):
        spec_pairs.extend([(str(k), str(v)) for k, v in specs.items()])
    filtered_pairs: List[Any] = []
    drivetrain_label = None
    for label, raw_value in spec_pairs:
        spec_code, _, _ = map_spec_label(label, ctx["locale"], raw_value)
        if spec_code == "drivetrain":
            drivetrain_label = str(raw_value).strip()
            if not drivetrain_code:
                drivetrain_code = normalize_drivetrain_code(drivetrain_label, ctx["locale"])
            continue
        if spec_code == "aspiration":
            if not aspiration_raw:
                aspiration_raw = str(raw_value).strip()
            if not aspiration_code:
                aspiration_code = normalize_aspiration_code(aspiration_raw, ctx["locale"])
            continue
        filtered_pairs.append((label, raw_value))
    spec_pairs = filtered_pairs
    if ctx["rust_spec_bin"] is not None:
        try:
            normalized_codes = normalize_codes_with_rust(
                binary=ctx["rust_spec_bin"],
                locale=ctx["locale"],
                aspiration=aspiration_raw,
                aspiration_short=aspiration_code,
                drivetrain=drivetrain_label or ctx["pick_first"](car, ["driveTrain"]),
            )
            aspiration_code = normalized_codes.get("aspiration_code") or aspiration_code
            aspiration_label = normalized_codes.get("aspiration_label") or aspiration_label
            drivetrain_code = normalized_codes.get("drivetrain_code") or drivetrain_code
            drivetrain_label = normalized_codes.get("drivetrain_label") or drivetrain_label
        except Exception:
            pass
    return {
        "car_id": car_id,
        "manufacturer": {
            "id": manufacturer_id,
            "name": manufacturer_name,
            "logo_path": logo_path,
            "country_id": country_id if ctx["locale"] == ctx["base_path_locale"] else None,
        },
        "car": {
            "id": car_id,
            "name": car_name,
            "manufacturer_id": manufacturer_id,
            "aspiration_code": aspiration_code,
            "drivetrain_code": drivetrain_code,
            "intro": intro,
            "detail": detail,
            "car_class": car_class,
            "pp": pp,
            "year": year,
            "raw_json": json_dumps(car),
        },
        "text": {
            "car_id": car_id,
            "locale": ctx["locale"],
            "name": car_name,
            "intro": intro,
            "detail": detail,
        },
        "aspiration": {"code": aspiration_code, "label": aspiration_label or aspiration_raw},
        "drivetrain": {"code": drivetrain_code, "label": drivetrain_label},
        "spec_pairs": spec_pairs,
        "images": image_rows,
    }


def run_car_processing(
    conn: sqlite3.Connection,
    car_ids: List[str],
    ctx: Dict[str, Any],
) -> None:
    executor_workers = max(1, int(ctx["workers"] or 1))
    effective_commit_batch = max(1, int(ctx["commit_batch"] or 1))
    pending_writes = 0
    futures = []
    with ThreadPoolExecutor(max_workers=executor_workers) as executor:
        for car_id in car_ids:
            futures.append(executor.submit(process_car, car_id, ctx))
        progress_bar = None
        if ctx["show_progress"]:
            progress_bar = tqdm(
                total=len(futures),
                desc=ctx["progress_desc"],
                position=ctx["progress_position"],
                leave=True,
            )
        for future in as_completed(futures):
            car_id = None
            try:
                result = future.result()
                car_id = result["car_id"]
                db.upsert_manufacturer(conn, result["manufacturer"], update_name=(ctx["locale"] == ctx["base_path_locale"]))
                if result["manufacturer"].get("name"):
                    db.upsert_manufacturer_i18n(
                        conn, result["manufacturer"]["id"], ctx["locale"], result["manufacturer"]["name"]
                    )
                db.upsert_car(conn, result["car"], update_texts=(ctx["locale"] == ctx["base_path_locale"]))
                db.upsert_car_text(conn, result["text"])
                if result.get("aspiration") and result["aspiration"].get("code"):
                    code = result["aspiration"]["code"]
                    label = result["aspiration"].get("label") or code
                    if code == "TC+SC":
                        combined = build_tc_sc_label(conn, ctx["locale"])
                        if combined:
                            label = combined
                    db.upsert_aspiration(conn, code, ctx["locale"], label, default_name=code)
                if result.get("drivetrain") and result["drivetrain"].get("code"):
                    code = result["drivetrain"]["code"]
                    label = result["drivetrain"].get("label") or code
                    db.upsert_drivetrain(conn, code, ctx["locale"], label, default_name=code)
                if ctx["rust_spec_bin"] is not None:
                    try:
                        spec_rows = normalize_specs_with_rust(
                            binary=ctx["rust_spec_bin"],
                            specs=result["spec_pairs"],
                            locale=ctx["locale"],
                            mappings_dir=ctx["spec_mappings_dir"],
                        )
                    except Exception:
                        spec_rows = normalize_specs_py(result["spec_pairs"], locale=ctx["locale"])
                else:
                    spec_rows = normalize_specs_py(result["spec_pairs"], locale=ctx["locale"])
                db.replace_specs(conn, car_id, spec_rows)
                for spec in spec_rows:
                    if spec.get("spec_key") and spec.get("spec_label"):
                        if spec["spec_key"].startswith("raw_"):
                            continue
                        if spec["spec_key"] not in ctx["seeded_codes"]:
                            db.upsert_spec_label(conn, spec["spec_key"], ctx["locale"], spec["spec_label"])
                if ctx["download_images"]:
                    image_rows = result["images"]
                    if ctx["locale"] != ctx["base_path_locale"]:
                        existing_rows = db.get_car_images(conn, car_id)
                        image_rows = merge_image_rows_preserve_non_regression(existing_rows, image_rows)
                    db.replace_images(conn, car_id, image_rows)
                db.log_fetch(conn, car_id, ctx["locale"], "success", "", datetime.utcnow().isoformat())
            except Exception as exc:
                if car_id is None:
                    car_id = "unknown"
                db.log_fetch(conn, car_id, ctx["locale"], "failed", str(exc), datetime.utcnow().isoformat())
            finally:
                pending_writes += 1
                if pending_writes >= effective_commit_batch:
                    conn.commit()
                    pending_writes = 0
                if ctx["show_progress"] and progress_bar:
                    progress_bar.update(1)
                if ctx["progress_callback"]:
                    ctx["progress_callback"]()
            if ctx["rate"] > 0:
                time.sleep(ctx["rate"])
        if ctx["show_progress"] and progress_bar:
            progress_bar.close()
    if pending_writes > 0:
        conn.commit()
