import sqlite3
from typing import Optional


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    cur = conn.execute("SELECT value FROM meta WHERE key=?", (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def log_fetch(conn: sqlite3.Connection, car_id: str, locale: str, status: str, message: str, updated_at: str) -> None:
    conn.execute(
        "INSERT INTO fetch_log(car_id, locale, status, message, updated_at) VALUES(?, ?, ?, ?, ?)",
        (car_id, locale, status, message, updated_at),
    )


def latest_status(conn: sqlite3.Connection, car_id: str, locale: str) -> Optional[str]:
    cur = conn.execute(
        "SELECT status FROM fetch_log WHERE car_id=? AND locale=? ORDER BY id DESC LIMIT 1",
        (car_id, locale),
    )
    row = cur.fetchone()
    return row["status"] if row else None


def count_cars(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) as cnt FROM cars")
    return int(cur.fetchone()["cnt"])
