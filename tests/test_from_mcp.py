import contextlib
import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "tools"))

import creative_metrics as cm  # noqa: E402
import from_mcp  # noqa: E402
import sync_shared  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mcp_rows.json"
RAW = json.loads(FIXTURE.read_text())["data"]
VIDEO_AD = "120000000101"
STILL_AD = "120000000103"


def _value(cell):
    return float(cell["value"]) if isinstance(cell, dict) else float(str(cell).replace(",", ""))


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = from_mcp.main(argv)
    return code, out.getvalue()


class LoaderMappingTest(unittest.TestCase):
    def setUp(self):
        self.rows = cm.load_rows(RAW, level="ad")
        self.first = self.rows[0]

    def test_every_connector_field_is_mapped(self):
        raw = RAW[0]
        self.assertEqual(self.first["ad_id"], raw["id"])
        self.assertEqual(self.first["ad_name"], raw["name"])
        self.assertEqual(self.first["date"], raw["date_start"])
        self.assertEqual(self.first["spend"], _value(raw["spend"]))
        self.assertEqual(self.first["impressions"], _value(raw["impressions"]))
        self.assertEqual(self.first["link_clicks"], float(raw["link_click"]))
        self.assertEqual(self.first["conversions"], float(raw["omni_purchase"]))
        self.assertEqual(self.first["conversions_source"], "omni_purchase")
        self.assertEqual(self.first["conversion_value"], _value(raw["omni_purchase_values"]))
        self.assertEqual(self.first["add_to_carts"], float(raw["omni_add_to_cart"]))
        self.assertEqual(self.first["created_time"], raw["created_time"])
        self.assertEqual(self.first["video_thruplay"], float(raw["video_thruplay_watched_actions"][0]["value"]))

    def test_three_second_plays_are_derived_and_labelled(self):
        raw = RAW[0]
        expected = _value(raw["spend"]) / _value(raw["cost_per_action_type:video_view"])
        self.assertAlmostEqual(self.first["video_views_3s"], expected, places=6)
        self.assertEqual(self.first["video_views_3s_source"], "derived: spend / cost per 3-second view")

    def test_row_without_a_video_cost_has_no_three_second_plays(self):
        still = next(r for r in self.rows if r["ad_id"] == STILL_AD)
        self.assertIsNone(still.get("video_views_3s"))
        self.assertNotIn("derived", str(still.get("video_views_3s_source")))

    def test_reported_three_second_plays_are_never_overwritten(self):
        row = cm.load_rows([{"ad_name": "a", "spend": 100, "3-second video plays": 500,
                             "cost_per_action_type:video_view": 0.5}])[0]
        self.assertEqual(row["video_views_3s"], 500.0)
        self.assertEqual(row["video_views_3s_source"], "reported")

    def test_hook_rate_is_computed_and_labelled_derived(self):
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(self.rows)}
        ad = ads[VIDEO_AD]
        mine = [r for r in self.rows if r["ad_id"] == VIDEO_AD]
        plays = sum(r["video_views_3s"] for r in mine)
        self.assertAlmostEqual(ad["hook_rate"], plays / ad["impressions"] * 100, places=6)
        self.assertTrue(ad["video_views_3s_source"].startswith("derived"))
        self.assertIsNone(ads[STILL_AD]["hook_rate"])

    def test_age_comes_from_created_time(self):
        ad = next(a for a in cm.aggregate_by_ad(self.rows) if a["ad_id"] == VIDEO_AD)
        self.assertEqual(ad["age_days"], (dt.date(2026, 3, 3) - dt.date(2026, 1, 15)).days)
        self.assertEqual(ad["age_basis"], "created_time")

    def test_age_falls_back_to_first_delivery_and_says_so(self):
        stripped = [{k: v for k, v in r.items() if k != "created_time"} for r in self.rows]
        ad = next(a for a in cm.aggregate_by_ad(stripped) if a["ad_id"] == VIDEO_AD)
        self.assertEqual(ad["age_days"], 2)
        self.assertTrue(ad["age_basis"].startswith("first delivery in window"))
        self.assertIn("understated", ad["age_basis"])

    def test_id_and_name_are_not_remapped_on_a_non_ad_row(self):
        row = cm.load_rows([{"id": "999", "name": "Some campaign", "spend": 5}])[0]
        self.assertNotIn("ad_id", row)
        self.assertNotIn("ad_name", row)
        self.assertEqual((row["id"], row["name"]), ("999", "Some campaign"))

    def test_id_and_name_remap_when_the_row_carries_an_ad_marker(self):
        by_level = cm.load_rows([{"id": "7", "name": "x", "level": "ad"}])[0]
        self.assertEqual((by_level["ad_id"], by_level["ad_name"]), ("7", "x"))
        by_ad_name = cm.load_rows([{"id": "7", "ad_name": "named"}])[0]
        self.assertEqual((by_ad_name["ad_id"], by_ad_name["ad_name"]), ("7", "named"))

    def test_num_reads_value_dicts_and_thousands_separators(self):
        self.assertEqual(cm._num({"value": "12.5", "unit": "USD"}), 12.5)
        self.assertEqual(cm._num("1,234,567"), 1234567.0)
        self.assertIsNone(cm._num({"unit": "USD"}))


