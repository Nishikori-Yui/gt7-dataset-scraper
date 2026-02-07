import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_catalog_binary(engines_dir: Optional[Path]) -> Optional[str]:
    if not engines_dir:
        return None
    candidate = Path(engines_dir) / "gt7-catalog-go"
    if candidate.exists():
        return str(candidate)
    return None


def parse_detail_with_go(binary: str, html: str, car_id: Optional[str]) -> Dict[str, Any]:
    payload = {"html": html, "car_id": car_id or ""}
    proc = subprocess.run(
        [binary],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"gt7-catalog-go failed rc={proc.returncode}: {detail}")
    output = (proc.stdout or "").strip()
    if not output:
        return {}
    parsed = json.loads(output)
    if isinstance(parsed, dict):
        return parsed
    return {}
