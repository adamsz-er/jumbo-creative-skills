import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "skills" / "keep-or-kill" / "scripts"))

import creative_metrics as cm  # noqa: E402
import verdicts  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
CHECK = "rule out tracking, site or audience problems first"


def fixture_verdicts(**kwargs):
    rows = cm.load_rows(str(FIXTURE))
    return {r["ad"]: r for r in verdicts.judge_ads(rows, **kwargs)}


class ConcentrationTest(unittest.TestCase):
    ADS = [{"ad_name": n, "spend": s} for n, s in (("a", 50.0), ("b", 30.0), ("c", 15.0), ("d", 5.0))]

    def test_concentration_of_four_ads(self):
        self.assertAlmostEqual(cm.concentration(self.ADS, top_n=3), 95.0)
        self.assertAlmostEqual(cm.concentration(self.ADS, top_n=1), 50.0)

    def test_spend_share_is_sorted_with_cumulative_share(self):
        shares = cm.spend_share(list(reversed(self.ADS)))
        self.assertEqual([s["ad"] for s in shares], ["a", "b", "c", "d"])
        self.assertAlmostEqual(shares[1]["cumulative"], 80.0)
        self.assertAlmostEqual(shares[-1]["cumulative"], 100.0)

    def test_no_spend_is_none_not_zero(self):
        self.assertIsNone(cm.concentration([{"ad_name": "a", "spend": None}]))


class WindowAggregateTest(unittest.TestCase):
    def test_first_and_last_window_are_separate(self):
        rows = []
        for day in range(1, 11):
            rows.append({"Day": "2026-03-%02d" % day, "Ad name": "a", "Ad ID": "a",
                         "Amount spent": 10.0, "Impressions": 1000 * day, "Link clicks": 10})
        rows = cm.load_rows(rows)
        first = cm.window_aggregate(rows, window=3, which="first")[0]
        last = cm.window_aggregate(rows, window=3, which="last")[0]
        self.assertEqual(first["impressions"], 6000)
        self.assertEqual(last["impressions"], 27000)
        self.assertEqual(cm.window_aggregate(rows, window=11), [])


class JsonRowsTest(unittest.TestCase):
    def test_json_file_of_api_rows_loads(self):
        import json
        import tempfile
        api = {"data": [{"date_start": "2026-03-01", "ad_name": "a", "ad_id": "1", "spend": "10",
                         "impressions": "2000", "actions": [{"action_type": "video_view", "value": "500"}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.json"
            path.write_text(json.dumps(api))
            rows = cm.load_rows(str(path))
        self.assertEqual(rows[0]["video_views_3s"], 500.0)
        self.assertEqual(rows[0]["spend"], 10.0)


class HeaderTest(unittest.TestCase):
    def test_output_states_min_change_as_an_arbitrary_default(self):
        import subprocess
        out = subprocess.run([sys.executable, str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"),
                              str(FIXTURE), "--min-change", "18"], capture_output=True, text=True, check=True).stdout
        self.assertIn("min-change=18%", out)
        self.assertIn("not a fatigue benchmark", out)


class FixtureVerdictsTest(unittest.TestCase):
    def test_fatiguing_ad_is_iterated_or_killed_as_fatigued(self):
        verdict = fixture_verdicts()["120000000001"]
        self.assertTrue(verdict["fatiguing"])
        self.assertTrue(verdict["verdict"].startswith(("iterate", "kill: fatigued")), verdict["verdict"])

    def test_young_ad_is_too_early_and_nothing_else(self):
        verdict = fixture_verdicts()["120000000030"]
        self.assertEqual(verdict["verdict"], "too early (learning)")
        self.assertTrue(verdict["learning"])
        self.assertNotIn("kill", " ".join(verdict["reasons"]))

    def test_never_worked_ad_is_killed_as_never_worked(self):
        self.assertEqual(fixture_verdicts()["120000000017"]["verdict"], "kill: never worked")

    def test_every_kill_carries_the_check_line(self):
        results = fixture_verdicts()
        kills = [r for r in results.values() if r["verdict"].startswith("kill")]
        self.assertTrue(kills)
        for entry in kills:
            self.assertIn(CHECK, entry["check"])
        for entry in results.values():
            if not entry["verdict"].startswith("kill"):
                self.assertIsNone(entry["check"])

    def test_every_verdict_lists_reasons(self):
        for entry in fixture_verdicts().values():
            self.assertTrue(entry["reasons"], entry["ad"])

    def test_small_wobbles_are_not_fatigue(self):
        self.assertFalse(fixture_verdicts()["120000000026"]["fatiguing"])

    def test_young_days_is_a_parameter(self):
        self.assertNotEqual(fixture_verdicts(young_days=5)["120000000025"]["verdict"], "too early (learning)")
        self.assertEqual(fixture_verdicts(young_days=13)["120000000025"]["verdict"], "too early (learning)")

    def test_summary_counts_and_concentration(self):
        rows = cm.load_rows(str(FIXTURE))
        results = verdicts.judge_ads(rows)
        summary = verdicts.summarise(results)
        self.assertEqual(sum(summary["counts"].values()), 30)
        self.assertIn("120000000030", summary["too_young"])
        self.assertIn("top 3 ads (N=3, an arbitrary default: set your own) hold", summary["concentration_line"])
        self.assertIn("top 2 ads (N=2", verdicts.summarise(results, top_n=2)["concentration_line"])


if __name__ == "__main__":
    unittest.main()
