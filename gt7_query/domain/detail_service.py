from pathlib import Path

from ..query_detail import get_car_details


def get_car_details_service(db_path: Path, car_id: str, locale: str):
    return get_car_details(db_path, car_id, locale=locale)


__all__ = ["get_car_details_service", "get_car_details"]
