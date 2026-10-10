import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "fatigue-planner" / "scripts"
SCRIPT = SCRIPTS / "fatigue_plan.py"
sys.path.insert(0, str(SCRIPTS))

import creative_metrics as cm  # noqa: E402
import fatigue_plan  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
FADING_AD = "120000000001"
YOUNG_AD = "120000000030"
START = dt.date(2026, 1, 1)


def make_rows(ad_id, clicks_by_day, impressions=10000, spend=100.0, name=None):
    """Daily rows for one ad: ctr on delivery day n is clicks_by_day[n-1] / impressions * 100."""
    return [{"date": (START + dt.timedelta(days=i)).isoformat(), "ad_id": ad_id, "ad_name": name or "ad-" + ad_id,
             "spend": spend, "impressions": impressions, "reach": impressions, "link_clicks": clicks}
            for i, clicks in enumerate(clicks_by_day)]


def plan_for(rows, **kwargs):
    kwargs.setdefault("min_impressions", 100)
    return fatigue_plan.build_plan(rows, **kwargs)


def entry(plan, ad):
    return next(e for e in plan["ads"] if e["ad"] == ad)


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.plan = fatigue_plan.build_plan(cm.load_rows(str(FIXTURE)), capacity=2, start="2026-03-31")

    def test_the_planted_fatiguing_ad_is_fading_and_first_in_the_calendar(self):
        found = entry(self.plan, FADING_AD)
        self.assertEqual(found["status"], "fading")
        self.assertIn(found["days_left"], range(0, 6))
        first_week = self.plan["calendar"]["weeks"][0]["refreshes"]
        self.assertEqual(first_week[0]["ad"], FADING_AD)
        self.assertFalse(first_week[0]["late"])

    def test_the_young_ad_never_gets_days_left(self):
        found = entry(self.plan, YOUNG_AD)
        self.assertIn(found["status"], ("too little history", "too little delivery"))
        self.assertIsNone(found["days_left"])
        self.assertIn("delivery days, needs 9", found["reason"])

    def test_text_leads_with_the_answer(self):
        text = fatigue_plan.render(self.plan)
        self.assertRegex(text.splitlines()[0], r"^\d+ ads? (is|are) fading, \d+ (is|are) on course to fade within 6 weeks")
        self.assertIn("the queue clears by", text.splitlines()[1])
        self.assertIn("Week of 2026-03-31:", text)

    def test_default_start_is_the_day_after_the_last_date(self):
        plan = fatigue_plan.build_plan(cm.load_rows(str(FIXTURE)), capacity=2)
        self.assertEqual(plan["settings"]["start"], "2026-03-31")


