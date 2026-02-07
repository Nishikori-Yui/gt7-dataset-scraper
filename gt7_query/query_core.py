import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    match = re.match(r"-?[0-9]+(\.[0-9]+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def car_name_expr() -> str:
    return "COALESCE(ct.name, c.name)"


def manufacturer_expr() -> str:
    return "COALESCE(mi.name, m.name)"


def country_expr(locale: str) -> Tuple[str, str]:
    return (
        "COALESCE(ci.name, cigb.name, cim.iso3, m.country_id)",
        locale,
    )


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def load_country_maps() -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    base = Path(__file__).resolve().parents[1] / "gt7_scraper" / "mappings"
    iso_path = base / "country_iso.json"
    i18n_path = base / "country_i18n.json"
    iso_map: Dict[str, str] = {}
    i18n_map: Dict[str, Dict[str, str]] = {}
    if iso_path.exists():
        iso_map = json.loads(iso_path.read_text(encoding="utf-8"))
    if i18n_path.exists():
        i18n_map = json.loads(i18n_path.read_text(encoding="utf-8"))
    return iso_map, i18n_map


def resolve_country_label(
    country_id: Optional[str], locale: str, iso_map: Dict[str, str], i18n_map: Dict[str, Dict[str, str]]
) -> Optional[str]:
    if not country_id:
        return None
    iso3 = iso_map.get(country_id)
    if not iso3:
        return country_id
    locales = i18n_map.get(iso3, {})
    return locales.get(locale) or locales.get("gb") or iso3 or country_id


def get_country_info_from_raw_json(raw_json: Optional[str], locale: str) -> Dict[str, Optional[str]]:
    iso_map, i18n_map = load_country_maps()
    if not raw_json:
        return {"country_id": None, "iso3": None, "name": None}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"country_id": None, "iso3": None, "name": None}
    country_id = data.get("countryId")
    if not country_id:
        return {"country_id": None, "iso3": None, "name": None}
    iso3 = iso_map.get(country_id)
    label = resolve_country_label(country_id, locale, iso_map, i18n_map)
    return {"country_id": country_id, "iso3": iso3, "name": label}


def get_country_info(conn: sqlite3.Connection, manufacturer_id: Optional[str], locale: str) -> Dict[str, Optional[str]]:
    if not manufacturer_id:
        return {"country_id": None, "iso3": None, "name": None}
    if table_exists(conn, "country_iso_map") and table_exists(conn, "country_i18n"):
        row = conn.execute(
            "SELECT m.country_id, cim.iso3, COALESCE(ci.name, cigb.name, cim.iso3, m.country_id) AS name "
            "FROM manufacturers m "
            "LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id "
            "LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=? "
            "LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb' "
            "WHERE m.id=?",
            (locale, manufacturer_id),
        ).fetchone()
        if row:
            return {"country_id": row["country_id"], "iso3": row["iso3"], "name": row["name"]}
    if column_exists(conn, "manufacturers", "country_id"):
        row = conn.execute(
            "SELECT country_id FROM manufacturers WHERE id=?",
            (manufacturer_id,),
        ).fetchone()
        if row and row["country_id"]:
            iso_map, i18n_map = load_country_maps()
            country_id = row["country_id"]
            iso3 = iso_map.get(country_id)
            label = resolve_country_label(country_id, locale, iso_map, i18n_map)
            return {"country_id": country_id, "iso3": iso3, "name": label}
    return {"country_id": None, "iso3": None, "name": None}
