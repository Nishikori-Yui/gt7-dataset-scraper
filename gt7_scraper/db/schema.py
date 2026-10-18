import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional


def connect_db(path: Path) -> sqlite3.Connection:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def configure_sqlite(conn: sqlite3.Connection, use_wal: bool = False) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    if use_wal:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    conn.commit()


def init_db(conn: sqlite3.Connection, create_images: bool = True) -> None:
    cur = conn.cursor()
    script = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS manufacturers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        logo_path TEXT,
        country_id TEXT
    );

    CREATE TABLE IF NOT EXISTS manufacturer_i18n (
        id TEXT NOT NULL,
        locale TEXT NOT NULL,
        name TEXT NOT NULL,
        PRIMARY KEY (id, locale),
        FOREIGN KEY (id) REFERENCES manufacturers(id)
    );

    CREATE TABLE IF NOT EXISTS cars (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        manufacturer_id TEXT,
        aspiration_code TEXT,
        drivetrain_code TEXT,
        intro TEXT,
        detail TEXT,
        car_class TEXT,
        pp TEXT,
        year TEXT,
        raw_json TEXT,
        FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
    );

    CREATE TABLE IF NOT EXISTS aspiration_codes (
        code TEXT PRIMARY KEY,
        default_name TEXT
    );

    CREATE TABLE IF NOT EXISTS aspiration_i18n (
        code TEXT NOT NULL,
        locale TEXT NOT NULL,
        label TEXT,
        PRIMARY KEY (code, locale),
        FOREIGN KEY (code) REFERENCES aspiration_codes(code)
    );

    CREATE TABLE IF NOT EXISTS drivetrain_codes (
        code TEXT PRIMARY KEY,
        default_name TEXT
    );

    CREATE TABLE IF NOT EXISTS drivetrain_i18n (
        code TEXT NOT NULL,
        locale TEXT NOT NULL,
        label TEXT,
        PRIMARY KEY (code, locale),
        FOREIGN KEY (code) REFERENCES drivetrain_codes(code)
    );

    CREATE TABLE IF NOT EXISTS car_specs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car_id TEXT NOT NULL,
        locale TEXT NOT NULL DEFAULT 'us',
        spec_key TEXT NOT NULL,
        spec_value TEXT,
        spec_unit TEXT,
        spec_raw TEXT,
        sort_order INTEGER,
        FOREIGN KEY (car_id) REFERENCES cars(id)
    );

    CREATE TABLE IF NOT EXISTS spec_code_i18n (
        code TEXT NOT NULL,
        locale TEXT NOT NULL,
        label TEXT NOT NULL,
        PRIMARY KEY (code, locale)
    );

    CREATE TABLE IF NOT EXISTS car_texts (
        car_id TEXT NOT NULL,
        locale TEXT NOT NULL,
        name TEXT,
        intro TEXT,
        detail TEXT,
        PRIMARY KEY (car_id, locale),
        FOREIGN KEY (car_id) REFERENCES cars(id)
    );

    CREATE TABLE IF NOT EXISTS fetch_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car_id TEXT NOT NULL,
        locale TEXT NOT NULL DEFAULT 'us',
        status TEXT NOT NULL,
        message TEXT,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS country_iso_map (
        country_id TEXT PRIMARY KEY,
        iso3 TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS country_i18n (
        iso3 TEXT NOT NULL,
        locale TEXT NOT NULL,
        name TEXT NOT NULL,
        PRIMARY KEY (iso3, locale)
    );
    """
    if create_images:
        script += """
        CREATE TABLE IF NOT EXISTS car_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id TEXT NOT NULL,
            image_path TEXT NOT NULL,
            sort_order INTEGER,
            image_type TEXT,
            FOREIGN KEY (car_id) REFERENCES cars(id)
        );
        """
    cur.executescript(script)

    manufacturer_columns = {row[1] for row in cur.execute("PRAGMA table_info(manufacturers)")}
    if "country_id" not in manufacturer_columns:
        cur.execute("ALTER TABLE manufacturers ADD COLUMN country_id TEXT")
    columns = {row[1] for row in cur.execute("PRAGMA table_info(cars)")}
    if "aspiration_code" not in columns:
        cur.execute("ALTER TABLE cars ADD COLUMN aspiration_code TEXT")
    if "drivetrain_code" not in columns:
        cur.execute("ALTER TABLE cars ADD COLUMN drivetrain_code TEXT")
    if "intro" not in columns:
        cur.execute("ALTER TABLE cars ADD COLUMN intro TEXT")
    if "detail" not in columns:
        cur.execute("ALTER TABLE cars ADD COLUMN detail TEXT")
    spec_columns = {row[1] for row in cur.execute("PRAGMA table_info(car_specs)")}
    if "locale" not in spec_columns:
        cur.execute("ALTER TABLE car_specs ADD COLUMN locale TEXT NOT NULL DEFAULT 'us'")
    log_columns = {row[1] for row in cur.execute("PRAGMA table_info(fetch_log)")}
    if "locale" not in log_columns:
        cur.execute("ALTER TABLE fetch_log ADD COLUMN locale TEXT NOT NULL DEFAULT 'us'")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_fetch_log_car_locale_id ON fetch_log(car_id, locale, id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fetch_log_locale_status ON fetch_log(locale, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_car_specs_car_locale_sort ON car_specs(car_id, locale, sort_order)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_car_specs_locale_key ON car_specs(locale, spec_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_car_texts_locale_car ON car_texts(locale, car_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manufacturer_i18n_locale_id ON manufacturer_i18n(locale, id)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_manufacturers_country_id ON manufacturers(country_id)")
    has_car_images_table = (
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1").fetchone()
        is not None
    )
    if has_car_images_table:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_car_images_car_type_sort ON car_images(car_id, image_type, sort_order)")
    conn.commit()


def cleanup_descriptions(conn: sqlite3.Connection) -> None:
    migrate_cars_table(conn)
    migrate_car_texts_table(conn)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _has_non_null_values(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE {column} IS NOT NULL AND {column} != ''")
    return int(cur.fetchone()["cnt"]) > 0


def migrate_cars_table(conn: sqlite3.Connection) -> None:
    has_country = _has_column(conn, "cars", "country")
    has_description = _has_column(conn, "cars", "description")
    keep_description = has_description and _has_non_null_values(conn, "cars", "description")
    if not has_country and not has_description:
        return
    if not has_country and has_description and keep_description:
        return
    if not has_country and has_description and not keep_description:
        drop_cars_description(conn)
        return
    rebuild_cars_table(conn, keep_description=keep_description)


def migrate_car_texts_table(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "car_texts", "description"):
        return
    keep_description = _has_non_null_values(conn, "car_texts", "description")
    if keep_description:
        return
    drop_car_texts_description(conn)


def rebuild_cars_table(conn: sqlite3.Connection, keep_description: bool) -> None:
    columns = [
        "id",
        "name",
        "manufacturer_id",
        "aspiration_code",
        "drivetrain_code",
        "intro",
        "detail",
        "car_class",
        "pp",
        "year",
        "raw_json",
    ]
    if keep_description:
        columns.insert(7, "description")
    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE cars_new (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            manufacturer_id TEXT,
            aspiration_code TEXT,
            drivetrain_code TEXT,
            intro TEXT,
            detail TEXT,
            {"description TEXT," if keep_description else ""}
            car_class TEXT,
            pp TEXT,
            year TEXT,
            raw_json TEXT,
            FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
        );
        INSERT INTO cars_new({",".join(columns)}) SELECT {",".join(columns)} FROM cars;
        DROP TABLE cars;
        ALTER TABLE cars_new RENAME TO cars;
        PRAGMA foreign_keys = ON;
        """
    )
    conn.commit()


