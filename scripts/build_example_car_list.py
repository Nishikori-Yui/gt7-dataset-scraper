import argparse
from pathlib import Path
import sqlite3


def build_example_list(db_path: Path, out_path: Path) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT manufacturer_id, MIN(id) AS car_id "
            "FROM cars WHERE manufacturer_id IS NOT NULL "
            "GROUP BY manufacturer_id ORDER BY manufacturer_id"
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for _, car_id in rows:
            f.write(f"{car_id}\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build example car id list (one car per manufacturer)."
    )
    parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    parser.add_argument("--out", default="./output/example_car_ids.txt", help="Output file path")
    args = parser.parse_args()

    exit_code = build_example_list(Path(args.db), Path(args.out))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
