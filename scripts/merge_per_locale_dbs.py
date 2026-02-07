import argparse
import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Iterable, List


LOCALE_DB_PATTERN = re.compile(r"^gt7\.([a-zA-Z0-9_]+)\.db$")


def parse_locales(raw: str) -> List[str]:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    seen = set()
    out: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def discover_locales(out_dir: Path) -> List[str]:
    locales: List[str] = []
    for path in sorted(out_dir.glob("gt7.*.db"), key=lambda p: p.name):
        match = LOCALE_DB_PATTERN.match(path.name)
        if not match:
            continue
        locale = match.group(1)
        if locale == "":
            continue
        locales.append(locale)
    return locales


def table_exists(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    cur = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def merge_locale(conn: sqlite3.Connection, locale: str, src_db: Path, include_fetch_log: bool) -> None:
    conn.execute("ATTACH ? AS src", (str(src_db),))
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT OR IGNORE INTO manufacturers(id, name, logo_path, country_id) "
            "SELECT id, name, logo_path, country_id FROM src.manufacturers"
        )
        conn.execute(
            "INSERT OR IGNORE INTO manufacturer_i18n(id, locale, name) "
            "SELECT id, locale, name FROM src.manufacturer_i18n"
        )
        conn.execute(
            "INSERT OR IGNORE INTO aspiration_codes(code, default_name) "
            "SELECT code, default_name FROM src.aspiration_codes"
        )
        conn.execute(
            "INSERT OR IGNORE INTO drivetrain_codes(code, default_name) "
            "SELECT code, default_name FROM src.drivetrain_codes"
        )
        conn.execute(
            "INSERT OR IGNORE INTO cars("
            "id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json"
            ") "
            "SELECT id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json "
            "FROM src.cars"
        )

        conn.execute("DELETE FROM aspiration_i18n WHERE locale=?", (locale,))
        conn.execute(
            "INSERT INTO aspiration_i18n(code, locale, label) "
            "SELECT code, locale, label FROM src.aspiration_i18n WHERE locale=?",
            (locale,),
        )

        conn.execute("DELETE FROM drivetrain_i18n WHERE locale=?", (locale,))
        conn.execute(
            "INSERT INTO drivetrain_i18n(code, locale, label) "
            "SELECT code, locale, label FROM src.drivetrain_i18n WHERE locale=?",
            (locale,),
        )

        conn.execute("DELETE FROM spec_code_i18n WHERE locale=?", (locale,))
        conn.execute(
            "INSERT INTO spec_code_i18n(code, locale, label) "
            "SELECT code, locale, label FROM src.spec_code_i18n WHERE locale=?",
            (locale,),
        )

        conn.execute("DELETE FROM car_texts WHERE locale=?", (locale,))
        conn.execute(
            "INSERT INTO car_texts(car_id, locale, name, intro, detail) "
            "SELECT car_id, locale, name, intro, detail FROM src.car_texts WHERE locale=?",
            (locale,),
        )

        conn.execute("DELETE FROM car_specs WHERE locale=?", (locale,))
        conn.execute(
            "INSERT INTO car_specs(car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order) "
            "SELECT car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order "
            "FROM src.car_specs WHERE locale=?",
            (locale,),
        )

        if include_fetch_log:
            conn.execute("DELETE FROM fetch_log WHERE locale=?", (locale,))
            conn.execute(
                "INSERT INTO fetch_log(car_id, locale, status, message, updated_at) "
                "SELECT car_id, locale, status, message, updated_at FROM src.fetch_log WHERE locale=?",
                (locale,),
            )

        target_has_images = table_exists(conn, "main", "car_images")
        source_has_images = table_exists(conn, "src", "car_images")
        if target_has_images and source_has_images:
            conn.execute(
                "INSERT INTO car_images(car_id, image_path, sort_order, image_type) "
                "SELECT s.car_id, s.image_path, s.sort_order, s.image_type "
                "FROM src.car_images s "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM car_images d "
                "  WHERE d.car_id=s.car_id "
                "    AND d.image_path=s.image_path "
                "    AND COALESCE(d.image_type,'')=COALESCE(s.image_type,'')"
                ")"
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("DETACH src")


def normalize_locale_order(locales: Iterable[str], base_locale: str) -> List[str]:
    out: List[str] = []
    seen = set()
    if base_locale:
        out.append(base_locale)
        seen.add(base_locale)
    for locale in locales:
        if locale in seen:
            continue
        seen.add(locale)
        out.append(locale)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge per-locale DBs (gt7.<locale>.db) into one combined gt7.db without re-scraping."
    )
    parser.add_argument("--out-dir", default="./output", help="Directory containing per-locale DB files")
    parser.add_argument("--base-locale", default="gb", help="Base locale DB used as merge template")
    parser.add_argument(
        "--locales",
        default="",
        help="Comma-separated locales to merge. Empty means auto-discover from gt7.<locale>.db files.",
    )
    parser.add_argument(
        "--combined-db",
        default="",
        help="Output combined DB path. Empty = <out-dir>/gt7.db",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing combined DB if it already exists",
    )
    parser.add_argument(
        "--include-fetch-log",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include fetch_log rows from each locale DB (default: true)",
    )
    parser.add_argument(
        "--checkpoint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run WAL checkpoint(TRUNCATE) and set journal_mode=DELETE at end (default: true)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    combined_db = Path(args.combined_db) if args.combined_db else out_dir / "gt7.db"

    locales = parse_locales(args.locales) if args.locales else discover_locales(out_dir)
    if not locales:
        raise SystemExit("No locale DBs found. Provide --locales or place gt7.<locale>.db files in --out-dir.")

    if args.base_locale not in locales:
        raise SystemExit(
            f"Base locale '{args.base_locale}' is not in merge locales {locales}. "
            "Pass --locales including base locale or change --base-locale."
        )

    ordered_locales = normalize_locale_order(locales, args.base_locale)
    base_db = out_dir / f"gt7.{args.base_locale}.db"
    if not base_db.exists():
        raise SystemExit(f"Base DB not found: {base_db}")

    if combined_db.exists() and not args.overwrite:
        raise SystemExit(f"Combined DB already exists: {combined_db}. Use --overwrite to replace it.")
    combined_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_db, combined_db)

    conn = sqlite3.connect(combined_db)
    try:
        for locale in ordered_locales:
            if locale == args.base_locale:
                continue
            src_db = out_dir / f"gt7.{locale}.db"
            if not src_db.exists():
                raise SystemExit(f"Locale DB not found: {src_db}")
            merge_locale(
                conn=conn,
                locale=locale,
                src_db=src_db,
                include_fetch_log=bool(args.include_fetch_log),
            )

        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("build_base_locale", args.base_locale),
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("build_locales", json.dumps(ordered_locales, ensure_ascii=False)),
        )
        conn.commit()

        if args.checkpoint:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()
    finally:
        conn.close()

    print(
        f"merged locales={','.join(ordered_locales)} base={args.base_locale} "
        f"into {combined_db}"
    )


if __name__ == "__main__":
    main()
