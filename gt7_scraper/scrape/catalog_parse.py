import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from ..parser import extract_exported_literal, find_largest_array, find_largest_object
from .constants import BASE_URL, EXPORT_NAMES, ID_LIST_EXPORT_NAMES, LOCALE_PATH_MAP, TUNER_EXPORT_NAMES


class ScraperError(Exception):
    pass


def resolve_locales(locale: str) -> Tuple[str, str]:
    if locale in {"br", "mx", "gr", "sa"}:
        reverse = {value: key for key, value in LOCALE_PATH_MAP.items()}
        return locale, reverse.get(locale, locale)
    return LOCALE_PATH_MAP.get(locale, locale), locale


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
    match = re.search(r"(/common/dist/gt7/carlist/assets/index-[^\"']+\.js)", html)
    if match:
        return normalize_url(match.group(1))
    raise ScraperError("Failed to locate index JS bundle")


def extract_site_total_count(html: str) -> Optional[int]:
    matches = re.findall(r"(\d{1,5})\s*Car", html, flags=re.IGNORECASE)
    if matches:
        return max(int(match) for match in matches)
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


def pick_first(data: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def extract_specs_from_data(car: Dict[str, Any]) -> List[Tuple[str, str]]:
    specs: List[Tuple[str, str]] = []
    if isinstance(car.get("spec"), dict):
        specs.extend([(key, car["spec"][key]) for key in car["spec"].keys()])
    elif isinstance(car.get("specs"), dict):
        specs.extend([(key, car["specs"][key]) for key in car["specs"].keys()])
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
    for key, value in specs:
        if key in seen:
            continue
        seen.add(key)
        unique_specs.append((key, value))
    return unique_specs
