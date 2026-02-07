import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .. import db


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
        key in lower
        for key in [
            "自然",
            "naturally",
            "n/a",
            "na",
            "atmosfér",
            "atmosfer",
            "doğal",
            "dogal",
            "emişli",
            "ατμοσφαιρ",
            "سحب طبيعي",
            "ไม่ใช้ระบบอัดอากาศ",
        ]
    ):
        return "NA"
    if any(key in lower for key in ["涡轮", "渦輪", "turbo", "ターボ", "터보", "турбо"]):
        return "TC"
    if any(
        key in lower
        for key in [
            "机械",
            "機械",
            "supercharger",
            "スーパーチャージャ",
            "슈퍼차저",
            "kompresor",
            "kompresör",
        ]
    ):
        return "SC"
    if any(key in lower for key in ["电", "電", "electric", "電気", "전기"]):
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
    cn_map = {
        "前置后驱": "FR",
        "前置前驱": "FF",
        "中置后驱": "MR",
        "后置后驱": "RR",
        "四驱": "4WD",
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
    path = Path(__file__).resolve().parents[1] / "mappings" / "spec_labels" / f"{locale}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def load_country_iso_map() -> Dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "mappings" / "country_iso.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def load_country_i18n_map() -> Dict[str, Dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "mappings" / "country_i18n.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {}
    cleaned: Dict[str, Dict[str, str]] = {}
    for iso3, locales in data.items():
        if isinstance(locales, dict):
            cleaned[str(iso3)] = {str(key): str(value) for key, value in locales.items()}
    return cleaned


def parse_car_list(path: Path) -> List[str]:
    car_ids: List[str] = []
    if not path.exists():
        return car_ids
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            car_ids.append(value)
    return car_ids
