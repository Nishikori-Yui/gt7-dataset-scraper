import hashlib
import json
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .release_native import (
    REPO_ROOT,
    REQUIRED_NATIVE,
    exe_name,
    find_binary,
    git_commit,
    is_windows,
    release_basename,
)


def copy_project(stage_root: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for name in ("gt7_scraper", "gt7_query", "scripts", "docs", "engines", "tests"):
        shutil.copytree(REPO_ROOT / name, stage_root / name, ignore=ignore)
    for name in ("README.md", "README.zh-CN.md", "LICENSE", "requirements.txt"):
        shutil.copy2(REPO_ROOT / name, stage_root / name)


def copy_native(stage_root: Path, platform_id: str) -> None:
    native_root = stage_root / "local" / "bin"
    native_root.mkdir(parents=True, exist_ok=True)
    for stem in REQUIRED_NATIVE:
        source = find_binary(stem, platform_id)
        shutil.copy2(source, native_root / exe_name(stem, platform_id))


def copy_launcher(stage_root: Path, platform_id: str) -> None:
    bin_dir = stage_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if is_windows(platform_id):
        launcher = bin_dir / "gt7db.cmd"
        launcher.write_text(
            '@echo off\r\n'
            'setlocal\r\n'
            'set "ROOT=%~dp0.."\r\n'
            'if not defined PYTHON_BIN set "PYTHON_BIN=python"\r\n'
            'if exist "%ROOT%\\.venv\\Scripts\\python.exe" set "PYTHON_BIN=%ROOT%\\.venv\\Scripts\\python.exe"\r\n'
            '"%PYTHON_BIN%" "%ROOT%\\scripts\\gt7db.py" %*\r\n'
            'exit /b %errorlevel%\r\n',
            encoding="utf-8",
            newline="",
        )
        return

    launcher = bin_dir / "gt7db"
    launcher.write_text(
        '#!/bin/sh\n'
        'set -eu\n'
        'ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"\n'
        'PYTHON_BIN="${PYTHON_BIN:-python3}"\n'
        'if [ -x "$ROOT/.venv/bin/python" ]; then PYTHON_BIN="$ROOT/.venv/bin/python"; fi\n'
        'exec "$PYTHON_BIN" "$ROOT/scripts/gt7db.py" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def write_manifest(stage_root: Path, *, platform_id: str, version: str) -> None:
    manifest = {
        "schema_version": 2,
        "name": "gt7db",
        "version": version,
        "target_platform": platform_id,
        "git_commit": git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entrypoint": "bin/gt7db.cmd" if is_windows(platform_id) else "bin/gt7db",
    }
    path = stage_root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sha256sums(stage_root: Path) -> None:
    lines = []
    for path in sorted(stage_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(stage_root).as_posix()}")
    (stage_root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_archive(stage_root: Path, out_dir: Path, platform_id: str, version: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = release_basename(version, platform_id)
    if is_windows(platform_id):
        archive = out_dir / f"{base_name}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for path in sorted(stage_root.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(stage_root.parent).as_posix())
        return archive

    archive = out_dir / f"{base_name}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(stage_root, arcname=stage_root.name)
    return archive
