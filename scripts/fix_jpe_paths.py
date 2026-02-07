#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path
from typing import List, Tuple


def rename_jpe_files(images_dir: Path) -> Tuple[int, int]:
    renamed = 0
    removed_duplicates = 0
    for path in images_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".jpe":
            continue
        target = path.with_suffix(".jpg")
        if target.exists():
            path.unlink()
            removed_duplicates += 1
            continue
        path.rename(target)
        renamed += 1
    return renamed, removed_duplicates


def update_db_paths(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1"
        ).fetchone()
        if not table_exists:
            return 0
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM car_images WHERE lower(image_path) LIKE '%.jpe'"
            ).fetchone()[0]
        )
        if count > 0:
            conn.execute(
                "UPDATE car_images "
                "SET image_path=substr(image_path, 1, length(image_path)-4) || '.jpg' "
                "WHERE lower(image_path) LIKE '%.jpe'"
            )
            conn.commit()
        return count
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename .jpe images to .jpg and update DB image paths.")
    parser.add_argument("--output-dir", default="./output", help="Output directory containing images and DB files")
    parser.add_argument(
        "--images-dir",
        default=None,
        help="Images directory to fix (default: <output-dir>/images)",
    )
    parser.add_argument(
        "--db-glob",
        default="*.db",
        help="DB glob pattern under output dir (default: *.db)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    images_dir = Path(args.images_dir).resolve() if args.images_dir else output_dir / "images"
    db_paths: List[Path] = sorted(output_dir.glob(args.db_glob))

    renamed, removed_duplicates = rename_jpe_files(images_dir) if images_dir.exists() else (0, 0)
    updated_rows = 0
    touched_dbs = 0
    for db_path in db_paths:
        count = update_db_paths(db_path)
        if count > 0:
            touched_dbs += 1
            updated_rows += count

    print(
        "fix_jpe_paths summary: "
        f"images_dir={images_dir} "
        f"renamed={renamed} "
        f"duplicates_removed={removed_duplicates} "
        f"dbs_checked={len(db_paths)} "
        f"dbs_updated={touched_dbs} "
        f"rows_updated={updated_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
