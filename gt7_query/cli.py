import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from .queries import (
    dump_json,
    get_car_details,
    list_cars,
    overview_stats,
    stats_by_country,
    stats_by_drivetrain,
    stats_by_manufacturer,
)


def write_output(data: Any, fmt: str, out_path: str) -> None:
    if fmt == "json":
        text = dump_json(data)
    else:
        text = format_text(data)
    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def format_text(data: Any) -> str:
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, dict):
                if "id" in item and "name" in item and len(item) == 2:
                    lines.append(f"{item['id']}\t{item['name']}")
                elif "label" in item and "count" in item:
                    lines.append(f"{item['label']}\t{item['count']}")
                else:
                    lines.append(dump_json(item))
            else:
                lines.append(str(item))
        return "\n".join(lines)
    return str(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GT7 database query CLI")
    parser.add_argument(
        "--query-engine",
        choices=["python", "go"],
        default="python",
        help="Query backend",
    )
    parser.add_argument(
        "--query-go-bin",
        default="./local/bin/gt7-query-go",
        help="Go query backend binary path",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List cars")
    list_parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    list_parser.add_argument("--locale", default="gb", help="Locale for output and sorting")
    list_parser.add_argument(
        "--sort",
        default="manufacturer",
        choices=["manufacturer", "country", "drivetrain", "max_power", "weight"],
        help="Sort by",
    )
    list_parser.add_argument("--limit", type=int, default=0, help="Limit number of rows")
    list_parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")
    list_parser.add_argument("--out", default="", help="Output file path")

    car_parser = sub.add_parser("car", help="Get car details")
    car_parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    car_parser.add_argument("--locale", default="gb", help="Locale for output")
    car_parser.add_argument("--car-id", required=True, help="Car id")
    car_parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")
    car_parser.add_argument("--out", default="", help="Output file path")

    stats_parser = sub.add_parser("stats", help="Aggregate stats")
    stats_parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    stats_parser.add_argument("--locale", default="gb", help="Locale for output")
    stats_parser.add_argument(
        "--by",
        required=True,
        choices=["manufacturer", "country", "drivetrain"],
        help="Group by",
    )
    stats_parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")
    stats_parser.add_argument("--out", default="", help="Output file path")

    overview_parser = sub.add_parser("overview", help="Database overview")
    overview_parser.add_argument("--db", default="./output/gt7.db", help="SQLite DB path")
    overview_parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")
    overview_parser.add_argument("--out", default="", help="Output file path")

    return parser


def run_go_backend(args: argparse.Namespace) -> Any:
    if args.command == "car":
        raise RuntimeError("go query backend for 'car' is not parity-validated yet")
    if args.command == "list" and args.sort in {"max_power", "weight"}:
        raise RuntimeError("go query backend for list sort=max_power/weight is not parity-validated yet")

    command = [args.query_go_bin, args.command, "--db", args.db]
    if args.command == "list":
        command.extend(["--locale", args.locale, "--sort", args.sort, "--limit", str(args.limit)])
    elif args.command == "car":
        command.extend(["--locale", args.locale, "--car-id", args.car_id])
    elif args.command == "stats":
        command.extend(["--locale", args.locale, "--by", args.by])
    elif args.command == "overview":
        pass
    else:
        raise RuntimeError(f"Unsupported command for go backend: {args.command}")

    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"go query backend failed rc={proc.returncode}: {detail}")
    payload = (proc.stdout or "").strip()
    if not payload:
        raise RuntimeError("go query backend returned empty payload")
    try:
        return json.loads(payload)
    except Exception as exc:
        raise RuntimeError(f"go query backend returned invalid json: {exc}") from exc


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.query_engine == "go":
        try:
            data = run_go_backend(args)
            write_output(data, args.format, args.out)
            return
        except Exception as exc:
            print(f"warning: {exc}; falling back to python query backend", file=sys.stderr)

    if args.command == "list":
        data = list_cars(Path(args.db), locale=args.locale, sort_by=args.sort, limit=args.limit)
        write_output(data, args.format, args.out)
        return

    if args.command == "car":
        data = get_car_details(Path(args.db), args.car_id, locale=args.locale)
        write_output(data, args.format, args.out)
        return

    if args.command == "stats":
        if args.by == "manufacturer":
            data = stats_by_manufacturer(Path(args.db), locale=args.locale)
        elif args.by == "country":
            data = stats_by_country(Path(args.db), locale=args.locale)
        else:
            data = stats_by_drivetrain(Path(args.db), locale=args.locale)
        write_output(data, args.format, args.out)
        return

    if args.command == "overview":
        data = overview_stats(Path(args.db))
        write_output(data, args.format, args.out)
        return


if __name__ == "__main__":
    main()
