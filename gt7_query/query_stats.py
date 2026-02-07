import json
from pathlib import Path
from typing import Any, Dict, List

from .query_core import connect_db, load_country_maps, resolve_country_label, table_exists


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
        if table_exists(conn, "country_iso_map") and table_exists(conn, "country_i18n"):
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

        iso_map, i18n_map = load_country_maps()
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
            label = resolve_country_label(country_id, locale, iso_map, i18n_map) or "Unknown"
            counts[label] = counts.get(label, 0) + 1
        return [{"label": key, "count": value} for key, value in sorted(counts.items(), key=lambda item: item[0])]
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
        if table_exists(conn, "car_images"):
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
