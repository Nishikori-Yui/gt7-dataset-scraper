import json
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
            launcher = launcher_path(package) if os.name != "nt" else Path(sys.executable)
            prefix = [str(launcher)]
            if os.name == "nt":
                prefix.append(str(package / "scripts" / "gt7db.py"))
            env = {**os.environ, "PYTHON_BIN": sys.executable}
            for command in ("scrape", "build-dbs", "query"):
                proc = subprocess.run(
                    [*prefix, command, "--help"], cwd=root, env=env, capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = subprocess.run(
                [*prefix, "doctor", "--json"], cwd=root, env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["packaged"])
            self.assertEqual(Path(payload["project_root"]), package.resolve())

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
