import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def resolve_catalog_binary(engines_dir: Optional[Path]) -> Optional[str]:
    if not engines_dir:
        return None
    base = Path(engines_dir) / "gt7-catalog-go"
    for candidate in (base, base.with_suffix(".exe")):
        if candidate.exists():
            return str(candidate)
    return None


def _run_catalog_go(binary: str, payload: Dict[str, Any]) -> Any:
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
        return None
    return json.loads(output)


def parse_detail_with_go(binary: str, html: str, car_id: Optional[str]) -> Dict[str, Any]:
    parsed = _run_catalog_go(
        binary,
        {
            "mode": "detail",
            "html": html,
            "car_id": car_id or "",
        },
    )
    if isinstance(parsed, dict):
        return parsed
    return {}


def parse_list_thumbs_with_go(binary: str, html: str) -> Dict[str, List[str]]:
    parsed = _run_catalog_go(
        binary,
        {
            "mode": "list-thumbs",
            "html": html,
        },
    )
    if not isinstance(parsed, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for key, value in parsed.items():
        if not isinstance(value, list):
            continue
        urls = [str(item) for item in value if item]
        if urls:
            out[str(key)] = urls
    return out


def parse_chunk_with_go(binary: str, js_text: str, chunk_type: str) -> Any:
    return _run_catalog_go(
        binary,
        {
            "mode": "chunk-parse",
            "js": js_text,
            "chunk_type": chunk_type,
        },
    )
