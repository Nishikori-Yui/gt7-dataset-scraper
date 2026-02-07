import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..backends.go_backend import run_go_backend
from ..backends.python_backend import run_python_backend
from ..query_stats import dump_json


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
        choices=["auto", "python", "go"],
        default="auto",
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


def resolve_backend(args: argparse.Namespace) -> str:
    if args.query_engine in {"python", "go"}:
        return args.query_engine
    return "go"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    selected_backend = resolve_backend(args)
    if selected_backend == "go":
        try:
            data = run_go_backend(args)
            write_output(data, args.format, args.out)
            return
        except Exception as exc:
            print(f"warning: {exc}; falling back to python query backend", file=sys.stderr)

    data = run_python_backend(args)
    write_output(data, args.format, args.out)


if __name__ == "__main__":
    main()
