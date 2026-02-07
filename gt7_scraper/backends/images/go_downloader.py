import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def resolve_downloader_binary(engines_dir: Optional[Path]) -> Optional[str]:
    if engines_dir:
        candidate = engines_dir / "gt7-downloader"
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    repo_candidate = (
        Path(__file__).resolve().parents[3]
        / "engines"
        / "gt7_downloader"
        / "gt7-downloader"
    )
    if repo_candidate.exists() and repo_candidate.is_file():
        return str(repo_candidate)
    path_bin = shutil.which("gt7-downloader")
    if path_bin:
        return path_bin
    return None


def run_downloader_jobs(
    binary: str,
    image_dir: Path,
    jobs: List[Dict[str, object]],
    workers: int,
    timeout: int,
    retries: int,
) -> Dict[str, Dict[str, object]]:
    if not jobs:
        return {}
    cmd = [
        binary,
        "--base-dir",
        str(image_dir),
        "--workers",
        str(max(1, int(workers))),
        "--timeout",
        str(max(1, int(timeout))),
        "--retries",
        str(max(0, int(retries))),
    ]
    payload = "\n".join(json.dumps(job, ensure_ascii=True) for job in jobs) + "\n"
    proc = subprocess.run(
        cmd,
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    out: Dict[str, Dict[str, object]] = {}
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        job_id = str(item.get("job_id", ""))
        if not job_id:
            continue
        out[job_id] = item
    return out