class TrajectoryTest(unittest.TestCase):
    def test_constant_metric_is_steady_with_no_days_left(self):
        plan = plan_for(make_rows("1", [300] * 12) + make_rows("2", [100] * 12) + make_rows("3", [100] * 12))
        found = entry(plan, "1")
        self.assertEqual(found["slope"], 0)
        self.assertEqual(found["status"], "steady")
        self.assertIsNone(found["days_left"])
        self.assertEqual(found["days_left_note"], "not falling")

    def test_exact_falling_line_gives_exact_slope_and_days_left(self):
        # ctr falls 0.1 a day from 4.0; the other ads hold at 1.0, which sets the floor
        falling = [(4.0 - 0.1 * i) * 100 for i in range(12)]
        rows = make_rows("1", falling) + make_rows("2", [100] * 12) + make_rows("3", [100] * 12) \
            + make_rows("4", [100] * 12) + make_rows("5", [100] * 12)
        plan = plan_for(rows, fit_days=9, min_days=9)
        found = entry(plan, "1")
        self.assertAlmostEqual(found["slope"], -0.1, places=9)
        self.assertAlmostEqual(found["slope_se"], 0, places=9)
        self.assertAlmostEqual(found["floor"], 1.0)
        fitted_now = 4.0 - 0.1 * 11
        self.assertEqual(found["days_left"], round((fitted_now - found["floor"]) / 0.1))
        self.assertEqual(found["days_left_low"], found["days_left"])
        self.assertEqual(found["days_left_high"], found["days_left"])

    def test_a_line_still_above_the_floor_never_reads_as_at_it(self):
        # ends 0.04 above the floor while falling 0.1 a day: it crosses during the next day, not before today
        falling = [(1.04 + 0.1 * (11 - i)) * 100 for i in range(12)]
        rows = make_rows("1", falling) + make_rows("2", [100] * 12) + make_rows("3", [100] * 12) \
            + make_rows("4", [100] * 12) + make_rows("5", [100] * 12)
        found = entry(plan_for(rows, fit_days=9, min_days=9), "1")
        self.assertEqual(found["days_left"], 1)
        self.assertEqual((found["days_left_low"], found["days_left_high"]), (1, 1))
        self.assertNotEqual(fatigue_plan.describe_days_left(found), "already at or below the floor")

    def test_noisy_falling_line_has_an_ordered_range(self):
        noise = [0, 12, -9, 14, -11, 7, -13, 10, -6, 9, -8, 5]
        values = [(3.0 - 0.1 * i) * 100 + n for i, n in enumerate(noise)]
        rows = make_rows("1", values) + make_rows("2", [100] * 12) + make_rows("3", [100] * 12) \
            + make_rows("4", [100] * 12) + make_rows("5", [100] * 12)
        found = entry(plan_for(rows, fit_days=12), "1")
        self.assertGreater(found["slope_se"], 0)
        self.assertLessEqual(found["days_left_low"], found["days_left"])
        high = found["days_left_high"]
        self.assertTrue(high is None or found["days_left"] <= high)

    def test_fit_line_standard_error_needs_three_points(self):
        self.assertIsNone(fatigue_plan.fit_line([(1, 2.0), (2, 1.0)])["se"])
        self.assertIsNone(fatigue_plan.fit_line([(1, 2.0)]))

    def test_range_upper_end_is_open_when_the_slower_slope_is_flat(self):
        low, high = fatigue_plan.days_left_range(5.0, 1.0, -0.1, 0.2)
        self.assertEqual(low, round(4.0 / 0.3))
        self.assertIsNone(high)

    def test_at_the_floor_and_clearly_falling_is_on_course_not_fading(self):
        rows = make_rows("1", [(1.0 - 0.05 * i) * 100 for i in range(12)])
        rows += make_rows("2", [200] * 12) + make_rows("3", [200] * 12) + make_rows("4", [200] * 12)
        found = entry(plan_for(rows), "1")
        self.assertEqual(found["days_left"], 0)
        self.assertEqual(found["status"], "on course to fade")

    def test_a_noisy_flat_line_below_the_floor_is_not_on_course(self):
        values = [100, 104, 97, 103, 98, 102, 99, 101, 100, 103, 97, 100]
        rows = make_rows("1", values) + make_rows("2", [200] * 12) + make_rows("3", [200] * 12) + make_rows("4", [200] * 12)
        found = entry(plan_for(rows), "1")
        self.assertEqual(found["status"], "steady")

    def test_too_few_delivery_days_never_gets_a_number(self):
        found = entry(plan_for(make_rows("1", [300, 200, 100])), "1")
        self.assertEqual(found["status"], "too little history")
        self.assertIsNone(found["days_left"])
        self.assertEqual(found["reason"], "3 delivery days, needs 9")

    def test_low_impressions_are_not_judged(self):
        found = entry(plan_for(make_rows("1", [3] * 12, impressions=100), min_impressions=5000), "1")
        self.assertEqual(found["status"], "too little delivery")
        self.assertIsNone(found["days_left"])

    def test_trend_rule_marks_fading_when_frequency_rises(self):
        rows = []
        for i in range(12):
            reach = 10000 - i * 400
            rows.append({"date": (START + dt.timedelta(days=i)).isoformat(), "ad_id": "1", "ad_name": "a",
                         "spend": 100.0, "impressions": 10000, "reach": reach,
                         "link_clicks": (3.0 - 0.1 * i) * 100})
        rows += make_rows("2", [100] * 12) + make_rows("3", [100] * 12) + make_rows("4", [100] * 12)
        found = entry(plan_for(rows), "1")
        self.assertEqual(found["status"], "fading")
        self.assertLessEqual(found["trend"]["pct_change"], -8)
        self.assertGreaterEqual(found["trend"]["frequency_pct_change"], 8)


