import json
import re
import time
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local as thread_local
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from . import db
from .parser import (
    extract_exported_literal,
    find_largest_array,
    find_largest_object,
    json_dumps,
    map_spec_label,
    normalize_specs as normalize_specs_py,
    parse_descriptions,
)
from .engine.downloader import resolve_downloader_binary, run_downloader_jobs
from .engine.playwright_node import (
    extract_detail_with_node,
    extract_list_thumbs_with_node,
    resolve_node_playwright_script,
)
from .engine.spec_rust import normalize_specs_with_rust, resolve_rust_spec_binary
from .utils import download_file, looks_like_image_url, slugify

BASE_URL = "https://www.gran-turismo.com"

EXPORT_NAMES = ["CarList", "CarData", "CarCatalog", "CarInfo"]
ID_LIST_EXPORT_NAMES = ["CarIdList", "CarIds"]
TUNER_EXPORT_NAMES = ["TunerList", "Tuners", "TunerData"]

LOCALE_PATH_MAP = {
    "bp": "br",
    "ms": "mx",
    "el": "gr",
    "ar": "sa",
}


def resolve_locales(locale: str) -> Tuple[str, str]:
    # returns (path_locale, asset_locale)
    if locale in {"br", "mx", "gr", "sa"}:
        reverse = {v: k for k, v in LOCALE_PATH_MAP.items()}
        return locale, reverse.get(locale, locale)
    return LOCALE_PATH_MAP.get(locale, locale), locale


class ScraperError(Exception):
    pass


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0.0.0 Safari/537.36",
        }
    )
    return session


def fetch_text(session: requests.Session, url: str, timeout: int) -> str:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def normalize_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url}"


