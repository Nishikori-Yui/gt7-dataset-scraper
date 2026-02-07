#!/usr/bin/env python3
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BIN = REPO_ROOT / "local" / "bin"

PLATFORM_CONFIG: Dict[str, Dict[str, str]] = {
    "darwin-arm64": {"rid": "osx-arm64", "goos": "darwin", "goarch": "arm64"},
    "darwin-amd64": {"rid": "osx-amd64", "goos": "darwin", "goarch": "amd64"},
    "linux-amd64": {"rid": "linux-amd64", "goos": "linux", "goarch": "amd64"},
    "linux-arm64": {"rid": "linux-arm64", "goos": "linux", "goarch": "arm64"},
    "win-amd64": {"rid": "win-amd64", "goos": "windows", "goarch": "amd64"},
    "win-arm64": {"rid": "win-arm64", "goos": "windows", "goarch": "arm64"},
}

REQUIRED_NATIVE = [
    "gt7-catalog-go",
    "gt7-downloader",
    "gt7-spec-normalizer",
    "gt7-db-merge-go",
    "gt7-hero-check",
    "gt7-query-go",
]
OPTIONAL_NATIVE = ["gt7-db-merge"]


def run(cmd: List[str], *, cwd: Path | None = None, env: Dict[str, str] | None = None) -> None:
    print("[run]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"command failed rc={proc.returncode}: {' '.join(cmd)}")


def is_windows(platform_id: str) -> bool:
    return platform_id.startswith("win-")


def exe_name(stem: str, platform_id: str) -> str:
    return f"{stem}.exe" if is_windows(platform_id) else stem


def binary_candidates(stem: str) -> Iterable[Path]:
    yield LOCAL_BIN / stem
    yield LOCAL_BIN / f"{stem}.exe"


def find_binary(stem: str) -> Path:
    for candidate in binary_candidates(stem):
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"binary not found: {stem} under {LOCAL_BIN}")


def build_go_binaries(cfg: Dict[str, str], platform_id: str) -> None:
    builds = [
        (REPO_ROOT / "engines" / "gt7_catalog_go", "gt7-catalog-go"),
        (REPO_ROOT / "engines" / "gt7_downloader", "gt7-downloader"),
        (REPO_ROOT / "engines" / "gt7_db_merge_go", "gt7-db-merge-go"),
        (REPO_ROOT / "engines" / "gt7_query_go", "gt7-query-go"),
    ]
    env = os.environ.copy()
    env["GOOS"] = cfg["goos"]
    env["GOARCH"] = cfg["goarch"]
    env.setdefault("CGO_ENABLED", "0")
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    for cwd, stem in builds:
        out = LOCAL_BIN / exe_name(stem, platform_id)
        run(["go", "build", "-o", str(out), "."], cwd=cwd, env=env)


def build_rust_binaries(platform_id: str) -> None:
    builds = [
        (REPO_ROOT / "engines" / "gt7_spec_normalizer", "gt7-spec-normalizer"),
        (REPO_ROOT / "engines" / "gt7_hero_check_rust", "gt7-hero-check"),
    ]
    target = None
    if platform_id == "darwin-amd64":
        target = "x86_64-apple-darwin"

    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    for cwd, stem in builds:
        cmd = ["cargo", "build", "--release"]
        if target:
            cmd.extend(["--target", target])
        run(cmd, cwd=cwd)
        if target:
            source = cwd / "target" / target / "release" / exe_name(stem, platform_id)
        else:
            source = cwd / "target" / "release" / exe_name(stem, platform_id)
        if not source.exists() and is_windows(platform_id):
            source = cwd / "target" / "release" / f"{stem}.exe"
        if not source.exists():
            raise SystemExit(f"rust output missing: {source}")
        shutil.copy2(source, LOCAL_BIN / source.name)


def build_cpp_merge(platform_id: str) -> None:
    if is_windows(platform_id):
        print("[warn] skip C++ merge build on windows")
        return
    build_script = REPO_ROOT / "engines" / "gt7_db_merge_cpp" / "build.sh"
    if not build_script.exists():
        print("[warn] C++ merge build script missing")
        return
    run([str(build_script)])


def build_launcher(rid: str, platform_id: str) -> Path:
    proj = REPO_ROOT / "engines" / "gt7db_launcher_dotnet" / "Gt7db.Launcher.csproj"
    out = LOCAL_BIN / f"gt7db-{rid}"
    out.mkdir(parents=True, exist_ok=True)
    dotnet_rid = rid.replace("-amd64", "-x64")
    run(
        [
            "dotnet",
            "publish",
            str(proj),
            "-c",
            "Release",
            "-r",
            dotnet_rid,
            "--self-contained",
            "true",
            "/p:PublishSingleFile=true",
            "/p:PublishTrimmed=false",
            "-o",
            str(out),
        ]
    )
    launcher = out / exe_name("gt7db", platform_id)
    if not launcher.exists() and is_windows(platform_id):
        launcher = out / "gt7db.exe"
    if not launcher.exists():
        raise SystemExit(f"launcher missing: {launcher}")
    return launcher


def git_commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return (proc.stdout or "").strip() or "unknown"


def platform_parts(platform_id: str) -> tuple[str, str]:
    os_key, arch = platform_id.split("-", 1)
    os_name = {"darwin": "macOS", "linux": "linux", "win": "windows"}.get(os_key, os_key)
    return os_name, arch


def release_basename(version: str, platform_id: str, flavor: str) -> str:
    os_name, arch = platform_parts(platform_id)
    return f"GT7DB_{version}_{flavor.upper()}_{os_name}_{arch.upper()}"
