import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def run_rust_hero_check(
    binary: Path,
    db_paths: List[Path],
    manifest_path: Path,
    hero_min: int,
) -> Tuple[bool, str, int, List[Dict[str, object]]]:
    if not binary.exists():
        exe_binary = binary.with_suffix(".exe")
        if exe_binary.exists():
            binary = exe_binary
        else:
            return False, f"rust hero-check binary not found: {binary}", 0, []
    cmd = [
        str(binary),
        "--manifest",
        str(manifest_path),
        "--hero-min",
        str(hero_min),
    ]
    for path in db_paths:
        cmd.extend(["--db", str(path)])
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return False, f"rust hero-check execution failed: {exc}", 0, []

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"rust hero-check failed rc={proc.returncode}: {detail}", 0, []
    text = (proc.stdout or "").strip()
    if not text:
        return False, "rust hero-check returned empty payload", 0, []
    try:
        payload = json.loads(text)
    except Exception as exc:
        return False, f"rust hero-check invalid json: {exc}", 0, []
    checked_rows = int(payload.get("checked_rows", 0))
    diffs_raw = payload.get("diffs", [])
    diffs: List[Dict[str, object]] = []
    if isinstance(diffs_raw, list):
        for row in diffs_raw:
            if isinstance(row, dict):
                diffs.append(row)
    return True, "rust hero-check ok", checked_rows, diffs