def extract_index_js_url(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        src = script.get("src")
        if not src:
            continue
        if "/common/dist/gt7/carlist/assets/index-" in src:
            return normalize_url(src)
    # fallback regex
    match = re.search(r"(/common/dist/gt7/carlist/assets/index-[^\"']+\.js)", html)
    if match:
        return normalize_url(match.group(1))
    raise ScraperError("Failed to locate index JS bundle")


def extract_site_total_count(html: str) -> Optional[int]:
    # Try to find patterns like "123 Car(s)" or "123 Cars"
    matches = re.findall(r"(\d{1,5})\s*Car", html, flags=re.IGNORECASE)
    if matches:
        return max(int(m) for m in matches)
    return None


def parse_og_description(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        content = og.get("content").strip()
        return content if content else None
    return None


def extract_chunk_name(index_js: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, index_js)
    return match.group(0) if match else None


def resolve_asset_url(name: str) -> str:
    if name.startswith("http://") or name.startswith("https://"):
        return name
    name = name.lstrip("./")
    if name.startswith("/common/"):
        return normalize_url(name)
    return f"{BASE_URL}/common/dist/gt7/carlist/assets/{name}"


def parse_car_data(js_text: str) -> Dict[str, Dict[str, Any]]:
    for export_name in EXPORT_NAMES:
        data = extract_exported_literal(js_text, export_name)
        if isinstance(data, dict):
            return data
    # fallback: largest object literal
    data = find_largest_object(js_text)
    if isinstance(data, dict):
        return data
    raise ScraperError("Failed to parse car data from JS chunk")


def parse_tuner_data(js_text: str) -> Dict[str, Dict[str, Any]]:
    for export_name in TUNER_EXPORT_NAMES:
        data = extract_exported_literal(js_text, export_name)
        if isinstance(data, dict):
            return data
    data = find_largest_object(js_text)
    if isinstance(data, dict):
        return data
    return {}


def parse_id_list(js_text: str) -> Optional[List[Any]]:
    for export_name in ID_LIST_EXPORT_NAMES:
        data = extract_exported_literal(js_text, export_name)
        if isinstance(data, list):
            return data
    data = find_largest_array(js_text)
    if isinstance(data, list):
        return data
    return None


def collect_image_urls(obj: Any) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []

    def walk(value: Any, path: List[str]):
        if isinstance(value, dict):
            for key, val in value.items():
                walk(val, path + [str(key)])
        elif isinstance(value, list):
            for idx, val in enumerate(value):
                walk(val, path + [str(idx)])
        elif isinstance(value, str) and looks_like_image_url(value):
            found.append((".".join(path), value))

    walk(obj, [])
    return found


def split_images(obj: Any) -> Dict[str, List[str]]:
    logos: List[str] = []
    heroes: List[str] = []
    thumbs: List[str] = []

    for keypath, url in collect_image_urls(obj):
        lower = keypath.lower()
        if "logo" in lower:
            logos.append(url)
        elif any(token in lower for token in ["thumb", "list", "card", "small"]):
            thumbs.append(url)
        else:
            heroes.append(url)

    def unique(values: Iterable[str]) -> List[str]:
        seen = set()
        out = []
        for val in values:
            if val in seen:
                continue
            seen.add(val)
            out.append(val)
        return out

    return {
        "logos": unique(logos),
        "heroes": unique(heroes),
        "thumbs": unique(thumbs),
    }


def pick_first(data: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def extract_specs_from_data(car: Dict[str, Any]) -> List[Tuple[str, str]]:
    specs: List[Tuple[str, str]] = []
    if isinstance(car.get("spec"), dict):
        specs.extend([(k, car["spec"][k]) for k in car["spec"].keys()])
    elif isinstance(car.get("specs"), dict):
        specs.extend([(k, car["specs"][k]) for k in car["specs"].keys()])
    elif isinstance(car.get("specs"), list):
        for item in car.get("specs", []):
            if isinstance(item, dict) and "key" in item and "value" in item:
                specs.append((str(item["key"]), str(item["value"])))

    fallback_map = {
        "displacement": "Displacement",
        "driveTrain": "Drivetrain",
        "drivetrain": "Drivetrain",
        "maxPower": "Max Power",
        "maxTorque": "Max Torque",
        "weight": "Weight",
        "aspirationLong": "Aspiration",
        "length": "Length",
        "width": "Width",
        "height": "Height",
    }
    for key, label in fallback_map.items():
        if key in car and car[key] is not None:
            specs.append((label, car[key]))

    seen = set()
    unique_specs = []
    for key, val in specs:
        if key in seen:
            continue
        seen.add(key)
        unique_specs.append((key, val))
    return unique_specs


def build_car_images(
    car_id: str,
    image_dir: Path,
    hero_urls: List[str],
    thumb_urls: List[str],
    session: requests.Session,
    timeout: int,
) -> List[Dict[str, str]]:
    images = []
    for idx, url in enumerate(hero_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        url = normalize_url(url)
        filename = f"{car_id}_hero_{idx:02d}"
        path = image_dir / "cars" / car_id / filename
        try:
            final_path = download_file(url, path, session, timeout)
        except Exception:
            continue
        images.append(
            {
                "image_path": str(final_path.relative_to(image_dir)),
                "sort_order": idx,
                "image_type": "hero",
            }
        )

    for idx, url in enumerate(thumb_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        url = normalize_url(url)
        filename = f"{car_id}_thumb_{idx:02d}"
        path = image_dir / "cars" / car_id / filename
        try:
            final_path = download_file(url, path, session, timeout)
        except Exception:
            continue
        images.append(
            {
                "image_path": str(final_path.relative_to(image_dir)),
                "sort_order": idx,
                "image_type": "thumb",
            }
        )

    return images


def build_logo(
    manufacturer_id: str,
    logo_url: Optional[str],
    image_dir: Path,
    session: requests.Session,
    timeout: int,
) -> Optional[str]:
    if not logo_url:
        return None
    logo_url = normalize_url(logo_url)
    path = image_dir / "manufacturers" / manufacturer_id / "logo"
    try:
        final_path = download_file(logo_url, path, session, timeout)
    except Exception:
        return None
    return str(final_path.relative_to(image_dir))


def build_assets_with_go_downloader(
    car_id: str,
    manufacturer_id: str,
    logo_url: Optional[str],
    hero_urls: List[str],
    thumb_urls: List[str],
    image_dir: Path,
    go_binary: str,
    workers: int,
    timeout: int,
    retries: int,
) -> Tuple[Optional[str], List[Dict[str, str]]]:
    jobs: List[Dict[str, object]] = []
    if logo_url and not logo_url.startswith("data:"):
        jobs.append(
            {
                "job_id": "logo",
                "url": normalize_url(logo_url),
                "dest_rel": f"manufacturers/{manufacturer_id}/logo",
            }
        )
    for idx, url in enumerate(hero_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        jobs.append(
            {
                "job_id": f"hero_{idx}",
                "url": normalize_url(url),
                "dest_rel": f"cars/{car_id}/{car_id}_hero_{idx:02d}",
            }
        )
    for idx, url in enumerate(thumb_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        jobs.append(
            {
                "job_id": f"thumb_{idx}",
                "url": normalize_url(url),
                "dest_rel": f"cars/{car_id}/{car_id}_thumb_{idx:02d}",
            }
        )
    if not jobs:
        return None, []
    results = run_downloader_jobs(
        binary=go_binary,
        image_dir=image_dir,
        jobs=jobs,
        workers=workers,
        timeout=timeout,
        retries=retries,
    )
    logo_path = None
    images: List[Dict[str, str]] = []
    for job in jobs:
        job_id = str(job["job_id"])
        item = results.get(job_id)
        if not item:
            continue
        if item.get("status") not in {"ok", "skipped"}:
            continue
        path_rel = item.get("path_rel")
        if not path_rel:
            continue
        if job_id == "logo":
            logo_path = str(path_rel)
            continue
        if job_id.startswith("hero_"):
            sort_order = int(job_id.split("_", 1)[1])
            images.append(
                {
                    "image_path": str(path_rel),
                    "sort_order": sort_order,
                    "image_type": "hero",
                }
            )
            continue
        if job_id.startswith("thumb_"):
            sort_order = int(job_id.split("_", 1)[1])
            images.append(
                {
                    "image_path": str(path_rel),
                    "sort_order": sort_order,
                    "image_type": "thumb",
                }
            )
    return logo_path, images


def merge_image_rows_preserve_non_regression(
    existing_rows: List[Dict[str, object]],
    new_rows: List[Dict[str, object]],
    protected_types: Optional[Iterable[str]] = None,
) -> List[Dict[str, object]]:
    protected = {str(t).lower() for t in (protected_types or ["hero", "thumb"])}

    def group_by_type(rows: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
        grouped: Dict[str, List[Dict[str, object]]] = {}
        for row in rows:
            image_type = str(row.get("image_type") or "").strip().lower()
            if not image_type:
                image_type = "unknown"
            grouped.setdefault(image_type, []).append(
                {
                    "image_path": str(row.get("image_path") or ""),
                    "sort_order": row.get("sort_order"),
                    "image_type": image_type,
                }
            )
        for values in grouped.values():
            values.sort(key=lambda item: (item.get("sort_order") is None, item.get("sort_order"), item["image_path"]))
        return grouped

    existing_map = group_by_type(existing_rows)
    new_map = group_by_type(new_rows)
    type_order: List[str] = []
    for image_type in ["hero", "thumb"]:
        if image_type in existing_map or image_type in new_map:
            type_order.append(image_type)
    for image_type in list(existing_map.keys()) + list(new_map.keys()):
        if image_type not in type_order:
            type_order.append(image_type)

    merged: List[Dict[str, object]] = []
    for image_type in type_order:
        old_items = existing_map.get(image_type, [])
        new_items = new_map.get(image_type, [])
        if image_type in protected and len(new_items) < len(old_items):
            chosen = old_items
        elif new_items:
            chosen = new_items
        else:
            chosen = old_items
        merged.extend(chosen)
    return merged


def derive_year_from_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    if match:
        return match.group(1)
    match = re.search(r"'(\d{2})\b", name)
    if not match:
        return None
    year_two = int(match.group(1))
    year = 2000 + year_two if year_two <= 29 else 1900 + year_two
    return str(year)


def extract_aspiration_label(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    match = re.search(r"[（(]\s*([^）)]+)\s*[）)]", text)
    if match:
        label = match.group(1).strip()
        return label if label else text
    return text


def normalize_aspiration_code(raw_value: Optional[str], locale: str) -> Optional[str]:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if text == "---":
        return None
    text_clean = text.replace(" ", "").replace("＋", "+").upper()
    if "TC+SC" in text_clean:
        return "TC+SC"
    if text_clean.startswith("TC+SC"):
        return "TC+SC"
    if re.match(r"^TC\\+SC$", text_clean):
        return "TC+SC"
    if re.match(r"^T(\\b|\\+)", text_clean):
        return "TC"
    for code in ["NA", "TC", "SC", "EV", "HV"]:
        if text_clean.startswith(code):
            return code

    lower = text.lower()
    if any(
        k in lower
        for k in [
            "\u81ea\u7136",
            "naturally",
            "n/a",
            "na",
            "atmosf\u00e9r",
            "atmosfer",
            "do\u011fal",
            "dogal",
            "emi\u015fli",
            "\u03b1\u03c4\u03bc\u03bf\u03c3\u03c6\u03b1\u03b9\u03c1",
            "\u0633\u062d\u0628 \u0637\u0628\u064a\u0639\u064a",
            "\u0e44\u0e21\u0e48\u0e43\u0e0a\u0e49\u0e23\u0e30\u0e1a\u0e1a\u0e2d\u0e31\u0e14\u0e2d\u0e32\u0e01\u0e32\u0e28",
        ]
    ):
        return "NA"
    if any(k in lower for k in ["\u6da1\u8f6e", "\u6e26\u8f6e", "turbo", "ターボ", "터보", "турбо"]):
        return "TC"
    if any(
        k in lower
        for k in [
            "\u673a\u68b0",
            "\u6a5f\u68b0",
            "supercharger",
            "スーパーチャージャ",
            "슈퍼차저",
            "kompresor",
            "kompres\u00f6r",
        ]
    ):
        return "SC"
    if any(k in lower for k in ["\u7535", "\u96fb", "electric", "\u96fb\u6c17", "전기"]):
        return "EV"
    return None


def normalize_drivetrain_code(raw_value: Optional[str], locale: str) -> Optional[str]:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if text == "---":
        return None
    upper = text.upper().replace(" ", "")
    for code in ["FR", "FF", "MR", "RR", "4WD", "AWD"]:
        if upper == code:
            return code
    # Chinese localized labels
    cn_map = {
        "\u524d\u7f6e\u540e\u9a71": "FR",
        "\u524d\u7f6e\u524d\u9a71": "FF",
        "\u4e2d\u7f6e\u540e\u9a71": "MR",
        "\u540e\u7f6e\u540e\u9a71": "RR",
        "\u56db\u9a71": "4WD",
    }
    if text in cn_map:
        return cn_map[text]
    return None


def build_tc_sc_label(conn: sqlite3.Connection, locale: str) -> Optional[str]:
    tc = db.get_aspiration_label(conn, "TC", locale)
    sc = db.get_aspiration_label(conn, "SC", locale)
    if tc and sc:
        return f"{tc} + {sc}"
    return None


def load_spec_label_map(locale: str) -> Dict[str, str]:
    path = Path(__file__).resolve().parent / "mappings" / "spec_labels" / f"{locale}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_country_iso_map() -> Dict[str, str]:
    path = Path(__file__).resolve().parent / "mappings" / "country_iso.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_country_i18n_map() -> Dict[str, Dict[str, str]]:
    path = Path(__file__).resolve().parent / "mappings" / "country_i18n.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    cleaned: Dict[str, Dict[str, str]] = {}
    for iso3, locales in data.items():
        if isinstance(locales, dict):
            cleaned[str(iso3)] = {str(k): str(v) for k, v in locales.items()}
    return cleaned


def parse_car_list(path: Path) -> List[str]:
    car_ids: List[str] = []
    if not path.exists():
        return car_ids
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            car_ids.append(value)
    return car_ids


def extract_detail_with_playwright_on_page(
    page: Any, car_id: str, locale: str, timeout: int
) -> Dict[str, Any]:
    url = f"{BASE_URL}/{locale}/gt7/carlist/id/{car_id}"
    data: Dict[str, Any] = {}
    page.set_default_navigation_timeout(timeout * 1000)
    navigated = False
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        navigated = True
    except Exception:
        pass
    if not navigated:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            return {}

    parsed = {}
    max_wait = min(8, max(3, int(timeout)))
    for _ in range(max_wait):
        try:
            page.wait_for_timeout(800)
        except Exception:
            pass
        html = page.content()
        parsed = parse_detail_html(html, car_id)
        hero = parsed.get("hero_images") or []
        if any("/carlist/assets/" in u for u in hero):
            data.update(parsed)
            break

    if not data and parsed:
        data.update(parsed)

    return data


def extract_detail_with_playwright(car_id: str, locale: str, timeout: int) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    data: Dict[str, Any] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        data = extract_detail_with_playwright_on_page(page, car_id, locale, timeout)
        browser.close()
    return data


class PlaywrightPool:
    def __init__(self, locale: str, timeout: int, workers: int) -> None:
        self.locale = locale
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.local = thread_local()
        self.contexts: List[Dict[str, Any]] = []
        self.lock = Lock()

    def _get_page(self):
        if hasattr(self.local, "page"):
            return self.local.page
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
        page = browser.new_page()
        self.local.pw = pw
        self.local.browser = browser
        self.local.page = page
        with self.lock:
            self.contexts.append({"pw": pw, "browser": browser, "page": page})
        return page

    def _task(self, car_id: str) -> Dict[str, Any]:
        page = self._get_page()
        if page is None:
            return {}
        return extract_detail_with_playwright_on_page(page, car_id, self.locale, self.timeout)

    def fetch(self, car_id: str) -> Dict[str, Any]:
        future = self.executor.submit(self._task, car_id)
        return future.result()

    def close(self) -> None:
        try:
            self.executor.shutdown(wait=True)
        except Exception:
            pass
        for ctx in self.contexts:
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


def parse_list_html_for_thumbs(html: str) -> Dict[str, List[str]]:
    soup = BeautifulSoup(html, "lxml")
    thumb_map: Dict[str, List[str]] = {}
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "/car_thumbnails/" in src and "car" in src:
            match = re.search(r"(car\d+)", src)
            if match:
                car_id = match.group(1)
                thumb_map.setdefault(car_id, []).append(src)
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/gt7/carlist/id/" not in href:
            continue
        match = re.search(r"/id/(car\d+)", href)
        if not match:
            continue
        car_id = match.group(1)
        img_url = None
        img_tag = anchor.find("img")
        if img_tag and img_tag.get("src"):
            img_url = img_tag.get("src")
        if not img_url and anchor.parent is not None:
            parent_img = anchor.parent.find("img")
            if parent_img and parent_img.get("src"):
                img_url = parent_img.get("src")
        if not img_url:
            style = anchor.get("style") or (anchor.parent.get("style") if anchor.parent else None)
            if style:
                m = re.search(r"url\\([\"']?([^\"')]+)", style)
                if m:
                    img_url = m.group(1)
        if img_url:
            thumb_map.setdefault(car_id, []).append(img_url)
    deduped: Dict[str, List[str]] = {}
    for car_id, urls in thumb_map.items():
        seen = set()
        out = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        deduped[car_id] = out
    return deduped


def extract_list_thumbs_with_playwright(locale: str, timeout: int = 30) -> Dict[str, List[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    url = f"{BASE_URL}/{locale}/gt7/carlist/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_default_navigation_timeout(timeout * 1000)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception:
                browser.close()
                return {}
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            try:
                page.wait_for_selector("a[href*='/gt7/carlist/id/']", timeout=15000)
            except Exception:
                pass
            try:
                # attempt to force lazy content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            html = page.content()
            browser.close()
        return parse_list_html_for_thumbs(html)
    except Exception:
        return {}


def _extract_intro_detail(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    intro = None
    detail = None

    for h4 in soup.find_all("h4"):
        text = h4.get_text(" ", strip=True)
        if not text or len(text) < 20:
            continue
        parent = h4.parent
        if parent:
            p = parent.find("p")
            if p:
                intro = text
                detail = p.get_text(" ", strip=True)
                break

    if not intro:
        main = soup.find("main") or soup
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in main.find_all("p")
            if p.get_text(strip=True)
        ]
        filtered = [
            t
            for t in paragraphs
            if len(t) > 20 and "Gran Turismo" not in t and "Car List" not in t
        ]
        if filtered:
            intro = filtered[0]
            if len(filtered) > 1:
                detail = filtered[1]

    return intro, detail


def parse_detail_html(html: str, car_id: Optional[str] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {}

    h1 = soup.find("h1")
    if h1:
        data["name"] = h1.get_text(strip=True)

    h2 = soup.find("h2")
    if h2:
        data["manufacturer_name"] = h2.get_text(strip=True)

    intro, detail = _extract_intro_detail(soup)
    if not intro:
        og_desc = parse_og_description(html)
        if og_desc:
            intro = og_desc
    if intro:
        data["intro"] = intro
    if detail:
        data["detail"] = detail

    specs = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True)
                val = cells[1].get_text(" ", strip=True)
                if key and val:
                    specs.append((key, val))
    if not specs:
        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                key = dt.get_text(" ", strip=True)
                val = dd.get_text(" ", strip=True)
                if key and val:
                    specs.append((key, val))

    if specs:
        data["specs"] = specs

    image_urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if looks_like_image_url(src):
            if car_id:
                if car_id in src and "/car_thumbnails/" not in src:
                    image_urls.append(src)
            else:
                image_urls.append(src)
    if car_id:
        pattern = rf"/common/dist/gt7/carlist/assets/{car_id}_[^\"'\\s]+\\.(?:jpg|jpeg|png|webp)"
        for match in re.findall(pattern, html, flags=re.IGNORECASE):
            image_urls.append(match)
    if not image_urls:
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            content = og.get("content")
            if not car_id or (car_id and car_id in content):
                image_urls.append(content)
    if image_urls:
        seen = set()
        unique = []
        for url in image_urls:
            if url in seen:
                continue
            seen.add(url)
            unique.append(url)
        data["hero_images"] = unique

    return data


def extract_hero_module_files(index_js: str, car_id: str) -> List[str]:
    pattern = re.compile(
        rf'{re.escape(car_id)}_[0-9]+_[0-9]+\.(?:jpg|jpeg|png|webp)"\s*:\s*\(\)\s*=>\s*e\(\(\)\s*=>\s*import\("\./([^"]+\.js)"\)',
        flags=re.IGNORECASE,
    )
    modules: List[str] = []
    seen = set()
    for match in pattern.finditer(index_js):
        module_name = match.group(1)
        if module_name in seen:
            continue
        seen.add(module_name)
        modules.append(module_name)
    return modules


def extract_hero_urls_from_module_js(module_js: str, car_id: str) -> List[str]:
    pattern = re.compile(
        rf"(/common/dist/gt7/carlist/assets/{re.escape(car_id)}_[0-9]+_[0-9]+-[^\"']+\.(?:jpg|jpeg|png|webp))",
        flags=re.IGNORECASE,
    )
    urls: List[str] = []
    seen_keys = set()
    for match in pattern.finditer(module_js):
        url = match.group(1)
        key_match = re.search(rf"({re.escape(car_id)}_[0-9]+_[0-9]+)", url, flags=re.IGNORECASE)
        if not key_match:
            continue
        key = key_match.group(1).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        urls.append(url)
    return urls


def resolve_hero_urls_from_asset_modules(
    session: requests.Session,
    index_js: str,
    car_id: str,
    timeout: int,
) -> List[str]:
    modules = extract_hero_module_files(index_js, car_id)
    if not modules:
        return []
    urls: List[str] = []
    seen_keys = set()
    for module_name in modules:
        module_url = resolve_asset_url(module_name)
        try:
            module_js = fetch_text(session, module_url, timeout)
        except Exception:
            continue
        for url in extract_hero_urls_from_module_js(module_js, car_id):
            key_match = re.search(rf"({re.escape(car_id)}_[0-9]+_[0-9]+)", url, flags=re.IGNORECASE)
            if not key_match:
                continue
            key = key_match.group(1).lower()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            urls.append(url)
    return urls


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
    progress_desc: str = "Cars",
    progress_position: int = 0,
    commit_batch: int = 1,
    sqlite_wal: bool = False,
    engines_dir: Optional[Path] = None,
    downloader_engine: str = "python",
    download_workers: int = 32,
    download_timeout: int = 30,
    download_retries: int = 2,
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

    def process_car(car_id: str):
        car = car_data.get(car_id, {})
        images = split_images(car)

        manufacturer_id = car.get("manufacturerId")
        manufacturer_name = None
        if manufacturer_id and manufacturer_id in tuner_map:
            manufacturer_name = tuner_map.get(manufacturer_id)
        if not manufacturer_name:
            manufacturer_name = pick_first(
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
        car_name = pick_first(car, ["nameShort", "name", "carName", "model"]) or car_id
        if not car_name:
            car_name = pick_first(car, ["nameLong", "carNameLong"]) or car_id
        year = pick_first(car, ["year", "productionYear"])
        if not year:
            name_long = pick_first(car, ["nameLong", "carNameLong"])
            year = derive_year_from_name(name_long or car_name)
        country_id = car.get("countryId")
        aspiration_raw = pick_first(car, ["aspirationLong", "aspiration"])
        aspiration_code = pick_first(car, ["aspirationShort"])
        drivetrain_code = normalize_drivetrain_code(pick_first(car, ["driveTrain"]), locale)
        intro = None
        detail = None
        car_class = pick_first(car, ["carClass", "class"])
        pp = pick_first(car, ["pp", "performance", "performancePoint"])

        logo_url = images["logos"][0] if images["logos"] else None
        if manufacturer_id and not logo_url:
            logo_url = f"/common/dist/gt7/carlist/tuner_logos/light/{manufacturer_id}.png"

        specs = extract_specs_from_data(car)

        hero_urls = images["heroes"]
        thumb_urls = thumb_map.get(car_id) or images["thumbs"]

        desc_item = description_map.get(car_id)
        if isinstance(desc_item, dict):
            intro = desc_item.get("hero") or intro
            detail = desc_item.get("desc") or detail

        if download_images and len(hero_urls) <= 1:
            try:
                hero_from_assets = resolve_hero_urls_from_asset_modules(
                    session=get_session(),
                    index_js=index_js,
                    car_id=car_id,
                    timeout=timeout,
                )
            except Exception:
                hero_from_assets = []
            if hero_from_assets:
                hero_urls = hero_from_assets

        # Keep one stable HTTP-detail parse across all modes; Playwright can enrich afterward.
        need_detail_fetch = (
            download_images
            or not intro
            or not detail
            or not specs
            or len(hero_urls) <= 1
        )
        if need_detail_fetch:
            try:
                detail_url = f"{BASE_URL}/{path_locale}/gt7/carlist/id/{car_id}"
                detail_html = fetch_text(get_session(), detail_url, timeout)
                detail_data = parse_detail_html(detail_html, car_id)
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

        if use_playwright:
            try:
                detail_data: Dict[str, Any] = {}
                if node_playwright_script is not None:
                    def fetch_python_playwright_detail() -> Dict[str, Any]:
                        if pw_pool is not None:
                            return pw_pool.fetch(car_id)
                        page = get_playwright_page()
                        if page is not None:
                            return extract_detail_with_playwright_on_page(
                                page, car_id, path_locale, timeout
                            )
                        return extract_detail_with_playwright(car_id, path_locale, timeout)

                    try:
                        detail_data = extract_detail_with_node(
                            script=node_playwright_script,
                            car_id=car_id,
                            locale=path_locale,
                            timeout=timeout,
                            workers=max(1, playwright_workers or workers or 1),
                        )
                    except Exception:
                        detail_data = {}
                    node_heroes = detail_data.get("hero_images") if isinstance(detail_data, dict) else None
                    node_hero_count = len(node_heroes) if isinstance(node_heroes, list) else 0
                    node_low_quality = (not detail_data) or (not detail_data.get("detail")) or (node_hero_count <= 1)
                    if node_low_quality:
                        try:
                            fallback_detail = fetch_python_playwright_detail()
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
                elif pw_pool is not None:
                    detail_data = pw_pool.fetch(car_id)
                else:
                    page = get_playwright_page()
                    if page is not None:
                        detail_data = extract_detail_with_playwright_on_page(page, car_id, path_locale, timeout)
                    else:
                        detail_data = extract_detail_with_playwright(car_id, path_locale, timeout)
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
            manufacturer_id = slugify(manufacturer_name)

        aspiration_code = normalize_aspiration_code(aspiration_code or aspiration_raw, locale)
        aspiration_label = extract_aspiration_label(aspiration_raw)

        logo_path = None
        image_rows: List[Dict[str, str]] = []
        if download_images and go_downloader_bin:
            try:
                logo_path, image_rows = build_assets_with_go_downloader(
                    car_id=car_id,
                    manufacturer_id=manufacturer_id,
                    logo_url=logo_url,
                    hero_urls=hero_urls or [],
                    thumb_urls=thumb_urls or [],
                    image_dir=image_dir,
                    go_binary=go_downloader_bin,
                    workers=download_workers,
                    timeout=download_timeout,
                    retries=download_retries,
                )
            except Exception:
                session = get_session()
                logo_path = build_logo(manufacturer_id, logo_url, image_dir, session, timeout)
                image_rows = build_car_images(
                    car_id,
                    image_dir,
                    hero_urls or [],
                    thumb_urls or [],
                    session,
                    timeout,
                )
        elif download_images:
            session = get_session()
            logo_path = build_logo(manufacturer_id, logo_url, image_dir, session, timeout)
            image_rows = build_car_images(
                car_id,
                image_dir,
                hero_urls or [],
                thumb_urls or [],
                session,
                timeout,
            )

        spec_pairs: List[Tuple[str, str]] = []
        if isinstance(specs, list):
            for item in specs:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    spec_pairs.append((str(item[0]), str(item[1])))
                elif isinstance(item, dict) and "spec_key" in item and "spec_raw" in item:
                    spec_pairs.append((str(item["spec_key"]), str(item["spec_raw"])))
        elif isinstance(specs, dict):
            spec_pairs.extend([(str(k), str(v)) for k, v in specs.items()])

        # Extract drivetrain / aspiration from localized specs if present
        filtered_pairs: List[Tuple[str, str]] = []
        drivetrain_label = None
        for label, raw_value in spec_pairs:
            spec_code, spec_label, _ = map_spec_label(label, locale, raw_value)
            if spec_code == "drivetrain":
                drivetrain_label = str(raw_value).strip()
                if not drivetrain_code:
                    drivetrain_code = normalize_drivetrain_code(drivetrain_label, locale)
                continue
            if spec_code == "aspiration":
                if not aspiration_raw:
                    aspiration_raw = str(raw_value).strip()
                if not aspiration_code:
                    aspiration_code = normalize_aspiration_code(aspiration_raw, locale)
                continue
            filtered_pairs.append((label, raw_value))

        spec_pairs = filtered_pairs

        return {
            "car_id": car_id,
            "manufacturer": {
                "id": manufacturer_id,
                "name": manufacturer_name,
                "logo_path": logo_path,
                "country_id": country_id if locale == base_path_locale else None,
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
                "locale": locale,
                "name": car_name,
                "intro": intro,
                "detail": detail,
            },
            "aspiration": {
                "code": aspiration_code,
                "label": aspiration_label or aspiration_raw,
            },
            "drivetrain": {
                "code": drivetrain_code,
                "label": drivetrain_label,
            },
            "spec_pairs": spec_pairs,
            "images": image_rows,
        }

    # Filter cars to process
    if resume:
        car_ids = [cid for cid in car_ids if db.latest_status(conn, cid, locale) != "success"]

    executor_workers = max(1, int(workers or 1))
    effective_commit_batch = max(1, int(commit_batch or 1))
    pending_writes = 0
    futures = []
    with ThreadPoolExecutor(max_workers=executor_workers) as executor:
        for car_id in car_ids:
            futures.append(executor.submit(process_car, car_id))

        progress_bar = None
        if show_progress:
            progress_bar = tqdm(
                total=len(futures),
                desc=progress_desc,
                position=progress_position,
                leave=True,
            )
        for future in as_completed(futures):
            car_id = None
            try:
                result = future.result()
                car_id = result["car_id"]

                db.upsert_manufacturer(
                    conn, result["manufacturer"], update_name=(locale == base_path_locale)
                )
                if result["manufacturer"].get("name"):
                    db.upsert_manufacturer_i18n(
                        conn,
                        result["manufacturer"]["id"],
                        locale,
                        result["manufacturer"]["name"],
                    )
                db.upsert_car(conn, result["car"], update_texts=(locale == base_path_locale))
                db.upsert_car_text(conn, result["text"])
                if result.get("aspiration") and result["aspiration"].get("code"):
                    code = result["aspiration"]["code"]
                    label = result["aspiration"].get("label") or code
                    if code == "TC+SC":
                        combined = build_tc_sc_label(conn, locale)
                        if combined:
                            label = combined
                    db.upsert_aspiration(conn, code, locale, label, default_name=code)
                if result.get("drivetrain") and result["drivetrain"].get("code"):
                    code = result["drivetrain"]["code"]
                    label = result["drivetrain"].get("label") or code
                    db.upsert_drivetrain(conn, code, locale, label, default_name=code)

                if rust_spec_bin is not None:
                    try:
                        spec_rows = normalize_specs_with_rust(
                            binary=rust_spec_bin,
                            specs=result["spec_pairs"],
                            locale=locale,
                            mappings_dir=spec_mappings_dir,
                        )
                    except Exception:
                        spec_rows = normalize_specs_py(result["spec_pairs"], locale=locale)
                else:
                    spec_rows = normalize_specs_py(result["spec_pairs"], locale=locale)
                db.replace_specs(conn, car_id, spec_rows)
                for spec in spec_rows:
                    if spec.get("spec_key") and spec.get("spec_label"):
                        if spec["spec_key"].startswith("raw_"):
                            continue
                        if spec["spec_key"] not in seeded_codes:
                            db.upsert_spec_label(conn, spec["spec_key"], locale, spec["spec_label"])
                if download_images:
                    image_rows = result["images"]
                    if locale != base_path_locale:
                        existing_rows = db.get_car_images(conn, car_id)
                        image_rows = merge_image_rows_preserve_non_regression(existing_rows, image_rows)
                    db.replace_images(conn, car_id, image_rows)

                db.log_fetch(conn, car_id, locale, "success", "", datetime.utcnow().isoformat())
            except Exception as exc:
                if car_id is None:
                    car_id = "unknown"
                db.log_fetch(conn, car_id, locale, "failed", str(exc), datetime.utcnow().isoformat())
            finally:
                pending_writes += 1
                if pending_writes >= effective_commit_batch:
                    conn.commit()
                    pending_writes = 0
                if show_progress and progress_bar:
                    progress_bar.update(1)
                if progress_callback:
                    progress_callback()

            if rate > 0:
                time.sleep(rate)
        if show_progress and progress_bar:
            progress_bar.close()

    if pending_writes > 0:
        conn.commit()

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
