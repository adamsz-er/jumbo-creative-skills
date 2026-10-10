import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "copy-tests" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import creative_metrics as cm  # noqa: E402
import power  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
SCRIPT = str(SCRIPTS / "power.py")


def day_rows(spend=100.0, impressions=10000, clicks=200, days=9):
    return cm.load_rows([
        {"Day": "2026-03-%02d" % (d + 1), "Ad name": "a", "Ad ID": "1", "Amount spent (USD)": spend,
         "Impressions": impressions, "Link clicks": clicks}
        for d in range(days)
    ])


def plan(rows=None, **overrides):
    args = dict(metric="ctr", mde=18, daily_budget=300, max_days=21, arms=2, alpha=0.05, power=0.8)
    args.update(overrides)
    return power.plan(rows or day_rows(), None, args["metric"], args["mde"], args["daily_budget"],
                      args["max_days"], args["arms"], args["alpha"], args["power"])


def run(*args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True)


def write_csv(directory, rows):
    path = Path(directory) / "ads.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


class SampleSizeTest(unittest.TestCase):
    def test_exact_n_matches_the_formula(self):
        p1, p2 = 0.02, 0.02 * 1.18
        z_alpha, z_power = 1.959964, 0.841621
        pbar = (p1 + p2) / 2
        expected = ((z_alpha * math.sqrt(2 * pbar * (1 - pbar)) + z_power * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
                    / (p2 - p1) ** 2)
        n = power.sample_per_arm(p1, p2, 0.05, 0.8)
        self.assertLessEqual(abs(n - expected), 1)

    def test_plan_uses_the_pooled_baseline(self):
        result = plan()
        self.assertAlmostEqual(result["baseline"]["rate"], 0.02)
        self.assertAlmostEqual(result["target_rate"], 0.0236)
        self.assertEqual(result["n_per_arm"], power.sample_per_arm(0.02, 0.0236, 0.05, 0.8))
        self.assertAlmostEqual(result["baseline"]["volume_per_spend"], 100.0)
        self.assertAlmostEqual(result["daily_per_arm"], 300 / 2 * 100)

    def test_days_scale_inversely_with_budget(self):
        low, high = plan(daily_budget=100), plan(daily_budget=200)
        self.assertAlmostEqual(low["days_needed"] / high["days_needed"], 2, delta=0.1)
        self.assertEqual(plan(daily_budget=200)["total_budget"], high["days_needed"] * 200)

    def test_powered_boundary(self):
        days = plan()["days_needed"]
        self.assertTrue(plan(max_days=days)["powered"])
        self.assertFalse(plan(max_days=days - 1)["powered"])

    def test_smallest_detectable_change_fits_and_a_smaller_one_does_not(self):
        result = plan(daily_budget=100, max_days=5)
        self.assertFalse(result["powered"])
        smallest = result["smallest_detectable_mde"]
        capacity = 5 * result["daily_per_arm"]
        self.assertLessEqual(power.sample_per_arm(0.02, 0.02 * (1 + smallest / 100), 0.05, 0.8), capacity)
        self.assertGreater(power.sample_per_arm(0.02, 0.02 * (1 + (smallest - 0.01) / 100), 0.05, 0.8), capacity)

    def test_budget_to_fit_makes_the_test_fit(self):
        result = plan(daily_budget=100, max_days=5)
        self.assertLessEqual(plan(daily_budget=result["budget_to_fit"], max_days=5)["days_needed"], 5)
        self.assertGreater(plan(daily_budget=result["budget_to_fit"] * 0.98, max_days=5)["days_needed"], 5)

    def test_three_arms_split_alpha(self):
        result = plan(arms=3)
        self.assertEqual(result["settings"]["alpha_per_comparison"], 0.025)
        self.assertEqual(result["n_per_arm"], power.sample_per_arm(0.02, 0.0236, 0.025, 0.8))
        self.assertAlmostEqual(result["daily_per_arm"], 300 / 3 * 100)
        self.assertGreater(result["n_per_arm"], plan()["n_per_arm"])


class BadInputTest(unittest.TestCase):
    def test_missing_field_names_the_column(self):
        with self.assertRaises(ValueError) as caught:
            plan(metric="hold_rate")
        self.assertIn("n/a (missing video_thruplay)", str(caught.exception))
        self.assertIn("ThruPlays", str(caught.exception))

    def test_cli_missing_field_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, [{"Day": "2026-03-01", "Ad name": "a", "Ad ID": "1", "Amount spent (USD)": 90,
                                    "Impressions": 9000, "Link clicks": 180}])
            done = run(path, "--metric", "hold_rate", "--mde", "18", "--daily-budget", "300", "--max-days", "21")
        self.assertEqual(done.returncode, 2)
        self.assertIn("n/a (missing video_thruplay)", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_bad_metric_lists_the_allowed_ones(self):
        done = run(str(FIXTURE), "--metric", "cpa", "--mde", "18", "--daily-budget", "300", "--max-days", "21")
        self.assertEqual(done.returncode, 2)
        self.assertIn("hook_rate", done.stderr)
        self.assertIn("cart_to_checkout_rate", done.stderr)

    def test_target_rate_of_one_or_more_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            plan(mde=5000)
        self.assertIn("choose a smaller --mde", str(caught.exception))

    def test_no_variation_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            plan(rows=day_rows(clicks=0))
        self.assertIn("no variation", str(caught.exception))

    def test_arms_and_mde_are_validated(self):
        for bad in ({"arms": 1}, {"mde": 0}, {"max_days": 0}, {"alpha": 1.5}):
            with self.assertRaises(ValueError):
                plan(**bad)

    def test_empty_input_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.csv"
            path.write_text("Day,Ad name,Ad ID,Amount spent (USD),Impressions,Link clicks\n")
            done = run(str(path), "--metric", "ctr", "--mde", "18", "--daily-budget", "300", "--max-days", "21")
        self.assertEqual(done.returncode, 2)
        self.assertNotIn("Traceback", done.stderr)


class FixtureTest(unittest.TestCase):
    def test_ctr_baseline_is_the_csv_ratio(self):
        with open(FIXTURE, newline="", encoding="utf-8-sig") as handle:
            data = list(csv.DictReader(handle))
        clicks = sum(float(r["Link clicks"]) for r in data)
        impressions = sum(float(r["Impressions"]) for r in data)
        done = run(str(FIXTURE), "--metric", "ctr", "--mde", "18", "--daily-budget", "300", "--max-days", "21", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertAlmostEqual(result["baseline"]["rate"], clicks / impressions)
        self.assertEqual(result["baseline"]["numerator"], clicks)
        self.assertEqual(result["baseline"]["den_field"], "impressions")
        self.assertEqual(result["settings"]["currency"], "USD")
        self.assertIn("Fixed horizon", result["stopping_rule"])

    def test_cvr_cannot_be_powered_and_offers_options(self):
        done = run(str(FIXTURE), "--metric", "cvr", "--mde", "18", "--daily-budget", "300", "--max-days", "21")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("This account cannot power this test within 21 days", done.stdout)
        self.assertIn("smallest relative change detectable", done.stdout)
        self.assertIn("higher-funnel metric", done.stdout)

    def test_ctr_can_be_powered_text(self):
        done = run(str(FIXTURE), "--metric", "ctr", "--mde", "18", "--daily-budget", "300", "--max-days", "21")
        self.assertTrue(done.stdout.startswith("This account can power the test: about"))
        self.assertIn("USD/day", done.stdout)

    def test_where_changes_the_baseline(self):
        whole = json.loads(run(str(FIXTURE), "--metric", "ctr", "--mde", "18", "--daily-budget", "300",
                               "--max-days", "21", "--json").stdout)
        one = json.loads(run(str(FIXTURE), "--metric", "ctr", "--mde", "18", "--daily-budget", "300",
                             "--max-days", "21", "--where", "format=ugc-video", "--json").stdout)
        self.assertNotEqual(whole["baseline"]["denominator"], one["baseline"]["denominator"])
        self.assertLess(one["baseline"]["denominator"], whole["baseline"]["denominator"])


if __name__ == "__main__":
    unittest.main()
