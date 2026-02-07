from pathlib import Path
from typing import List, Optional

from gt7_scraper.scraper import BASE_URL, build_session, extract_site_total_count, fetch_text, resolve_locales

DEFAULT_LOCALES = [
    "gb",
    "us",
    "cn",
    "tw",
    "jp",
    "kr",
    "de",
    "fr",
    "it",
    "nl",
    "es",
    "mx",
    "pt",
    "br",
    "pl",
    "ru",
    "cz",
    "tr",
    "gr",
    "sa",
    "th",
]

DEFAULT_HERO_MANIFEST = "./gt7_scraper/mappings/hero_expected_counts.json"


def get_site_total(locale: str, timeout: int) -> Optional[int]:
    session = build_session()
    path_locale, _ = resolve_locales(locale)
    html = fetch_text(session, f"{BASE_URL}/{path_locale}/gt7/carlist/", timeout)
    return extract_site_total_count(html)


def resolve_base_locale(locales: List[str], requested: str) -> str:
    if requested:
        return requested
    if len(locales) == 1:
        return locales[0]
    if "gb" in locales:
        return "gb"
    return locales[0]


def normalize_locale_order(locales: List[str], base_locale: str) -> List[str]:
    ordered: List[str] = []
    seen = set()
    if base_locale:
        ordered.append(base_locale)
        seen.add(base_locale)
    for item in locales:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def resolve_playwright_policy(
    engine: str,
    use_playwright_flag: bool,
    requested_policy: Optional[str],
    requested_engine: str,
) -> tuple[bool, str]:
    if requested_policy:
        policy = requested_policy
    elif use_playwright_flag:
        policy = "node" if engine == "hybrid" else "python"
    else:
        policy = "off"
    use_playwright = policy != "off"
    playwright_engine = requested_engine or ("node" if engine == "hybrid" else "python")
    if policy in {"node", "python"}:
        playwright_engine = policy
    return use_playwright, playwright_engine


def resolve_image_policy(requested_policy: str, images_all_flag: bool, skip_images_flag: bool) -> str:
    if skip_images_flag:
        return "none"
    if images_all_flag:
        return "all-locales"
    return requested_policy


def should_download_for_template(image_policy: str) -> bool:
    return image_policy in {"base-only", "all-locales"}


def should_download_for_overlay(image_policy: str) -> bool:
    return image_policy == "all-locales"


def should_download_for_combined(image_policy: str, locale: str, base_locale: str) -> bool:
    if image_policy == "none":
        return False
    if image_policy == "all-locales":
        return True
    return locale == base_locale


def count_list_total(path: str) -> Optional[int]:
    if not path:
        return None
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            return len([line for line in (item.strip() for item in file) if line and not line.startswith("#")])
    except Exception:
        return None
