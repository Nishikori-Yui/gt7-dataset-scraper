#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .release_native import (
    OPTIONAL_NATIVE,
    REPO_ROOT,
    REQUIRED_NATIVE,
    exe_name,
    find_binary,
    git_commit,
    is_windows,
    release_basename,
    run,
)

WORKER_EXCLUDES = [
    "gt7_query/backends/python_backend.py",
    "gt7_query/cli.py",
    "gt7_query/queries.py",
    "gt7_scraper/cli.py",
    "gt7_scraper/scraper.py",
    "gt7_scraper/engine/catalog_go.py",
    "gt7_scraper/engine/downloader.py",
    "gt7_scraper/engine/playwright_node.py",
    "gt7_scraper/engine/spec_rust.py",
]


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def copy_worker(stage_root: Path, include_full_python_backends: bool) -> List[str]:
    worker_root = stage_root / "runtime" / "python" / "worker"
    worker_root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(REPO_ROOT / "gt7_scraper", worker_root / "gt7_scraper", dirs_exist_ok=True)
    shutil.copytree(REPO_ROOT / "gt7_query", worker_root / "gt7_query", dirs_exist_ok=True)
    (worker_root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "scripts" / "build_dbs.py", worker_root / "scripts" / "build_dbs.py")
    shutil.copy2(REPO_ROOT / "scripts" / "example_car_ids_10.txt", worker_root / "scripts" / "example_car_ids_10.txt")

    excluded: List[str] = []
    if not include_full_python_backends:
        for rel in WORKER_EXCLUDES:
            target = worker_root / rel
            if target.exists():
                remove_path(target)
                excluded.append(rel)

    for junk in worker_root.rglob("__pycache__"):
        remove_path(junk)
    for junk in worker_root.rglob("*.pyc"):
        remove_path(junk)
    for junk in worker_root.rglob(".DS_Store"):
        remove_path(junk)

    return excluded


def copy_python_runtime(stage_root: Path) -> Path:
    python_home = Path(sys_base_prefix()).resolve()
    runtime_python = stage_root / "runtime" / "python"
    if runtime_python.exists():
        shutil.rmtree(runtime_python)
    shutil.copytree(
        python_home,
        runtime_python,
        dirs_exist_ok=True,
        symlinks=True,
        ignore_dangling_symlinks=True,
    )

    py = resolve_python_executable(runtime_python)
    run([str(py), "-m", "ensurepip", "--upgrade"])
    run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "--no-cache-dir", "-r", str(REPO_ROOT / "requirements.txt")])
    return py


def sys_base_prefix() -> str:
    import sys

    return sys.base_prefix


def resolve_python_executable(runtime_python: Path) -> Path:
    candidates = [
        runtime_python / "bin" / "python3",
        runtime_python / "bin" / "python",
        runtime_python / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise SystemExit(f"python executable not found under {runtime_python}")


def copy_native(stage_root: Path, flavor: str, platform_id: str) -> None:
    native_root = stage_root / "runtime" / "native"
    native_root.mkdir(parents=True, exist_ok=True)

    for stem in REQUIRED_NATIVE:
        src = find_binary(stem)
        shutil.copy2(src, native_root / src.name)

    for stem in OPTIONAL_NATIVE:
        try:
            src = find_binary(stem)
        except FileNotFoundError:
            continue
        shutil.copy2(src, native_root / src.name)

    if flavor == "full":
        playwright_cli = stage_root / "runtime" / "playwright" / "dist" / "cli.js"
        if not playwright_cli.exists():
            raise SystemExit("full flavor requires playwright dist/cli.js")
        shutil.copy2(playwright_cli, native_root / "gt7-playwright.js")

        if not is_windows(platform_id):
            wrapper = native_root / "gt7-playwright"
            wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "ROOT=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\"\n"
                "export PLAYWRIGHT_BROWSERS_PATH=\"${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/playwright/browsers}\"\n"
                "exec \"$ROOT/node/bin/node\" \"$ROOT/playwright/dist/cli.js\" \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)


def prepare_full_playwright(stage_root: Path, platform_id: str) -> None:
    pw_dir = REPO_ROOT / "engines" / "gt7_playwright"
    run(["npm", "ci"], cwd=pw_dir)
    run(["npm", "run", "build"], cwd=pw_dir)

    browsers_dir = stage_root / "runtime" / "playwright" / "browsers"
    browsers_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    npx = "npx.cmd" if is_windows(platform_id) else "npx"
    run([npx, "playwright", "install", "chromium"], cwd=pw_dir, env=env)

    runtime_pw = stage_root / "runtime" / "playwright"
    runtime_pw.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pw_dir / "dist", runtime_pw / "dist", dirs_exist_ok=True)
    shutil.copytree(pw_dir / "node_modules", runtime_pw / "node_modules", dirs_exist_ok=True)
    for name in ["package.json", "package-lock.json"]:
        shutil.copy2(pw_dir / name, runtime_pw / name)

    node_path = shutil.which("node")
    if not node_path:
        raise SystemExit("node not found in PATH")
    node_exec = Path(node_path).resolve()
    node_home = node_exec.parent if is_windows(platform_id) else node_exec.parent.parent
    shutil.copytree(node_home, stage_root / "runtime" / "node", dirs_exist_ok=True)


def copy_launcher(stage_root: Path, launcher: Path, platform_id: str) -> None:
    bin_dir = stage_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    dst = bin_dir / exe_name("gt7db", platform_id)
    shutil.copy2(launcher, dst)
    if not is_windows(platform_id):
        dst.chmod(0o755)


def write_manifest(stage_root: Path, *, flavor: str, platform_id: str, version: str, excluded: List[str]) -> None:
    manifest = {
        "schema_version": 1,
        "name": "gt7db",
        "version": version,
        "flavor": flavor,
        "target_platform": platform_id,
        "git_commit": git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entrypoint": str(Path("bin") / exe_name("gt7db", platform_id)),
        "runtime": {
            "python": "runtime/python",
            "worker": "runtime/python/worker",
            "native": "runtime/native",
        },
        "defaults": {
            "scrape": {
                "engine": "hybrid",
                "catalog_engine": "go",
                "spec_engine": "rust",
                "backend_fallback": "off",
            },
            "build_dbs": {
                "engine": "hybrid",
                "catalog_engine": "go",
                "spec_engine": "rust",
                "merge_engine": "go",
                "hero_check_engine": "rust",
                "backend_fallback": "off",
            },
            "query": {
                "query_engine": "go",
                "query_fallback": "off",
                "query_mode": "go-first",
            },
        },
        "excluded_python_modules": excluded,
    }
    (stage_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sha256sums(stage_root: Path) -> None:
    lines: List[str] = []
    for path in sorted(stage_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(stage_root)
        if rel.as_posix() == "SHA256SUMS":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel.as_posix()}")
    (stage_root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_archive(stage_root: Path, out_dir: Path, platform_id: str, flavor: str, version: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = release_basename(version, platform_id, flavor)
    if is_windows(platform_id):
        archive = out_dir / f"{base_name}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(stage_root.rglob("*")):
                if path.is_dir():
                    continue
                zf.write(path, path.relative_to(stage_root.parent).as_posix())
        return archive

    archive = out_dir / f"{base_name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(stage_root, arcname=stage_root.name)
    return archive
