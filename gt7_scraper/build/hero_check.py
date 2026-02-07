import csv
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def load_hero_expected_counts(manifest_path: Path) -> Dict[str, int]:
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    source: Dict[str, object]
    if isinstance(payload, dict) and isinstance(payload.get("counts"), dict):
        source = payload["counts"]
    elif isinstance(payload, dict):
        source = payload
    else:
        return {}
    out: Dict[str, int] = {}
    for car_id, value in source.items():
        try:
            out[str(car_id)] = int(value)
        except Exception:
            continue
    return out


def collect_db_hero_counts(db_path: Path) -> Tuple[List[str], Dict[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        car_ids = [row[0] for row in cur.execute("SELECT id FROM cars")]
        table_exists = (
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1").fetchone()
            is not None
        )
        if not table_exists:
            return car_ids, {}
        hero_map: Dict[str, int] = {}
        for car_id, count in cur.execute(
            "SELECT car_id, COUNT(*) FROM car_images WHERE image_type='hero' GROUP BY car_id"
        ):
            hero_map[str(car_id)] = int(count)
        return car_ids, hero_map
    finally:
        conn.close()


def validate_hero_counts(
    db_path: Path,
    reference_counts: Dict[str, int],
    hero_min: int,
) -> Tuple[int, List[Dict[str, object]]]:
    car_ids, hero_counts = collect_db_hero_counts(db_path)
    diffs: List[Dict[str, object]] = []
    for car_id in car_ids:
        actual = hero_counts.get(car_id, 0)
        expected = reference_counts.get(car_id)
        if expected is not None:
            if actual != expected:
                diffs.append(
                    {
                        "db": db_path.name,
                        "car_id": car_id,
                        "expected": expected,
                        "actual": actual,
                        "reason": "mismatch_with_reference",
                    }
                )
            continue
        if actual < hero_min:
            diffs.append(
                {
                    "db": db_path.name,
                    "car_id": car_id,
                    "expected": f">={hero_min}",
                    "actual": actual,
                    "reason": "below_min_without_reference",
                }
            )
    return len(car_ids), diffs


def evaluate_hero_check_outcome(
    mode: str,
    checked_rows: int,
    mismatch_rows: int,
    soft_max_ratio: float,
    soft_max_count: int,
) -> Tuple[bool, str, float]:
    ratio = (float(mismatch_rows) / float(checked_rows)) if checked_rows > 0 else 0.0
    if mode == "strict":
        should_fail = mismatch_rows > 0
        threshold = "strict(any mismatch)"
        return should_fail, threshold, ratio
    if mode == "soft":
        should_fail = mismatch_rows > soft_max_count and ratio > soft_max_ratio
        threshold = f"soft(count>{soft_max_count} AND ratio>{soft_max_ratio:.6f})"
        return should_fail, threshold, ratio
    return False, "off", ratio


def write_hero_diff_reports(out_dir: Path, diffs: List[Dict[str, object]]) -> None:
    json_path = out_dir / "hero_diff.json"
    csv_path = out_dir / "hero_diff.csv"
    json_path.write_text(json.dumps(diffs, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["db", "car_id", "expected", "actual", "reason"])
        writer.writeheader()
        for row in diffs:
            writer.writerow(row)
