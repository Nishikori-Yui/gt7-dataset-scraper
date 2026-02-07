import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .query_core import (
    car_name_expr,
    connect_db,
    country_expr,
    load_country_maps,
    manufacturer_expr,
    parse_number,
    resolve_country_label,
    table_exists,
)


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
        ).format(name=car_name_expr(), maker=manufacturer_expr())
        rows = conn.execute(query, (locale, locale)).fetchall()
        if limit > 0:
            rows = rows[:limit]
        return [{"id": row["id"], "name": row["name"]} for row in rows]
    finally:
        conn.close()


def list_cars_sorted_by_country(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        if table_exists(conn, "country_iso_map") and table_exists(conn, "country_i18n"):
            country_sql, locale_val = country_expr(locale)
            query = (
                "SELECT c.id, {name} AS name, {country} AS sort_key "
                "FROM cars c "
                "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
                "LEFT JOIN manufacturers m ON m.id=c.manufacturer_id "
                "LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id "
                "LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=? "
                "LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb' "
                "ORDER BY sort_key COLLATE NOCASE, name COLLATE NOCASE"
            ).format(name=car_name_expr(), country=country_sql)
            try:
                rows = conn.execute(query, (locale, locale_val)).fetchall()
            except sqlite3.OperationalError:
                rows = None
            if rows is not None:
                if limit > 0:
                    rows = rows[:limit]
                return [{"id": row["id"], "name": row["name"]} for row in rows]

        iso_map, i18n_map = load_country_maps()
        rows = conn.execute(
            "SELECT c.id, {name} AS name, c.raw_json "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?".format(name=car_name_expr()),
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
            label = resolve_country_label(country_id, locale, iso_map, i18n_map)
            enriched.append((label, row["id"], row["name"]))
        enriched.sort(key=lambda item: (item[0] is None, item[0] or "", item[2] or ""))
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
        ).format(name=car_name_expr())
        rows = conn.execute(query, (locale, locale)).fetchall()
        if limit > 0:
            rows = rows[:limit]
        return [{"id": row["id"], "name": row["name"]} for row in rows]
    finally:
        conn.close()


def list_cars_sorted_by_max_power(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    return list_sorted_by_spec(db_path, locale, "max_power", limit, descending=True)


def list_cars_sorted_by_weight(db_path: Path, locale: str, limit: int = 0) -> List[Dict[str, Any]]:
    return list_sorted_by_spec(db_path, locale, "weight", limit, descending=False)


def list_sorted_by_spec(db_path: Path, locale: str, spec_key: str, limit: int, descending: bool) -> List[Dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        query = (
            "SELECT c.id, {name} AS name, COALESCE(sl.spec_value, sgb.spec_value) AS spec_value "
            "FROM cars c "
            "LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? "
            "LEFT JOIN car_specs sl ON sl.car_id=c.id AND sl.locale=? AND sl.spec_key=? "
            "LEFT JOIN car_specs sgb ON sgb.car_id=c.id AND sgb.locale='gb' AND sgb.spec_key=?"
        ).format(name=car_name_expr())
        rows = conn.execute(query, (locale, locale, spec_key, spec_key)).fetchall()
        enriched = []
        for row in rows:
            num = parse_number(row["spec_value"])
            enriched.append((num, row["id"], row["name"]))
        enriched.sort(key=lambda item: (item[0] is None, item[0]), reverse=descending)
        if limit > 0:
            enriched = enriched[:limit]
        return [{"id": car_id, "name": name} for _, car_id, name in enriched]
    finally:
        conn.close()
