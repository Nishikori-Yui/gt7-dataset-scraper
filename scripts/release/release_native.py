#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BIN = REPO_ROOT / "local" / "bin"

PLATFORM_CONFIG: Dict[str, Dict[str, str]] = {
    "darwin-arm64": {"goos": "darwin", "goarch": "arm64"},
    "darwin-amd64": {"goos": "darwin", "goarch": "amd64"},
    "linux-amd64": {"goos": "linux", "goarch": "amd64"},
    "linux-arm64": {"goos": "linux", "goarch": "arm64"},
    "win-amd64": {"goos": "windows", "goarch": "amd64"},
    "win-arm64": {"goos": "windows", "goarch": "arm64"},
}

REQUIRED_NATIVE = ["gt7-catalog-go", "gt7-downloader"]


def run(cmd: List[str], *, cwd: Path | None = None, env: Dict[str, str] | None = None) -> None:
    print("[run]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"command failed rc={proc.returncode}: {' '.join(cmd)}")


def is_windows(platform_id: str) -> bool:
    return platform_id.startswith("win-")


def exe_name(stem: str, platform_id: str) -> str:
    return f"{stem}.exe" if is_windows(platform_id) else stem


def find_binary(stem: str, platform_id: str) -> Path:
    candidate = LOCAL_BIN / exe_name(stem, platform_id)
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"binary not found: {candidate}")


def build_go_binaries(cfg: Dict[str, str], platform_id: str) -> None:
    builds = [
        (REPO_ROOT / "engines" / "gt7_catalog_go", "gt7-catalog-go"),
        (REPO_ROOT / "engines" / "gt7_downloader", "gt7-downloader"),
    ]
    env = os.environ.copy()
    env["GOOS"] = cfg["goos"]
    env["GOARCH"] = cfg["goarch"]
    env["CGO_ENABLED"] = "0"
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    for cwd, stem in builds:
        out = LOCAL_BIN / exe_name(stem, platform_id)
        run(["go", "build", "-trimpath", "-ldflags=-s -w", "-o", str(out), "."], cwd=cwd, env=env)


def git_commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return (proc.stdout or "").strip() or "unknown"


def platform_parts(platform_id: str) -> tuple[str, str]:
    os_key, arch = platform_id.split("-", 1)
    os_name = {"darwin": "macOS", "linux": "linux", "win": "windows"}.get(os_key, os_key)
    return os_name, arch


def release_basename(version: str, platform_id: str) -> str:
    os_name, arch = platform_parts(platform_id)
    return f"GT7DB_{version}_{os_name}_{arch.upper()}"
