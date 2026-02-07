from pathlib import Path

from ..query_list import (
    list_cars,
    list_cars_sorted_by_country,
    list_cars_sorted_by_drivetrain,
    list_cars_sorted_by_manufacturer,
    list_cars_sorted_by_max_power,
    list_cars_sorted_by_weight,
)


def list_cars_service(db_path: Path, locale: str, sort_by: str, limit: int):
    return list_cars(db_path, locale=locale, sort_by=sort_by, limit=limit)


__all__ = [
    "list_cars_service",
    "list_cars",
    "list_cars_sorted_by_manufacturer",
    "list_cars_sorted_by_country",
    "list_cars_sorted_by_drivetrain",
    "list_cars_sorted_by_max_power",
    "list_cars_sorted_by_weight",
]
