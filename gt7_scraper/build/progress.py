from dataclasses import dataclass
from typing import Optional

from tqdm import tqdm


@dataclass
class PlanRecord:
    locale: str
    planned_total: int
    site_total: Optional[int]


class TotalProgress:
    def __init__(self, desc: str = "Total") -> None:
        self._bar = tqdm(total=0, desc=desc, position=0, leave=True)
        self._planned = 0

    @property
    def planned_total(self) -> int:
        return self._planned

    def add_plan(self, locale: str, planned_total: int, site_total: Optional[int]) -> PlanRecord:
        planned = max(0, int(planned_total))
        self._planned += planned
        self._bar.total = self._planned
        self._bar.refresh()
        record = PlanRecord(locale=locale, planned_total=planned, site_total=site_total)
        self._bar.write(
            f"plan locale={record.locale} planned_total={record.planned_total} "
            f"site_total={record.site_total if record.site_total is not None else 'n/a'}"
        )
        return record

    def tick(self, delta: int = 1) -> None:
        self._bar.update(max(0, int(delta)))

    def close(self) -> None:
        self._bar.close()
