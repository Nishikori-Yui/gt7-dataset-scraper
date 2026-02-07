#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


EXPECTED_DEFAULTS = {
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
}


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
    assert_true(manifest.get("defaults") == EXPECTED_DEFAULTS, "manifest defaults mismatch")
    assert_true((package_dir / "SHA256SUMS").exists(), "SHA256SUMS missing")
    return manifest


def launcher_path(package_dir: Path) -> Path:
    exe = package_dir / "bin" / "gt7db.exe"
    if exe.exists():
        return exe
    unix = package_dir / "bin" / "gt7db"
    if unix.exists():
        return unix
    raise SystemExit("launcher missing under bin/")


def check_doctor(package_dir: Path, launcher: Path) -> None:
    proc = run([str(launcher), "doctor", "--json"], cwd=package_dir)
    assert_true(proc.returncode == 0, f"doctor failed: {proc.stderr}")
    data = json.loads(proc.stdout)
    defaults = data.get("defaults", {})
    assert_true(defaults.get("query", [])[-1] == "off", "doctor query fallback default is not off")
    assert_true(defaults.get("build-dbs", [])[-1] == "off", "doctor build-dbs fallback default is not off")


def check_query_fallback_off(package_dir: Path, launcher: Path) -> None:
    native_dir = package_dir / "runtime" / "native"
    go_query = native_dir / "gt7-query-go"
    if not go_query.exists():
        go_query = native_dir / "gt7-query-go.exe"
    assert_true(go_query.exists(), "gt7-query-go missing in runtime/native")

    temp = Path(tempfile.mkdtemp(prefix="gt7db-smoke-"))
    try:
        db_path = temp / "smoke.db"
        ensure_minimal_db(db_path)

        bak = go_query.with_name(go_query.name + ".bak")
        go_query.rename(bak)
        try:
            proc = run([str(launcher), "query", "overview", "--db", str(db_path)], cwd=package_dir)
            assert_true(proc.returncode != 0, "query unexpectedly succeeded without go backend")
            text = (proc.stderr + "\n" + proc.stdout).lower()
            assert_true("query-fallback=off" in text, "fallback-off message missing in query failure")
        finally:
            bak.rename(go_query)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def check_excluded_modules(package_dir: Path, manifest: dict) -> None:
    worker_root = package_dir / "runtime" / "python" / "worker"
    for rel in manifest.get("excluded_python_modules", []):
        path = worker_root / rel
        assert_true(not path.exists(), f"excluded module still exists: {rel}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test a built release package directory")
    parser.add_argument("--package-dir", required=True, help="Path to unpacked package root")
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    manifest = check_manifest(package_dir)
    launcher = launcher_path(package_dir)
    check_doctor(package_dir, launcher)
    check_query_fallback_off(package_dir, launcher)
    check_excluded_modules(package_dir, manifest)
    print("[ok] release smoke passed")


if __name__ == "__main__":
    main()
