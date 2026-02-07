import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_node_playwright_script(engines_dir: Optional[Path]) -> Optional[str]:
    if engines_dir:
        candidate = engines_dir / "gt7-playwright"
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    repo_script = (
        Path(__file__).resolve().parents[2]
        / "engines"
        / "gt7_playwright"
        / "dist"
        / "cli.js"
    )
    if repo_script.exists() and repo_script.is_file():
        return str(repo_script)
    return None


def _run_node_json_lines(cmd: list[str], stdin_payload: str = "") -> list[Dict[str, Any]]:
    proc = subprocess.run(
        cmd,
        input=stdin_payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    out: list[Dict[str, Any]] = []
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        out.append(json.loads(text))
    return out


def _script_command(script: str) -> list[str]:
    if script.endswith(".js"):
        return ["node", script]
    return [script]


def extract_list_thumbs_with_node(
    script: str,
    locale: str,
    timeout: int,
    workers: int,
) -> Dict[str, list[str]]:
    cmd = [
        *_script_command(script),
        "--mode",
        "list-thumbs",
        "--locale",
        locale,
        "--timeout-ms",
        str(max(1, int(timeout)) * 1000),
        "--workers",
        str(max(1, int(workers))),
    ]
    rows = _run_node_json_lines(cmd)
    out: Dict[str, list[str]] = {}
    for row in rows:
        car_id = row.get("car_id")
        thumbs = row.get("thumb_images")
        if not car_id or not isinstance(thumbs, list):
            continue
        out[str(car_id)] = [str(x) for x in thumbs if isinstance(x, str)]
    return out


def extract_detail_with_node(
    script: str,
    car_id: str,
    locale: str,
    timeout: int,
    workers: int,
) -> Dict[str, Any]:
    cmd = [
        *_script_command(script),
        "--mode",
        "detail",
        "--locale",
        locale,
        "--timeout-ms",
        str(max(1, int(timeout)) * 1000),
        "--workers",
        str(max(1, int(workers))),
        "--car-id",
        car_id,
    ]
    rows = _run_node_json_lines(cmd)
    if not rows:
        return {}
    row = rows[0]
    if not row.get("ok"):
        return {}
    out: Dict[str, Any] = {}
    for key in ["name", "manufacturer_name", "intro", "detail"]:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    specs = row.get("specs")
    if isinstance(specs, list):
        parsed_specs = []
        for item in specs:
            if isinstance(item, list) and len(item) >= 2:
                parsed_specs.append((str(item[0]), str(item[1])))
        if parsed_specs:
            out["specs"] = parsed_specs
    heroes = row.get("hero_images")
    if isinstance(heroes, list):
        out["hero_images"] = [str(x) for x in heroes if isinstance(x, str)]
    thumbs = row.get("thumb_images")
    if isinstance(thumbs, list):
        out["thumb_images"] = [str(x) for x in thumbs if isinstance(x, str)]
    return out
