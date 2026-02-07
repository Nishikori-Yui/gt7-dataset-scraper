import sqlite3
from typing import Dict, Iterable, List


def prune_car_texts_except_locale(conn: sqlite3.Connection, locale: str) -> None:
    conn.execute("DELETE FROM car_texts WHERE locale<>?", (locale,))
    conn.commit()


def get_car_images(conn: sqlite3.Connection, car_id: str) -> List[Dict[str, object]]:
    try:
        cur = conn.execute(
            "SELECT image_path, sort_order, image_type FROM car_images WHERE car_id=?"
            " ORDER BY CASE image_type WHEN 'hero' THEN 0 WHEN 'thumb' THEN 1 ELSE 2 END,"
            " sort_order, id",
            (car_id,),
        )
    except sqlite3.OperationalError:
        return []
    rows: List[Dict[str, object]] = []
    for row in cur.fetchall():
        rows.append(
            {
                "image_path": row["image_path"],
                "sort_order": row["sort_order"],
                "image_type": row["image_type"],
            }
        )
    return rows


def replace_images(conn: sqlite3.Connection, car_id: str, images: Iterable[Dict[str, str]]) -> None:
    conn.execute("DELETE FROM car_images WHERE car_id=?", (car_id,))
    conn.executemany(
        "INSERT INTO car_images(car_id, image_path, sort_order, image_type) VALUES(?, ?, ?, ?)",
        [
            (
                car_id,
                image["image_path"],
                image.get("sort_order"),
                image.get("image_type"),
            )
            for image in images
        ],
    )
