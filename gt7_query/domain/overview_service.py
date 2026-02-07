from pathlib import Path

from ..query_stats import overview_stats


def overview_service(db_path: Path):
    return overview_stats(db_path)


__all__ = ["overview_service", "overview_stats"]
