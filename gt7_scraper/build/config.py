from pathlib import Path
from typing import List

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

DEFAULT_HERO_MANIFEST = str(Path(__file__).resolve().parents[1] / "mappings" / "hero_expected_counts.json")


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


def should_download_for_template(image_policy: str) -> bool:
    return image_policy in {"base-only", "all-locales"}


def should_download_for_overlay(image_policy: str) -> bool:
    return image_policy == "all-locales"
