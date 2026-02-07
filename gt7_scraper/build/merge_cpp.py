import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def run_cpp_merge(
    binary: Path,
    out_dir: Path,
    base_locale: str,
    locales: List[str],
    combined_db: Path,
    include_fetch_log: bool,
    checkpoint: bool,
    timeout: Optional[int] = None,
) -> Tuple[bool, str]:
    if not binary.exists():
        exe_binary = binary.with_suffix(".exe")
        if exe_binary.exists():
            binary = exe_binary
        else:
            return False, f"cpp merge binary not found: {binary}"

    cmd = [
        str(binary),
        "--out-dir",
        str(out_dir),
        "--base-locale",
        base_locale,
        "--locales",
        ",".join(locales),
        "--combined-db",
        str(combined_db),
    ]
    cmd.extend(["--include-fetch-log" if include_fetch_log else "--no-include-fetch-log"])
    cmd.extend(["--checkpoint" if checkpoint else "--no-checkpoint"])

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"cpp merge execution failed: {exc}"

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        detail = stderr if stderr else stdout
        return False, f"cpp merge failed rc={proc.returncode}: {detail}"

    return True, stdout or "cpp merge ok"
