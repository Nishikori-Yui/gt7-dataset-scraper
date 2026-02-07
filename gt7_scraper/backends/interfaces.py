from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple


class CatalogBackend(Protocol):
    def parse_detail(self, html: str, car_id: Optional[str]) -> Dict[str, Any]: ...

    def parse_list_thumbs(self, html: str) -> Dict[str, List[str]]: ...

    def parse_chunk(self, js_text: str, chunk_type: str) -> Any: ...


class SpecBackend(Protocol):
    def normalize_specs(self, specs: List[Tuple[str, str]], locale: str, mappings_dir: Path) -> List[Dict[str, object]]: ...

    def normalize_codes(
        self,
        locale: str,
        aspiration: Optional[str],
        aspiration_short: Optional[str],
        drivetrain: Optional[str],
    ) -> Dict[str, Optional[str]]: ...


class ImageBackend(Protocol):
    def run_jobs(
        self,
        image_dir: Path,
        jobs: List[Dict[str, object]],
        workers: int,
        timeout: int,
        retries: int,
    ) -> Dict[str, Dict[str, object]]: ...


class QueryBackend(Protocol):
    def run(self, command: str, args: Dict[str, Any]) -> Any: ...
