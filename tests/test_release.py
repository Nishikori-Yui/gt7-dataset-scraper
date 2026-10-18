import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.release.release_package import (
    copy_launcher,
    copy_native,
    copy_project,
    make_archive,
    write_manifest,
    write_sha256sums,
)
from scripts.release.smoke_release import check_manifest, launcher_path


class ReleaseTests(unittest.TestCase):
    def test_archive_runs_after_relocation(self):
        with tempfile.TemporaryDirectory(prefix="gt7-release-") as directory:
            root = Path(directory)
            stage = root / "build" / "GT7DB_test_linux_AMD64"
            stage.mkdir(parents=True)
            copy_project(stage)
            copy_launcher(stage, "linux-amd64")
            write_manifest(stage, platform_id="linux-amd64", version="test")
            write_sha256sums(stage)
            archive = make_archive(stage, root / "archives", "linux-amd64", "test")
            moved = root / "moved package"
            shutil.unpack_archive(archive, moved)
            shutil.rmtree(stage)
            package = moved / stage.name
            check_manifest(package)
            self.assertFalse((package / "runtime").exists())
            self.assertFalse((package / ".venv").exists())
            self.assertFalse(any(package.rglob("__pycache__")))
            self.assertTrue((package / "pyproject.toml").is_file())
            self.assertTrue((package / "uv.lock").is_file())
            launcher = launcher_path(package)
            env = {
                **os.environ,
                "UV_PYTHON": sys.executable,
                "UV_OFFLINE": "1",
                "UV_CACHE_DIR": str(root / "uv-cache"),
            }
            env["UV_PROJECT_ENVIRONMENT"] = str(Path(sys.prefix))
            for command in ("scrape", "build-dbs", "query", "doctor"):
                proc = subprocess.run(
                    [sys.executable, str(package / "scripts" / "gt7db.py"), command, "--help"],
                    cwd=root, env=env, capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
            launcher_text = launcher.read_text(encoding="utf-8")
            self.assertIn("uv run --locked --project", launcher_text)
            self.assertIn("uv run --no-sync --project", launcher_text)
    def test_windows_package_selects_exe_files_and_cmd_launcher(self):
        with tempfile.TemporaryDirectory(prefix="gt7-windows-") as directory:
            root = Path(directory)
            native = root / "native"
            native.mkdir()
            for name in ("gt7-catalog-go", "gt7-downloader"):
                (native / name).write_bytes(b"unix")
                (native / f"{name}.exe").write_bytes(b"windows")
            stage = root / "GT7DB_test_windows_AMD64"
            with patch("scripts.release.release_native.LOCAL_BIN", native):
                copy_native(stage, "win-amd64")
            copy_launcher(stage, "win-amd64")
            write_manifest(stage, platform_id="win-amd64", version="test")
            write_sha256sums(stage)
            manifest = check_manifest(stage)
            self.assertEqual(manifest["entrypoint"], "bin/gt7db.cmd")
            self.assertEqual(launcher_path(stage).suffix, ".cmd")
            self.assertEqual((stage / "local" / "bin" / "gt7-catalog-go.exe").read_bytes(), b"windows")
            self.assertIn(b"\r\n", launcher_path(stage).read_bytes())


if __name__ == "__main__":
    unittest.main()
