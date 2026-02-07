import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def resolve_rust_spec_binary(engines_dir: Path | None) -> str | None:
    if engines_dir:
        base = engines_dir / "gt7-spec-normalizer"
        for candidate in (base, base.with_suffix(".exe")):
            if candidate.exists() and candidate.is_file():
                return str(candidate)
    path_bin = shutil.which("gt7-spec-normalizer")
    if path_bin:
        return path_bin
    repo_candidate = (
        Path(__file__).resolve().parents[3]
        / "engines"
        / "gt7_spec_normalizer"
        / "target"
        / "release"
        / "gt7-spec-normalizer"
    )
    for candidate in (repo_candidate, repo_candidate.with_suffix(".exe")):
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def normalize_specs_with_rust(
    binary: str,
    specs: Iterable[Tuple[str, str]],
    locale: str,
    mappings_dir: Path,
) -> List[Dict[str, object]]:
    payload = {
        "locale": locale,
        "specs": [[str(k), str(v)] for k, v in specs],
    }
    cmd = [
        binary,
        "--mappings-dir",
        str(mappings_dir),
    ]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    rows = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    if not isinstance(rows, list):
        raise RuntimeError("rust spec normalizer returned non-list output")
    out: List[Dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("spec_key")
        label = row.get("spec_label")
        if not key or not label:
            continue
        out.append(
            {
                "spec_key": str(key),
                "spec_label": str(label),
                "spec_value": str(row.get("spec_value", "")),
                "spec_unit": str(row.get("spec_unit", "")),
                "spec_raw": str(row.get("spec_raw", "")),
                "locale": str(row.get("locale", locale)),
                "sort_order": int(row.get("sort_order", 0) or 0),
            }
        )
    return out


def normalize_codes_with_rust(
    binary: str,
    locale: str,
    aspiration: Optional[str],
    aspiration_short: Optional[str],
    drivetrain: Optional[str],
) -> Dict[str, Optional[str]]:
    payload = {
        "locale": locale,
        "aspiration": aspiration or "",
        "aspiration_short": aspiration_short or "",
        "drivetrain": drivetrain or "",
    }
    cmd = [binary, "--mode", "codes"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    parsed = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("rust code normalizer returned non-dict output")
    return {
        "aspiration_code": str(parsed.get("aspiration_code", "") or "") or None,
        "aspiration_label": str(parsed.get("aspiration_label", "") or "") or None,
        "drivetrain_code": str(parsed.get("drivetrain_code", "") or "") or None,
        "drivetrain_label": str(parsed.get("drivetrain_label", "") or "") or None,
    }
