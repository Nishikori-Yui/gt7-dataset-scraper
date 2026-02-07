import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


def collect_reference_hero_counts(reference_images_dir: Path) -> Dict[str, int]:
    cars_root = reference_images_dir / "cars"
    if not cars_root.exists():
        return {}
    out: Dict[str, int] = {}
    for car_dir in sorted(cars_root.iterdir(), key=lambda item: item.name):
        if not car_dir.is_dir():
            continue
        hero_count = 0
        for item in car_dir.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if "_hero_" in name and "." in name:
                hero_count += 1
        out[car_dir.name] = hero_count
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate hero expected-count manifest JSON from reference images directory."
    )
    parser.add_argument(
        "--reference-images-dir",
        default="./output/reference/images",
        help="Reference images root containing cars/<car_id> directories",
    )
    parser.add_argument(
        "--out",
        default="./gt7_scraper/mappings/hero_expected_counts.json",
        help="Output manifest file path",
    )
    args = parser.parse_args()

    reference_dir = Path(args.reference_images_dir)
    counts = collect_reference_hero_counts(reference_dir)
    if not counts:
        raise SystemExit(f"No hero counts found under {reference_dir}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(reference_dir),
        "counts": dict(sorted(counts.items())),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(counts)} rows to {out_path}")


if __name__ == "__main__":
    main()
