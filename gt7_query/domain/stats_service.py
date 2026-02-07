from pathlib import Path

from ..query_stats import stats_by_country, stats_by_drivetrain, stats_by_manufacturer


def stats_service(db_path: Path, locale: str, group_by: str):
    if group_by == "manufacturer":
        return stats_by_manufacturer(db_path, locale=locale)
    if group_by == "country":
        return stats_by_country(db_path, locale=locale)
    return stats_by_drivetrain(db_path, locale=locale)


__all__ = ["stats_service", "stats_by_manufacturer", "stats_by_country", "stats_by_drivetrain"]
