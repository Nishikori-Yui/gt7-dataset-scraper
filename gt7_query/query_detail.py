from pathlib import Path
from typing import Any, Dict

from .query_core import (
    connect_db,
    get_country_info,
    get_country_info_from_raw_json,
    table_exists,
)


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
        if table_exists(conn, "car_images"):
            images = conn.execute(
                "SELECT image_type, image_path, sort_order FROM car_images "
                "WHERE car_id=? ORDER BY image_type, sort_order",
                (car_id,),
            ).fetchall()

        country = get_country_info(conn, car_row["manufacturer_id"], locale)
        if not country["country_id"] and car_row["raw_json"]:
            country = get_country_info_from_raw_json(car_row["raw_json"], locale)

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
