import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def connect_db(path: Path) -> sqlite3.Connection:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


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
    # Add missing columns for existing DBs
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
    conn.commit()


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


def log_fetch(conn: sqlite3.Connection, car_id: str, locale: str, status: str, message: str, updated_at: str) -> None:
    conn.execute(
        "INSERT INTO fetch_log(car_id, locale, status, message, updated_at) VALUES(?, ?, ?, ?, ?)",
        (car_id, locale, status, message, updated_at),
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


def cleanup_descriptions(conn: sqlite3.Connection) -> None:
    migrate_cars_table(conn)
    migrate_car_texts_table(conn)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _has_non_null_values(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(
        f"SELECT COUNT(*) as cnt FROM {table} WHERE {column} IS NOT NULL AND {column} != ''"
    )
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


def replace_country_i18n(conn: sqlite3.Connection, mapping: Dict[str, Dict[str, str]]) -> None:
    conn.execute("DELETE FROM country_i18n")
    rows = []
    for iso3, locales in mapping.items():
        for locale, name in locales.items():
            rows.append((iso3, locale, name))
    if rows:
        conn.executemany(
            "INSERT INTO country_i18n(iso3, locale, name) VALUES(?, ?, ?)",
            rows,
        )
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
        "DELETE FROM aspiration_i18n WHERE code NOT IN ({}) OR code='---'".format(
            ",".join("?" * len(valid_asp))
        ),
        tuple(valid_asp),
    )
    conn.execute(
        "DELETE FROM drivetrain_i18n WHERE code NOT IN ({}) OR code='---'".format(
            ",".join("?" * len(valid_drive))
        ),
        tuple(valid_drive),
    )
    conn.execute(
        "DELETE FROM aspiration_codes WHERE code NOT IN ({})".format(
            ",".join("?" * len(valid_asp))
        ),
        tuple(valid_asp),
    )
    conn.execute(
        "DELETE FROM drivetrain_codes WHERE code NOT IN ({})".format(
            ",".join("?" * len(valid_drive))
        ),
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
