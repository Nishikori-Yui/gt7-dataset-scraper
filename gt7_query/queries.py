import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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


def _car_name_expr() -> str:
    return "COALESCE(ct.name, c.name)"


def _manufacturer_expr() -> str:
    return "COALESCE(mi.name, m.name)"


def _country_expr(locale: str) -> Tuple[str, str]:
    return (
        "COALESCE(ci.name, cigb.name, cim.iso3, m.country_id)",
        locale,
    )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _load_country_maps() -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
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


def _resolve_country_label(country_id: Optional[str], locale: str, iso_map: Dict[str, str], i18n_map: Dict[str, Dict[str, str]]) -> Optional[str]:
    if not country_id:
        return None
    iso3 = iso_map.get(country_id)
    if not iso3:
        return country_id
    locales = i18n_map.get(iso3, {})
    return locales.get(locale) or locales.get("gb") or iso3 or country_id


def list_cars(db_path: Path, locale: str = "gb", sort_by: str = "manufacturer", limit: int = 0) -> List[Dict[str, Any]]:
    if sort_by == "manufacturer":
        return list_cars_sorted_by_manufacturer(db_path, locale, limit)
    if sort_by == "country":
        return list_cars_sorted_by_country(db_path, locale, limit)
    if sort_by == "drivetrain":
        return list_cars_sorted_by_drivetrain(db_path, locale, limit)
    if sort_by == "max_power":
        return list_cars_sorted_by_max_power(db_path, locale, limit)
    if sort_by == "weight":
        return list_cars_sorted_by_weight(db_path, locale, limit)
    raise ValueError(f"Unsupported sort: {sort_by}")


