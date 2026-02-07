from argparse import Namespace
from pathlib import Path
from typing import Any

from ..domain.detail_service import get_car_details_service
from ..domain.list_service import list_cars_service
from ..domain.overview_service import overview_service
from ..domain.stats_service import stats_service


def run_python_backend(args: Namespace) -> Any:
    if args.command == "list":
        return list_cars_service(Path(args.db), locale=args.locale, sort_by=args.sort, limit=args.limit)
    if args.command == "car":
        return get_car_details_service(Path(args.db), args.car_id, locale=args.locale)
    if args.command == "stats":
        return stats_service(Path(args.db), locale=args.locale, group_by=args.by)
    if args.command == "overview":
        return overview_service(Path(args.db))
    raise RuntimeError(f"Unsupported command: {args.command}")