class ReviewFixesTest(unittest.TestCase):
    def test_a_rows_own_level_beats_the_level_argument(self):
        row = cm.load_rows([{"level": "campaign", "id": "c1", "name": "Camp", "spend": 5}], level="ad")[0]
        self.assertNotIn("ad_id", row)
        self.assertEqual(row["id"], "c1")

    def test_level_argument_applies_when_the_row_has_none(self):
        row = cm.load_rows([{"id": "a1", "name": "x"}], level="ad")[0]
        self.assertEqual(row["ad_id"], "a1")

    def test_age_is_never_negative_and_uses_the_earlier_date(self):
        rows = cm.load_rows([{"ad_name": "a", "date_start": "2026-03-01", "created_time": "2026-03-05T00:00:00+0000",
                              "impressions": 100}])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertEqual(ad["age_days"], 0)
        later = cm.load_rows([{"ad_name": "a", "date_start": "2026-03-01", "created_time": "2026-02-25T00:00:00+0000",
                               "impressions": 100}, {"ad_name": "a", "date_start": "2026-03-04", "impressions": 100}])
        ad = cm.aggregate_by_ad(later)[0]
        self.assertEqual((ad["age_days"], ad["age_basis"]), (7, "created_time"))

    def test_a_created_time_after_first_delivery_falls_back_to_first_delivery(self):
        rows = cm.load_rows([{"ad_name": "a", "date_start": "2026-03-01", "created_time": "2026-03-02T00:00:00+0000",
                              "impressions": 100}, {"ad_name": "a", "date_start": "2026-03-05", "impressions": 100}])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertEqual(ad["age_days"], 4)
        self.assertTrue(ad["age_basis"].startswith("first delivery"))


class FromMcpTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.total = sum(_value(r["spend"]) for r in RAW)
        self.impressions = sum(_value(r["impressions"]) for r in RAW)
        self.out = self.dir / "ads.csv"

    def _write(self, name, rows):
        path = self.dir / name
        path.write_text(json.dumps(rows))
        return str(path)

    def test_merges_two_files_and_keeps_an_overlapping_row_once(self):
        first = self._write("a.json", {"data": RAW[:10]})
        second = self._write("b.json", {"rows": RAW[8:]})
        code, text = run_main([first, second, "-o", str(self.out)])
        self.assertEqual(code, 0, text)
        rows = cm.load_rows(str(self.out))
        self.assertEqual(len(rows), 18)
        self.assertIn("rows: 18", text)
        self.assertIn("distinct ads: 6", text)

    def test_last_duplicate_wins(self):
        changed = dict(RAW[0], omni_purchase=999)
        first = self._write("a.json", RAW)
        second = self._write("b.json", [changed])
        run_main([first, second, "-o", str(self.out)])
        rows = [r for r in cm.load_rows(str(self.out)) if r["ad_id"] == RAW[0]["id"] and r["date"] == RAW[0]["date_start"]]
        self.assertEqual([r["conversions"] for r in rows], [999.0])

    def test_csv_is_readable_by_the_analysis_scripts(self):
        run_main([str(FIXTURE), "-o", str(self.out)])
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(cm.load_rows(str(self.out)))}
        self.assertEqual(len(ads), 6)
        self.assertIsNotNone(ads[VIDEO_AD]["hook_rate"])
        self.assertTrue(ads[VIDEO_AD]["video_views_3s_source"].startswith("derived"))
        self.assertEqual(ads[VIDEO_AD]["age_basis"], "created_time")
        self.assertIsNotNone(ads[VIDEO_AD]["roas"])

    def test_short_pull_exits_3_with_the_warning_first(self):
        code, text = run_main([str(FIXTURE), "-o", str(self.out), "--expect-spend", str(self.total * 1.2)])
        self.assertEqual(code, 3)
        self.assertTrue(text.splitlines()[0].startswith("WARNING"), text)
        self.assertTrue(self.out.exists())

    def test_within_tolerance_exits_0(self):
        code, text = run_main([str(FIXTURE), "-o", str(self.out), "--expect-spend", str(self.total * 1.004),
                               "--expect-impressions", str(self.impressions)])
        self.assertEqual(code, 0, text)
        self.assertFalse(text.startswith("WARNING"))

    def test_tolerance_flag_is_honoured(self):
        argv = [str(FIXTURE), "-o", str(self.out), "--expect-spend", str(self.total * 1.004)]
        self.assertEqual(run_main(argv + ["--tolerance", "0.1"])[0], 3)

    def test_impressions_shortfall_alone_exits_3(self):
        code, text = run_main([str(FIXTURE), "-o", str(self.out), "--expect-spend", str(self.total),
                               "--expect-impressions", str(self.impressions * 1.2)])
        self.assertEqual(code, 3)
        self.assertTrue(text.splitlines()[0].startswith("WARNING"))

    def test_expect_ads_names_the_missing_id(self):
        ids = self.dir / "ids.txt"
        ids.write_text("\n".join([VIDEO_AD, "120000000999"]) + "\n")
        code, text = run_main([str(FIXTURE), "-o", str(self.out), "--expect-ads", str(ids)])
        self.assertEqual(code, 3)
        self.assertIn("120000000999", text.splitlines()[0] + text)
        self.assertNotIn("missing ads: " + VIDEO_AD, text)

    def test_the_same_file_twice_is_not_double_counted(self):
        one = [{"id": "a1", "name": "x", "date_start": "2026-03-01", "spend": 100, "impressions": 1000}]
        path = self._write("one.json", one)
        code, text = run_main([path, path, "-o", str(self.out), "--expect-spend", "100", "--expect-impressions", "1000"])
        self.assertEqual(code, 0, text)
        self.assertIn("rows: 1", text)

    def test_an_over_full_pull_exits_3_and_says_over_counted(self):
        code, text = run_main([str(FIXTURE), "-o", str(self.out), "--expect-spend", str(self.total / 2)])
        self.assertEqual(code, 3)
        first = text.splitlines()[0]
        self.assertTrue(first.startswith("WARNING"), text)
        self.assertIn("over-counted: likely duplicate rows or overlapping windows", first)

    def test_undated_rows_are_deduplicated_on_ad_and_window(self):
        row = {"id": "a1", "name": "x", "date_start": None, "date_stop": "2026-03-07", "spend": 100, "impressions": 1000}
        path = self._write("u.json", [row, dict(row)])
        code, text = run_main([path, "-o", str(self.out), "--expect-spend", "100"])
        self.assertEqual(code, 0, text)
        self.assertIn("rows: 1", text)

    def test_undated_rows_without_a_window_are_refused(self):
        path = self._write("n.json", [{"id": "a1", "name": "x", "spend": 100}])
        code, text = run_main([path, "-o", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("no date", text.lower())

    def test_no_expectations_reports_totals_only(self):
        code, text = run_main([str(FIXTURE), "-o", str(self.out)])
        self.assertEqual(code, 0)
        self.assertIn("total spend: %.2f" % self.total, text)
        self.assertIn("2026-03-01 to 2026-03-03", text)


class IsolatedImportTest(unittest.TestCase):
    def test_every_script_runs_under_isolated_python_from_another_directory(self):
        scripts = sorted(ROOT.glob("skills/*/scripts/*.py"))
        scripts = [s for s in scripts if s.name != "creative_metrics.py"]
        self.assertGreaterEqual(len(scripts), 7)
        with tempfile.TemporaryDirectory() as elsewhere:
            for script in scripts:
                done = subprocess.run([sys.executable, "-I", str(script), "--help"], cwd=elsewhere,
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, "%s: %s" % (script, done.stderr))

    def test_grade_runs_on_the_adapter_output_under_isolated_python(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            csv_path = str(Path(elsewhere) / "ads.csv")
            adapter = ROOT / "skills" / "creative-grader" / "scripts" / "from_mcp.py"
            made = subprocess.run([sys.executable, "-I", str(adapter), str(FIXTURE), "-o", csv_path],
                                  cwd=elsewhere, capture_output=True, text=True)
            self.assertEqual(made.returncode, 0, made.stderr)
            grade = ROOT / "skills" / "creative-grader" / "scripts" / "grade.py"
            done = subprocess.run([sys.executable, "-I", str(grade), csv_path, "--min-impressions", "9"],
                                  cwd=elsewhere, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("(derived)", done.stdout)


class SyncBothFilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "shared").mkdir()
        for name in ("creative_metrics.py", "from_mcp.py"):
            (self.root / "shared" / name).write_text("VERSION = 1\n")
        for skill in ("one", "two"):
            (self.root / "skills" / skill / "scripts").mkdir(parents=True)
            (self.root / "skills" / skill / "scripts" / "creative_metrics.py").write_text("VERSION = 1\n")
        (self.root / "skills" / "plain").mkdir()
        sync_shared.sync(self.root)

    def test_both_files_land_in_every_skill_with_the_metrics_copy(self):
        for skill in ("one", "two", "creative-context"):
            for name in ("creative_metrics.py", "from_mcp.py"):
                self.assertTrue((self.root / "skills" / skill / "scripts" / name).exists(), (skill, name))
        self.assertFalse((self.root / "skills" / "plain" / "scripts").exists())
        self.assertEqual(sync_shared.sync(self.root, check=True), [])

    def test_check_fails_when_from_mcp_drifts_in_one_skill(self):
        drifted = self.root / "skills" / "two" / "scripts" / "from_mcp.py"
        drifted.write_text("VERSION = 2\n")
        self.assertEqual(sync_shared.sync(self.root, check=True), [drifted])
        script = str(ROOT / "tools" / "sync_shared.py")
        done = subprocess.run([sys.executable, script, "--check", "--root", str(self.root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("out of sync", done.stdout)

    def test_real_repo_has_both_files_in_sync(self):
        self.assertEqual(sync_shared.sync(ROOT, check=True), [])
        self.assertTrue((ROOT / "skills" / "creative-grader" / "scripts" / "from_mcp.py").exists())


if __name__ == "__main__":
    unittest.main()