class MetricDirectionTest(unittest.TestCase):
    def test_lower_is_better_metrics_are_refused(self):
        rows = make_rows("1", [100] * 12)
        for metric in ("cpa", "cpm"):
            with self.assertRaises(ValueError) as caught:
                plan_for(rows, metric=metric)
            self.assertIn(metric, str(caught.exception))
            self.assertIn("ctr", str(caught.exception))

    def test_the_cli_exits_cleanly_on_a_lower_is_better_metric(self):
        done = run(FIXTURE, "--metric", "cpa")
        self.assertEqual(done.returncode, 2)
        self.assertIn("higher-is-better", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_frequency_and_account_level_metrics_are_refused(self):
        rows = make_rows("1", [100] * 12)
        for metric in ("frequency", "mer"):
            with self.assertRaises(ValueError) as caught:
                plan_for(rows, metric=metric)
            self.assertIn("use one of: hook_rate", str(caught.exception))
            self.assertNotIn("frequency", str(caught.exception).split("use one of:")[1])


class BandTest(unittest.TestCase):
    def rows(self):
        # the first day of the data has its own ad, so the later ads all launch inside the window
        early = make_rows("0", [100] * 12)
        late = []
        for ad, level in (("1", 100), ("2", 200), ("3", 300), ("4", 400)):
            shifted = make_rows(ad, [level] * 10)
            for row in shifted:
                row["date"] = (dt.date.fromisoformat(row["date"]) + dt.timedelta(days=1)).isoformat()
            late += shifted
        return early + late

    def test_below_band_count_uses_delivery_curve(self):
        rows = self.rows()
        with mock.patch.object(cm, "delivery_curve", wraps=cm.delivery_curve) as curve:
            plan = plan_for(rows, min_days=5)
        curve.assert_called_once()
        found = entry(plan, "1")
        series = cm.delivery_series(rows, "1", ["ctr"])[-6:]
        band = cm.delivery_curve(rows, ["ctr"], cm.CURVE_MIN_ADS)["ctr"]
        expected = sum(e["ctr"] < band[e["delivery_day"] - 1]["p25"] for e in series
                       if band[e["delivery_day"] - 1]["p25"] is not None)
        self.assertEqual(found["below_band_days"], expected)
        self.assertGreater(expected, 0)
        self.assertIn("below the account's band for its age for most of its last days", found["reason"])

    def test_ad_running_before_the_window_is_not_compared_with_the_band(self):
        found = entry(plan_for(self.rows(), min_days=5), "0")
        self.assertIsNone(found["below_band_days"])
        self.assertIn("running before the window began", found["reason"])


class CalendarTest(unittest.TestCase):
    def fading_rows(self, count, weeks_of_days=12):
        rows = []
        for n in range(count):
            for i in range(weeks_of_days):
                rows.append({"date": (START + dt.timedelta(days=i)).isoformat(), "ad_id": "f%d" % n,
                             "ad_name": "fade-%d" % n, "spend": 1000.0 - n * 100, "impressions": 10000,
                             "reach": 10000 - i * 400, "link_clicks": (3.0 - 0.1 * i) * 100})
        return rows

    def steady_rows(self):
        return make_rows("s1", [100] * 12) + make_rows("s2", [100] * 12) + make_rows("s3", [100] * 12)

    def test_capacity_one_puts_two_fading_ads_in_consecutive_weeks(self):
        plan = plan_for(self.fading_rows(2) + self.steady_rows(), capacity=1, start="2026-02-01")
        weeks = plan["calendar"]["weeks"]
        self.assertEqual([w["refreshes"][0]["ad"] for w in weeks[:2]], ["f0", "f1"])
        self.assertEqual(weeks[0]["week_start"], "2026-02-01")
        self.assertEqual(weeks[1]["week_start"], "2026-02-08")
        self.assertEqual([w["refreshes"][0]["late"] for w in weeks[:2]], [False, True])
        self.assertEqual(plan["calendar"]["late"], 1)
        self.assertEqual(plan["calendar"]["clears_by"], "2026-02-14")

    def test_largest_spend_goes_first(self):
        plan = plan_for(self.fading_rows(2) + self.steady_rows(), capacity=1, start="2026-02-01")
        self.assertEqual(plan["calendar"]["weeks"][0]["refreshes"][0]["ad"], "f0")

    def test_ads_past_the_horizon_are_listed_as_beyond_it(self):
        plan = plan_for(self.fading_rows(3) + self.steady_rows(), capacity=1, start="2026-02-01", weeks=2)
        self.assertEqual([i["ad"] for i in plan["calendar"]["beyond_horizon"]], ["f2"])
        text = fatigue_plan.render(plan)
        self.assertIn("Beyond the horizon: add capacity or extend --weeks", text)
        self.assertIn("1 more do not fit in 2 weeks", text)

    def test_no_capacity_prints_no_calendar_and_the_prompt(self):
        plan = plan_for(self.fading_rows(2) + self.steady_rows())
        self.assertIsNone(plan["calendar"])
        text = fatigue_plan.render(plan)
        self.assertIn("Give --capacity (ads you can make per week) for a dated refresh calendar.", text)
        self.assertNotIn("Week of", text)

    def test_on_course_ads_are_due_at_fade_date_minus_lead(self):
        rows = make_rows("1", [(3.0 - 0.05 * i) * 100 for i in range(12)]) + make_rows("2", [100] * 12) \
            + make_rows("3", [100] * 12) + make_rows("4", [100] * 12)
        plan = plan_for(rows, capacity=1, start="2026-02-01", lead_days=3)
        found = entry(plan, "1")
        self.assertEqual(found["status"], "on course to fade")
        item = plan["calendar"]["weeks"][0]["refreshes"][0]
        due = dt.date.fromisoformat(found["fade_date"]) - dt.timedelta(days=3)
        self.assertEqual(item["refresh_due"], due.isoformat())
        self.assertEqual(item["late"], dt.date(2026, 2, 1) > due)


class MissingDataTest(unittest.TestCase):
    def test_hook_rate_without_three_second_plays_is_unreadable(self):
        rows = cm.load_rows(make_rows("1", [100] * 12))
        plan = fatigue_plan.build_plan(rows, metric="hook_rate", min_impressions=100)
        found = entry(plan, "1")
        self.assertEqual(found["status"], "unreadable")
        self.assertIn("n/a (missing video_views_3s", found["reason"])
        self.assertIsNone(found["days_left"])
        self.assertNotIn(" 0", found["reason"])

    def test_empty_input(self):
        plan = fatigue_plan.build_plan([])
        self.assertEqual(plan["ads"], [])
        self.assertEqual(fatigue_plan.render(plan), "No ads with delivery in this data.")


class CommandLineTest(unittest.TestCase):
    def test_json_output_holds_settings_and_calendar(self):
        result = run(FIXTURE, "--capacity", 2, "--start", "2026-03-31", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["settings"]["capacity"], 2)
        self.assertEqual(data["settings"]["fit_days"], 9)
        self.assertEqual(data["calendar"]["weeks"][0]["refreshes"][0]["ad"], FADING_AD)

    def test_text_without_capacity(self):
        result = run(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Give --capacity", result.stdout)

    def test_capacity_zero_exits_2(self):
        result = run(FIXTURE, "--capacity", 0)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--capacity", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_bad_start_and_metric_and_file_exit_2(self):
        for args in (("--start", "soon"), ("--metric", "nope"), ()):
            path = FIXTURE if args else Path(tempfile.gettempdir()) / "missing-fatigue-plan.csv"
            result = run(path, *args)
            self.assertEqual(result.returncode, 2, args)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
