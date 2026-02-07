import sqlite3
from typing import Dict, List, Optional


def upsert_manufacturer(conn: sqlite3.Connection, manufacturer: Dict[str, str], update_name: bool = True) -> None:
    country_id = manufacturer.get("country_id")
    if update_name:
        conn.execute(
            "INSERT INTO manufacturers(id, name, logo_path, country_id) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name,"
            " logo_path=COALESCE(excluded.logo_path, manufacturers.logo_path),"
            " country_id=COALESCE(excluded.country_id, manufacturers.country_id)",
            (manufacturer["id"], manufacturer["name"], manufacturer.get("logo_path"), country_id),
        )
    else:
        conn.execute(
            "INSERT INTO manufacturers(id, name, logo_path, country_id) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " logo_path=COALESCE(excluded.logo_path, manufacturers.logo_path),"
            " country_id=COALESCE(excluded.country_id, manufacturers.country_id)",
            (manufacturer["id"], manufacturer["name"], manufacturer.get("logo_path"), country_id),
        )


def upsert_manufacturer_i18n(conn: sqlite3.Connection, manufacturer_id: str, locale: str, name: str) -> None:
    conn.execute(
        "INSERT INTO manufacturer_i18n(id, locale, name) VALUES(?, ?, ?)"
        " ON CONFLICT(id, locale) DO UPDATE SET name=excluded.name",
        (manufacturer_id, locale, name),
    )


def upsert_car(conn: sqlite3.Connection, car: Dict[str, str], update_texts: bool = True) -> None:
    conn.execute(
        "INSERT INTO cars(id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json)"
        " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        " name=CASE WHEN ? THEN excluded.name ELSE cars.name END,"
        " manufacturer_id=excluded.manufacturer_id,"
        " aspiration_code=excluded.aspiration_code,"
        " drivetrain_code=excluded.drivetrain_code,"
        " intro=CASE WHEN ? THEN excluded.intro ELSE cars.intro END,"
        " detail=CASE WHEN ? THEN excluded.detail ELSE cars.detail END,"
        " car_class=CASE WHEN ? THEN excluded.car_class ELSE cars.car_class END,"
        " pp=CASE WHEN ? THEN excluded.pp ELSE cars.pp END,"
        " year=CASE WHEN ? THEN excluded.year ELSE cars.year END,"
        " raw_json=CASE WHEN ? THEN excluded.raw_json ELSE cars.raw_json END",
        (
            car["id"],
            car["name"],
            car.get("manufacturer_id"),
            car.get("aspiration_code"),
            car.get("drivetrain_code"),
            car.get("intro"),
            car.get("detail"),
            car.get("car_class"),
            car.get("pp"),
            car.get("year"),
            car.get("raw_json"),
            1 if update_texts else 0,
            1 if update_texts else 0,
            1 if update_texts else 0,
            1 if update_texts else 0,
            1 if update_texts else 0,
            1 if update_texts else 0,
            1 if update_texts else 0,
        ),
    )


def replace_specs(conn: sqlite3.Connection, car_id: str, specs: List[Dict[str, str]]) -> None:
    locale = None
    if specs:
        locale = specs[0].get("locale")
    if locale:
        conn.execute("DELETE FROM car_specs WHERE car_id=? AND locale=?", (car_id, locale))
    else:
        conn.execute("DELETE FROM car_specs WHERE car_id=?", (car_id,))
    conn.executemany(
        "INSERT INTO car_specs(car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order)"
        " VALUES(?, ?, ?, ?, ?, ?, ?)",
        [
            (
                car_id,
                spec.get("locale", "us"),
                spec["spec_key"],
                spec.get("spec_value"),
                spec.get("spec_unit"),
                spec.get("spec_raw"),
                spec.get("sort_order"),
            )
            for spec in specs
        ],
    )


def upsert_car_text(conn: sqlite3.Connection, text: Dict[str, str]) -> None:
    conn.execute(
        "INSERT INTO car_texts(car_id, locale, name, intro, detail)"
        " VALUES(?, ?, ?, ?, ?)"
        " ON CONFLICT(car_id, locale) DO UPDATE SET name=excluded.name, intro=excluded.intro,"
        " detail=excluded.detail",
        (
            text["car_id"],
            text["locale"],
            text.get("name"),
            text.get("intro"),
            text.get("detail"),
        ),
    )


def upsert_aspiration(
    conn: sqlite3.Connection, code: str, locale: str, label: str, default_name: Optional[str] = None
) -> None:
    if default_name is None:
        default_name = code
    conn.execute(
        "INSERT INTO aspiration_codes(code, default_name) VALUES(?, ?)"
        " ON CONFLICT(code) DO UPDATE SET default_name=excluded.default_name",
        (code, default_name),
    )
    conn.execute(
        "INSERT INTO aspiration_i18n(code, locale, label) VALUES(?, ?, ?)"
        " ON CONFLICT(code, locale) DO UPDATE SET label=excluded.label",
        (code, locale, label),
    )


def get_aspiration_label(conn: sqlite3.Connection, code: str, locale: str) -> Optional[str]:
    cur = conn.execute(
        "SELECT label FROM aspiration_i18n WHERE code=? AND locale=?",
        (code, locale),
    )
    row = cur.fetchone()
    return row["label"] if row else None


def upsert_spec_label(conn: sqlite3.Connection, code: str, locale: str, label: str) -> None:
    conn.execute(
        "INSERT INTO spec_code_i18n(code, locale, label) VALUES(?, ?, ?)"
        " ON CONFLICT(code, locale) DO UPDATE SET label=COALESCE(spec_code_i18n.label, excluded.label)",
        (code, locale, label),
    )


def set_spec_label(conn: sqlite3.Connection, code: str, locale: str, label: str) -> None:
    conn.execute(
        "INSERT INTO spec_code_i18n(code, locale, label) VALUES(?, ?, ?)"
        " ON CONFLICT(code, locale) DO UPDATE SET label=excluded.label",
        (code, locale, label),
    )


def upsert_drivetrain(
    conn: sqlite3.Connection, code: str, locale: str, label: str, default_name: Optional[str] = None
) -> None:
    if default_name is None:
        default_name = code
    conn.execute(
        "INSERT INTO drivetrain_codes(code, default_name) VALUES(?, ?)"
        " ON CONFLICT(code) DO UPDATE SET default_name=excluded.default_name",
        (code, default_name),
    )
    conn.execute(
        "INSERT INTO drivetrain_i18n(code, locale, label) VALUES(?, ?, ?)"
        " ON CONFLICT(code, locale) DO UPDATE SET label=excluded.label",
        (code, locale, label),
    )