def list_cars_sorted_by_manufacturer(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        query = (
            "SELECT c.id, {name} AS name, {maker} AS sort_key "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
            "LEFT JOIN manufacturers m ON m.id=c.manufacturer_id "
            "LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=? "
            "ORDER BY sort_key COLLATE NOCASE, name COLLATE NOCASE"
        ).format(name=_car_name_expr(), maker=_manufacturer_expr())
        rows = conn.execute(query, (locale, locale)).fetchall()
        if limit > 0:
            rows = rows[:limit]
        return [{"id": row["id"], "name": row["name"]} for row in rows]
    finally:
        conn.close()


def list_cars_sorted_by_country(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        if _table_exists(conn, "country_iso_map") and _table_exists(conn, "country_i18n"):
            country_expr, locale_val = _country_expr(locale)
            query = (
                "SELECT c.id, {name} AS name, {country} AS sort_key "
                "FROM cars c "
                "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
                "LEFT JOIN manufacturers m ON m.id=c.manufacturer_id "
                "LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id "
                "LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=? "
                "LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb' "
                "ORDER BY sort_key COLLATE NOCASE, name COLLATE NOCASE"
            ).format(name=_car_name_expr(), country=country_expr)
            try:
                rows = conn.execute(query, (locale, locale_val)).fetchall()
            except sqlite3.OperationalError:
                rows = None
            if rows is not None:
                if limit > 0:
                    rows = rows[:limit]
                return [{"id": row["id"], "name": row["name"]} for row in rows]

        iso_map, i18n_map = _load_country_maps()
        rows = conn.execute(
            "SELECT c.id, {name} AS name, c.raw_json "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?"
            .format(name=_car_name_expr()),
            (locale,),
        ).fetchall()
        enriched = []
        for row in rows:
            country_id = None
            raw = row["raw_json"]
            if raw:
                try:
                    data = json.loads(raw)
                    country_id = data.get("countryId")
                except Exception:
                    country_id = None
            label = _resolve_country_label(country_id, locale, iso_map, i18n_map)
            enriched.append((label, row["id"], row["name"]))
        enriched.sort(key=lambda x: (x[0] is None, x[0] or "", x[2] or ""))
        if limit > 0:
            enriched = enriched[:limit]
        return [{"id": car_id, "name": name} for _, car_id, name in enriched]
    finally:
        conn.close()


def list_cars_sorted_by_drivetrain(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        query = (
            "SELECT c.id, {name} AS name, COALESCE(di.label, c.drivetrain_code) AS sort_key "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
            "LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=? "
            "ORDER BY sort_key COLLATE NOCASE, name COLLATE NOCASE"
        ).format(name=_car_name_expr())
        rows = conn.execute(query, (locale, locale)).fetchall()
        if limit > 0:
            rows = rows[:limit]
        return [{"id": row["id"], "name": row["name"]} for row in rows]
    finally:
        conn.close()


def _list_sorted_by_spec(db_path: Path, locale: str, spec_key: str, limit: int, descending: bool) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        query = (
            "SELECT c.id, {name} AS name, s.spec_value AS spec_value "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
            "LEFT JOIN car_specs s ON s.car_id=c.id AND s.locale=? AND s.spec_key=?"
        ).format(name=_car_name_expr())
        rows = conn.execute(query, (locale, "gb", spec_key)).fetchall()
        enriched = []
        for row in rows:
            num = parse_number(row["spec_value"])
            enriched.append((num, row["id"], row["name"]))
        enriched.sort(key=lambda x: (x[0] is None, x[0]), reverse=descending)
        if limit > 0:
            enriched = enriched[:limit]
        return [{"id": car_id, "name": name} for _, car_id, name in enriched]
    finally:
        conn.close()


def list_cars_sorted_by_max_power(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    return _list_sorted_by_spec(db_path, locale, "max_power", limit, descending=True)


def list_cars_sorted_by_weight(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    return _list_sorted_by_spec(db_path, locale, "weight", limit, descending=False)


def _get_country_info_from_raw_json(raw_json: Optional[str], locale: str) -> Dict[str, Optional[str]]:
    iso_map, i18n_map = _load_country_maps()
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
    label = _resolve_country_label(country_id, locale, iso_map, i18n_map)
    return {"country_id": country_id, "iso3": iso3, "name": label}


def _get_country_info(conn: sqlite3.Connection, manufacturer_id: Optional[str], locale: str) -> Dict[str, Optional[str]]:
    if not manufacturer_id:
        return {"country_id": None, "iso3": None, "name": None}
    if _table_exists(conn, "country_iso_map") and _table_exists(conn, "country_i18n"):
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
    if _column_exists(conn, "manufacturers", "country_id"):
        row = conn.execute(
            "SELECT country_id FROM manufacturers WHERE id=?",
            (manufacturer_id,),
        ).fetchone()
        if row and row["country_id"]:
            iso_map, i18n_map = _load_country_maps()
            country_id = row["country_id"]
            iso3 = iso_map.get(country_id)
            label = _resolve_country_label(country_id, locale, iso_map, i18n_map)
            return {"country_id": country_id, "iso3": iso3, "name": label}
    return {"country_id": None, "iso3": None, "name": None}


def get_car_details(db_path: Path, car_id: str, locale: str = "gb") -> Dict[str, Any]:
    conn = connect_db(db_path)
    try:
        car_row = conn.execute(
            "SELECT id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, raw_json "
            "FROM cars WHERE id=?",
            (car_id,),
        ).fetchone()
        if not car_row:
            raise ValueError(f"Car not found: {car_id}")

        text_row = conn.execute(
            "SELECT name, intro, detail FROM car_texts WHERE car_id=? AND locale=?",
            (car_id, locale),
        ).fetchone()

        name = text_row["name"] if text_row and text_row["name"] else car_row["name"]
        intro = text_row["intro"] if text_row and text_row["intro"] else car_row["intro"]
        detail = text_row["detail"] if text_row and text_row["detail"] else car_row["detail"]

        manufacturer_row = conn.execute(
            "SELECT m.id, COALESCE(mi.name, m.name) AS name "
            "FROM manufacturers m "
            "LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=? "
            "WHERE m.id=?",
            (locale, car_row["manufacturer_id"]),
        ).fetchone()

        aspiration_label = conn.execute(
            "SELECT label FROM aspiration_i18n WHERE code=? AND locale=?",
            (car_row["aspiration_code"], locale),
        ).fetchone()
        drivetrain_label = conn.execute(
            "SELECT label FROM drivetrain_i18n WHERE code=? AND locale=?",
            (car_row["drivetrain_code"], locale),
        ).fetchone()

        specs = conn.execute(
            "SELECT s.spec_key, i.label AS spec_label, s.spec_value, s.spec_unit, s.spec_raw, s.sort_order "
            "FROM car_specs s "
            "LEFT JOIN spec_code_i18n i ON i.code=s.spec_key AND i.locale=s.locale "
            "WHERE s.car_id=? AND s.locale=? "
            "ORDER BY s.sort_order",
            (car_id, locale),
        ).fetchall()

        images = []
        if _table_exists(conn, "car_images"):
            images = conn.execute(
                "SELECT image_type, image_path, sort_order FROM car_images "
                "WHERE car_id=? ORDER BY image_type, sort_order",
                (car_id,),
            ).fetchall()

        country = _get_country_info(conn, car_row["manufacturer_id"], locale)
        if not country["country_id"] and car_row["raw_json"]:
            country = _get_country_info_from_raw_json(car_row["raw_json"], locale)

        return {
            "id": car_row["id"],
            "name": name,
            "manufacturer": {
                "id": manufacturer_row["id"] if manufacturer_row else None,
                "name": manufacturer_row["name"] if manufacturer_row else None,
            },
            "country": country,
            "drivetrain": {
                "code": car_row["drivetrain_code"],
                "label": drivetrain_label["label"] if drivetrain_label else car_row["drivetrain_code"],
            },
            "aspiration": {
                "code": car_row["aspiration_code"],
                "label": aspiration_label["label"] if aspiration_label else car_row["aspiration_code"],
            },
            "intro": intro,
            "detail": detail,
            "specs": [
                {
                    "spec_key": row["spec_key"],
                    "spec_label": row["spec_label"],
                    "spec_value": row["spec_value"],
                    "spec_unit": row["spec_unit"],
                    "spec_raw": row["spec_raw"],
                    "sort_order": row["sort_order"],
                }
                for row in specs
            ],
            "images": [
                {
                    "image_type": row["image_type"],
                    "image_path": row["image_path"],
                    "sort_order": row["sort_order"],
                }
                for row in images
            ],
        }
    finally:
        conn.close()


def stats_by_manufacturer(db_path: Path, locale: str = "gb") -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT COALESCE(mi.name, m.name) AS label, COUNT(*) AS count "
            "FROM cars c "
            "LEFT JOIN manufacturers m ON m.id=c.manufacturer_id "
            "LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=? "
            "GROUP BY m.id "
            "ORDER BY label COLLATE NOCASE",
            (locale,),
        ).fetchall()
        return [{"label": row["label"], "count": row["count"]} for row in rows]
    finally:
        conn.close()


def stats_by_country(db_path: Path, locale: str = "gb") -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        if _table_exists(conn, "country_iso_map") and _table_exists(conn, "country_i18n"):
            rows = conn.execute(
                "SELECT COALESCE(ci.name, cigb.name, cim.iso3, m.country_id) AS label, COUNT(*) AS count "
                "FROM cars c "
                "LEFT JOIN manufacturers m ON m.id=c.manufacturer_id "
                "LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id "
                "LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=? "
                "LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb' "
                "GROUP BY cim.iso3, m.country_id "
                "ORDER BY label COLLATE NOCASE",
                (locale,),
            ).fetchall()
            return [{"label": row["label"], "count": row["count"]} for row in rows]

        iso_map, i18n_map = _load_country_maps()
        rows = conn.execute(
            "SELECT raw_json FROM cars",
        ).fetchall()
        counts: Dict[str, int] = {}
        for row in rows:
            raw = row["raw_json"]
            country_id = None
            if raw:
                try:
                    data = json.loads(raw)
                    country_id = data.get("countryId")
                except Exception:
                    country_id = None
            label = _resolve_country_label(country_id, locale, iso_map, i18n_map) or "Unknown"
            counts[label] = counts.get(label, 0) + 1
        return [{"label": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: x[0])]
    finally:
        conn.close()


def stats_by_drivetrain(db_path: Path, locale: str = "gb") -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT COALESCE(di.label, c.drivetrain_code) AS label, COUNT(*) AS count "
            "FROM cars c "
            "LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=? "
            "GROUP BY c.drivetrain_code "
            "ORDER BY label COLLATE NOCASE",
            (locale,),
        ).fetchall()
        return [{"label": row["label"], "count": row["count"]} for row in rows]
    finally:
        conn.close()


def overview_stats(db_path: Path) -> Dict[str, Any]:
    conn = connect_db(db_path)
    try:
        cars = conn.execute("SELECT COUNT(*) AS cnt FROM cars").fetchone()["cnt"]
        manufacturers = conn.execute("SELECT COUNT(*) AS cnt FROM manufacturers").fetchone()["cnt"]
        specs = conn.execute("SELECT COUNT(*) AS cnt FROM car_specs").fetchone()["cnt"]
        images = 0
        if _table_exists(conn, "car_images"):
            images = conn.execute("SELECT COUNT(*) AS cnt FROM car_images").fetchone()["cnt"]
        locales = [row[0] for row in conn.execute("SELECT DISTINCT locale FROM car_texts ORDER BY locale").fetchall()]
        return {
            "cars": cars,
            "manufacturers": manufacturers,
            "specs": specs,
            "images": images,
            "locales": locales,
        }
    finally:
        conn.close()


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
