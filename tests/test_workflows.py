import argparse
import io
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gt7_query import get_car_details, overview_stats
from gt7_scraper import db
from gt7_scraper.build import runner
from gt7_scraper.build.hero_check import evaluate_hero_check_outcome, validate_hero_counts
from gt7_scraper.cli import build_parser
from gt7_scraper.parser import normalize_specs
from gt7_scraper.scrape.catalog_parse import parse_car_data
from gt7_scraper.scraper import run_scraper


ROOT = Path(__file__).resolve().parents[1]


def fixture_fetch(_session, url, _timeout):
    if url.endswith("/carlist/"):
        locale = url.split("/")[-4]
        return f'<p>2 Cars</p><script src="/common/dist/gt7/carlist/assets/index-{locale}.js"></script>'
    if "/assets/index-" in url:
        locale = Path(url).stem.removeprefix("index-")
        return f'"cars.{locale}-sample.js"; "descriptions.{locale}-sample.js"'
    if "/assets/cars." in url:
        locale = re.search(r"cars\.(\w+)-", url)[1]
        cars = {
            f"car{index}": {
                "name": f"Sample {index}" if locale == "gb" else f"示例 {index}",
                "manufacturerId": "maker1",
                "manufacturerName": "Sample Motors",
                "countryId": "carctry2",
                "driveTrain": "FR",
                "aspirationShort": "NA",
                "specs": {"Weight": "1,200 kg", "Max Power": "203 HP / 6000 rpm"},
            }
            for index in (1, 2)
        }
        return f"const data = {json.dumps(cars)}; export {{data as CarList}};"
    if "/assets/descriptions." in url:
        descriptions = {f"car{index}": {"hero": "Sample intro", "desc": "Sample detail"} for index in (1, 2)}
        return f"const data = {json.dumps(descriptions)}; export {{data as Descriptions}};"
    if "/carlist/id/" in url:
        return ""
    raise AssertionError(f"Unexpected request: {url}")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gt7-workflow-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def build(self, *extra):
        parser = argparse.ArgumentParser()
        runner.add_arguments(parser)
        args = parser.parse_args([
            "--locales", "gb,cn",
            "--out-dir", str(self.output),
            "--images", str(self.output / "images"),
            "--image-policy", "none",
            "--hero-check", "off",
            *extra,
        ])
        with patch("gt7_scraper.scraper.fetch_text", side_effect=fixture_fetch) as fetch:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                runner.run(args)
        return fetch

    def test_scrape_merge_and_all_query_commands(self):
        fetch = self.build()
        # One catalog fetch per locale; creating the combined DB must not scrape again.
        self.assertEqual(sum(call.args[1].endswith("/carlist/") for call in fetch.call_args_list), 2)
        combined = self.output / "gt7.db"
        self.assertEqual(overview_stats(combined)["locales"], ["cn", "gb"])
        self.assertEqual(overview_stats(combined)["cars"], 2)
        details = get_car_details(combined, "car1", locale="cn")
        self.assertEqual(details["name"], "示例 1")
        self.assertEqual(details["country"]["iso3"], "JPN")
        weight = next(spec for spec in details["specs"] if spec["spec_key"] == "weight")
        self.assertEqual((weight["spec_value"], weight["spec_unit"]), ("1,200", "kg"))
        with sqlite3.connect(combined) as conn:
            self.assertEqual(conn.execute("SELECT name FROM cars WHERE id='car1'").fetchone()[0], "Sample 1")
        for locale in ("gb", "cn"):
            self.assertEqual(overview_stats(self.output / f"gt7.{locale}.db")["locales"], [locale])

        commands = [
            ["overview"],
            ["list", "--locale", "cn", "--sort", "weight"],
            ["car", "--car-id", "car1", "--locale", "cn"],
            *[["stats", "--by", group] for group in ("manufacturer", "country", "drivetrain")],
        ]
        for command in commands:
            with self.subTest(command=command):
                proc = subprocess.run(
                    [sys.executable, "-m", "gt7_query", *command, "--db", str(combined)],
                    cwd=ROOT, text=True, capture_output=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(json.loads(proc.stdout))

    def test_resume_preserves_existing_locale_database(self):
        self.build()
        overlay = self.output / "gt7.cn.db"
        with sqlite3.connect(overlay) as conn:
            conn.execute("UPDATE car_texts SET name='Preserved' WHERE car_id='car1'")
            before = conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0]
        self.build("--resume")
        self.assertEqual(get_car_details(overlay, "car1", locale="cn")["name"], "Preserved")
        with sqlite3.connect(overlay) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0], before)

    def test_merge_existing_databases_needs_no_fetch(self):
        self.build()
        fetch = self.build("--no-per-locale")
        fetch.assert_not_called()
        self.assertEqual(overview_stats(self.output / "gt7.db")["cars"], 2)

    def scrape_options(self):
        return dict(
            locale="gb", db_path=self.output / "sample.db", image_dir=self.output / "images",
            limit=2, resume=False, use_playwright=False, rate=0, timeout=1, workers=2,
            download_images=False, show_progress=False,
        )

    def test_missing_optional_tools_use_builtin_parser_without_warnings(self):
        kwargs = self.scrape_options()
        kwargs["tools_dir"] = self.output / "missing-tools"
        messages = io.StringIO()
        with patch("gt7_scraper.scraper.fetch_text", side_effect=fixture_fetch), redirect_stderr(messages):
            self.assertEqual(run_scraper(**kwargs), 0)
        self.assertEqual(overview_stats(kwargs["db_path"])["cars"], 2)
        self.assertEqual(messages.getvalue(), "")

    def test_catalog_tool_is_used_automatically(self):
        kwargs = self.scrape_options()
        cars = parse_car_data(fixture_fetch(None, "/assets/cars.gb-sample.js", 1))
        with (
            patch("gt7_scraper.scraper.fetch_text", side_effect=fixture_fetch),
            patch("gt7_scraper.scraper.resolve_catalog_binary", return_value="catalog-tool") as resolve,
            patch(
                "gt7_scraper.backends.catalog._run_catalog_go",
                side_effect=lambda _binary, payload: cars if payload["mode"] == "chunk-parse" else {},
            ) as tool,
        ):
            self.assertEqual(run_scraper(**kwargs), 0)
        resolve.assert_called_once_with(ROOT / "local" / "bin")
        self.assertTrue(any(call.args[1]["mode"] == "chunk-parse" for call in tool.call_args_list))
        self.assertEqual(overview_stats(kwargs["db_path"])["cars"], 2)

    def test_broken_optional_tool_uses_builtin_parser(self):
        kwargs = self.scrape_options()
        with (
            patch("gt7_scraper.scraper.fetch_text", side_effect=fixture_fetch),
            patch("gt7_scraper.scraper.resolve_catalog_binary", return_value="catalog-tool"),
            patch("gt7_scraper.backends.catalog._run_catalog_go", side_effect=RuntimeError("tool failed")),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(run_scraper(**kwargs), 0)
        self.assertEqual(overview_stats(kwargs["db_path"])["cars"], 2)

    def test_cli_exposes_workflow_options_without_execution_modes(self):
        build = argparse.ArgumentParser()
        runner.add_arguments(build)
        for parser in (build_parser(), build):
            with self.subTest(parser=parser.description):
                help_text = parser.format_help()
                for option in ("--engine", "--backend-fallback"):
                    self.assertNotIn(option, help_text)
                args = parser.parse_args([])
                self.assertEqual(args.commit_batch, 50)
                self.assertTrue(args.sqlite_wal)
                args = parser.parse_args(["--no-sqlite-wal", "--commit-batch", "1"])
                self.assertFalse(args.sqlite_wal)
                self.assertEqual(args.commit_batch, 1)

    def test_python_normalization_splits_values_units_and_rpm(self):
        rows = normalize_specs([("Weight", "1,200 kg"), ("Max Power", "203 HP / 6000 rpm")], locale="gb")
        values = {row["spec_key"]: (row["spec_value"], row["spec_unit"]) for row in rows}
        self.assertEqual(values["weight"], ("1,200", "kg"))
        self.assertEqual(values["max_power"], ("203", "HP"))
        self.assertEqual(values["max_power_rpm"], ("6000", "rpm"))

    def test_python_hero_validation_and_thresholds(self):
        self.build()
        target = self.output / "gt7.db"
        conn = db.connect_db(target)
        try:
            db.init_db(conn, create_images=True)
            db.replace_images(conn, "car1", [{"image_path": "hero.jpg", "image_type": "hero"}])
            conn.commit()
        finally:
            conn.close()
        checked, diffs = validate_hero_counts(target, {"car1": 2, "car2": 0}, hero_min=1)
        self.assertEqual((checked, len(diffs)), (2, 1))
        self.assertEqual((diffs[0]["car_id"], diffs[0]["actual"]), ("car1", 1))
        self.assertTrue(evaluate_hero_check_outcome("strict", checked, 1, 0.05, 20)[0])
        self.assertFalse(evaluate_hero_check_outcome("soft", checked, 1, 0.05, 20)[0])
        self.assertTrue(evaluate_hero_check_outcome("soft", checked, 1, 0.05, 0)[0])


if __name__ == "__main__":
    unittest.main()
