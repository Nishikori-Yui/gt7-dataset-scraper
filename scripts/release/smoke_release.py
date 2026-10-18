#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
    )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def ensure_minimal_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cars(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS manufacturers(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS car_specs(
              car_id TEXT,
              locale TEXT,
              spec_key TEXT,
              spec_value TEXT,
              spec_unit TEXT,
              spec_raw TEXT,
              sort_order INTEGER
            );
            CREATE TABLE IF NOT EXISTS car_texts(
              car_id TEXT,
              locale TEXT,
              name TEXT,
              intro TEXT,
              detail TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def check_manifest(package_dir: Path) -> dict:
    manifest_path = package_dir / "manifest.json"
    assert_true(manifest_path.exists(), f"manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert_true(manifest.get("schema_version") == 2, "manifest schema mismatch")
    assert_true((package_dir / manifest["entrypoint"]).is_file(), "manifest entrypoint missing")
    checksums = package_dir / "SHA256SUMS"
    assert_true(checksums.is_file(), "SHA256SUMS missing")
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = package_dir / name
        assert_true(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"checksum mismatch: {name}")
    return manifest


def check_native(package_dir: Path, platform_id: str) -> None:
    suffix = ".exe" if platform_id.startswith("win-") else ""
    native_dir = package_dir / "local" / "bin"
    for name in ("gt7-catalog-go", "gt7-downloader"):
        assert_true((native_dir / f"{name}{suffix}").is_file(), f"native tool missing: {name}")


def launcher_path(package_dir: Path) -> Path:
    command = package_dir / "bin" / "gt7db.cmd"
    if command.exists():
        return command
    unix = package_dir / "bin" / "gt7db"
    if unix.exists():
        return unix
    raise SystemExit("launcher missing under bin/")


def launch(launcher: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    command = [str(launcher), *args]
    if launcher.suffix.lower() == ".cmd" and os.name == "nt":
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/c", *command]
    return run(command, cwd=cwd)


def check_doctor(package_dir: Path, launcher: Path) -> None:
    proc = launch(launcher, "doctor", "--json", cwd=package_dir)
    assert_true(proc.returncode == 0, f"doctor failed: {proc.stderr}")
    data = json.loads(proc.stdout)
    expected_tools = {"gt7-catalog-go": True, "gt7-downloader": True}
    assert_true(data.get("native_bins") == expected_tools, "doctor cannot find Go tools")


def check_query(package_dir: Path, launcher: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="gt7db-smoke-") as directory:
        db_path = Path(directory) / "smoke.db"
        ensure_minimal_db(db_path)
        proc = launch(launcher, "query", "overview", "--db", str(db_path), cwd=package_dir)
        assert_true(proc.returncode == 0, f"query overview failed: {proc.stderr}")
        data = json.loads(proc.stdout)
        assert_true(data.get("cars") == 0, "query overview returned unexpected data")


def check_build_dbs_entrypoint(package_dir: Path, launcher: Path) -> None:
    proc = launch(launcher, "build-dbs", "--help", cwd=package_dir)
    assert_true(proc.returncode == 0, f"build-dbs --help failed: {proc.stderr}")
    text = proc.stdout + "\n" + proc.stderr
    assert_true("Build per-locale DBs" in text, "build-dbs help output mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test a built release package directory")
    parser.add_argument("--package-dir", required=True, help="Path to unpacked package root")
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    manifest = check_manifest(package_dir)
    check_native(package_dir, manifest.get("target_platform", ""))
    launcher = launcher_path(package_dir)
    check_doctor(package_dir, launcher)
    check_build_dbs_entrypoint(package_dir, launcher)
    check_query(package_dir, launcher)
    print("[ok] release smoke passed")


if __name__ == "__main__":
    main()