def drop_cars_description(conn: sqlite3.Connection) -> None:
    rebuild_cars_table(conn, keep_description=False)


def drop_car_texts_description(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE car_texts_new (
            car_id TEXT NOT NULL,
            locale TEXT NOT NULL,
            name TEXT,
            intro TEXT,
            detail TEXT,
            PRIMARY KEY (car_id, locale),
            FOREIGN KEY (car_id) REFERENCES cars(id)
        );
        INSERT INTO car_texts_new(car_id, locale, name, intro, detail)
        SELECT car_id, locale, name, intro, detail FROM car_texts;
        DROP TABLE car_texts;
        ALTER TABLE car_texts_new RENAME TO car_texts;
        PRAGMA foreign_keys = ON;
        """
    )
    conn.commit()


def replace_country_iso_map(conn: sqlite3.Connection, mapping: Dict[str, str]) -> None:
    conn.execute("DELETE FROM country_iso_map")
    conn.executemany(
        "INSERT INTO country_iso_map(country_id, iso3) VALUES(?, ?)",
        [(country_id, iso3) for country_id, iso3 in mapping.items()],
    )
    conn.commit()


def replace_country_i18n(
    conn: sqlite3.Connection,
    mapping: Dict[str, Dict[str, str]],
    locale: Optional[str] = None,
    fallback_locale: str = "gb",
) -> None:
    conn.execute("DELETE FROM country_i18n")
    rows = []
    if locale:
        for iso3, locales in mapping.items():
            name = locales.get(locale) or locales.get(fallback_locale)
            if name:
                rows.append((iso3, locale, name))
    else:
        for iso3, locales in mapping.items():
            for locale_key, name in locales.items():
                rows.append((iso3, locale_key, name))
    if rows:
        conn.executemany("INSERT INTO country_i18n(iso3, locale, name) VALUES(?, ?, ?)", rows)
    conn.commit()


def backfill_manufacturer_country_from_raw_json(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT id, manufacturer_id, raw_json FROM cars")
    mapping: Dict[str, str] = {}
    for row in cur.fetchall():
        raw = row["raw_json"]
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        country_id = data.get("countryId")
        manufacturer_id = row["manufacturer_id"]
        if not country_id or not manufacturer_id:
            continue
        if manufacturer_id in mapping:
            continue
        mapping[manufacturer_id] = country_id
    if not mapping:
        return
    conn.executemany(
        "UPDATE manufacturers SET country_id=? WHERE id=?",
        [(country_id, manufacturer_id) for manufacturer_id, country_id in mapping.items()],
    )
    conn.commit()


def cleanup_spec_labels(conn: sqlite3.Connection, locale: str) -> None:
    conn.execute("DELETE FROM spec_code_i18n WHERE code LIKE 'raw_%' AND locale=?", (locale,))
    conn.commit()


def cleanup_aspiration_drivetrain(conn: sqlite3.Connection, locale: str) -> None:
    valid_asp = {"NA", "TC", "SC", "EV", "HV", "TC+SC"}
    valid_drive = {"FR", "FF", "MR", "RR", "4WD", "AWD"}
    conn.execute(
        "DELETE FROM aspiration_i18n WHERE code NOT IN ({}) OR code='---'".format(",".join("?" * len(valid_asp))),
        tuple(valid_asp),
    )
    conn.execute(
        "DELETE FROM drivetrain_i18n WHERE code NOT IN ({}) OR code='---'".format(",".join("?" * len(valid_drive))),
        tuple(valid_drive),
    )
    conn.execute(
        "DELETE FROM aspiration_codes WHERE code NOT IN ({})".format(",".join("?" * len(valid_asp))),
        tuple(valid_asp),
    )
    conn.execute(
        "DELETE FROM drivetrain_codes WHERE code NOT IN ({})".format(",".join("?" * len(valid_drive))),
        tuple(valid_drive),
    )
    conn.commit()


def sync_manufacturers_from_i18n(conn: sqlite3.Connection, locale: str) -> None:
    conn.execute(
        "UPDATE manufacturers SET name=(SELECT name FROM manufacturer_i18n mi WHERE mi.id=manufacturers.id AND mi.locale=?)"
        " WHERE EXISTS (SELECT 1 FROM manufacturer_i18n mi WHERE mi.id=manufacturers.id AND mi.locale=?)",
        (locale, locale),
    )
    conn.commit()
