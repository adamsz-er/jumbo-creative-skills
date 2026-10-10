import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "sale-planner" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sale_lift  # noqa: E402

SCRIPT = SCRIPTS / "sale_lift.py"
FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
EXTENDED = ROOT / "examples" / "acme" / "ads_daily_extended.csv"
START = dt.date(2026, 3, 2)  # weekday 0


def day(offset):
    return START + dt.timedelta(days=offset)


def rows_for(values, spend=50.0, orders=None, **extra):
    """One row per day: values maps a day offset to purchase value; orders defaults to value / 10."""
    rows = []
    for offset, value in values.items():
        row = {"date": day(offset).isoformat(), "ad_id": "1", "ad_name": "a", "impressions": 1000.0, "spend": spend,
               "conversions": value / 10 if orders is None else orders, "conversion_value": value}
        row.update({k: v(offset) if callable(v) else v for k, v in extra.items()})
        rows.append(row)
    return rows


def flat(days, value=100.0):
    return {i: value for i in range(days)}


def span(first, last, value):
    return {i: value for i in range(first, last)}


def merge(*parts):
    merged = {}
    for part in parts:
        merged.update(part)
    return merged


def build(rows, sale_from, sale_to, **kw):
    return sale_lift.build_sale(rows, day(sale_from), day(sale_to), **kw)


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class LiftTest(unittest.TestCase):
    def test_flat_baseline_and_a_sale_at_160(self):
        values = merge(flat(21), span(21, 28, 160.0))
        result = build(rows_for(values), 21, 27, post_days=0)
        value = result["measures"]["conversion_value"]
        self.assertEqual(value["expected"], 700)
        self.assertEqual(value["lift"], 420)
        self.assertAlmostEqual(value["lift_pct"], 60)

    def test_weekday_matching_expects_the_saturday_mean(self):
        values = {i: 200.0 if day(i).weekday() == 5 else 100.0 for i in range(21)}
        saturday = next(i for i in range(21, 28) if day(i).weekday() == 5)
        values[saturday] = 250.0
        result = build(rows_for(values), saturday, saturday, post_days=0)
        value = result["measures"]["conversion_value"]
        self.assertEqual(value["expected"], 200)
        self.assertEqual(value["lift"], 50)

    def test_a_missing_weekday_falls_back_to_the_all_day_mean_with_a_note(self):
        values = {i: 100.0 for i in range(21) if day(i).weekday() != 5}
        saturday = next(i for i in range(21, 28) if day(i).weekday() == 5)
        values[saturday] = 130.0
        result = build(rows_for(values), saturday, saturday, post_days=0)
        self.assertEqual(result["measures"]["conversion_value"]["expected"], 100)
        self.assertIn("no Saturday in the baseline: used the all-day mean", result["notes"])

    def test_zero_baseline_gives_no_percent(self):
        values = merge(flat(21, 0.0), {21: 40.0})
        value = build(rows_for(values), 21, 21, post_days=0)["measures"]["conversion_value"]
        self.assertEqual(value["lift"], 40)
        self.assertIsNone(value["lift_pct"])
        self.assertTrue(value["lift_pct_note"].startswith("n/a (missing baseline "))

    def test_a_sale_day_without_data_is_a_listed_gap(self):
        values = merge(flat(21), {21: 160.0, 23: 160.0})
        result = build(rows_for(values), 21, 23, post_days=0)
        self.assertEqual(result["sale"]["gaps"], [day(22).isoformat()])
        self.assertEqual(result["measures"]["conversion_value"]["expected"], 200)

    def test_gap_days_skip_the_teaser_period(self):
        values = merge(flat(14), span(14, 21, 500.0), span(21, 28, 160.0))
        result = build(rows_for(values), 21, 27, baseline_days=14, gap_days=7, post_days=0)
        self.assertEqual(result["baseline"]["to"], day(13).isoformat())
        self.assertEqual(result["measures"]["conversion_value"]["expected"], 700)


class ExcludeTest(unittest.TestCase):
    def promo_rows(self):
        return rows_for(merge(flat(21), span(5, 8, 300.0), span(21, 28, 160.0)))

    def test_excluded_days_leave_the_baseline(self):
        result = build(self.promo_rows(), 21, 27, post_days=0, exclude=[(day(5), day(7))])
        self.assertEqual(result["baseline"]["days"], 18)
        self.assertEqual(result["baseline"]["excluded"], [{"from": day(5).isoformat(), "to": day(7).isoformat(),
                                                           "baseline_days_removed": 3, "post_days_removed": 0}])
        self.assertEqual(result["measures"]["conversion_value"]["expected"], 700)
        text = sale_lift.render(result)
        self.assertIn("%s to %s" % (day(5), day(7)), text)
        self.assertIn("18 baseline days remain", text)
        self.assertIn("(baseline days removed: 3; post-sale days removed: 0)", text)
        self.assertNotIn("may include other promotions", text)

    def test_an_exclude_outside_both_windows_says_it_removed_nothing(self):
        result = build(self.promo_rows(), 21, 27, post_days=0, exclude=[(day(40), day(42))])
        self.assertEqual(result["baseline"]["days"], 21)
        self.assertEqual(result["baseline"]["excluded"][0]["baseline_days_removed"], 0)
        text = sale_lift.render(result)
        self.assertIn("removed nothing", text)
        self.assertIn("may include other promotions", text)

    def test_without_exclude_the_baseline_may_hold_other_promotions(self):
        result = build(self.promo_rows(), 21, 27, post_days=0)
        self.assertGreater(result["measures"]["conversion_value"]["expected"], 700)
        self.assertIn("may include other promotions: pass --exclude", sale_lift.render(result))

    def test_excluded_days_leave_the_post_sale_window(self):
        rows = rows_for(merge(flat(21), span(21, 28, 160.0), span(28, 30, 400.0), span(30, 37, 100.0)))
        result = build(rows, 21, 27, post_days=9, exclude=[(day(28), day(29))])
        self.assertEqual(result["pull_forward"]["days_used"], 7)

    def test_cli_exclude_is_repeatable_and_bad_input_exits_2(self):
        base = ["--sale-from", "2026-03-16", "--sale-to", "2026-03-22", "--baseline-days", 13]
        done = run(FIXTURE, *base, "--exclude", "2026-03-04:2026-03-05", "--exclude", "2026-03-08:2026-03-08")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Left out: 2026-03-04 to 2026-03-05 (baseline days removed: 2;", done.stdout)
        self.assertIn("Left out: 2026-03-08 to 2026-03-08 (baseline days removed: 1;", done.stdout)
        for bad in ("2026-03-04", "soon:2026-03-05", "2026-03-06:2026-03-05"):
            proc = run(FIXTURE, *base, "--exclude", bad)
            self.assertEqual(proc.returncode, 2, bad)
            self.assertIn("--exclude", proc.stderr)


class PullForwardTest(unittest.TestCase):
    def setUp(self):
        values = merge(flat(21), span(21, 28, 160.0), span(28, 33, 80.0))
        self.result = build(rows_for(values), 21, 27, post_days=5)

    def test_a_dip_after_the_sale_is_reported(self):
        pull = self.result["pull_forward"]
        self.assertEqual(pull["measures"]["conversion_value"]["lift"], -100)
        self.assertIn("a dip of 10 purchases after the sale: some of the sale's lift may be sales pulled forward from "
                      "these days", pull["dip"])

    def test_a_dip_that_rounds_to_nothing_is_not_a_caveat(self):
        values = merge(flat(21), span(21, 28, 160.0), span(28, 30, 99.8))
        self.assertIsNone(build(rows_for(values), 21, 27, post_days=2)["pull_forward"]["dip"])

    def test_net_lift_is_reduced_by_the_dip(self):
        net = self.result["net"]["conversion_value"]
        self.assertEqual(net["lift"], 320)
        self.assertIn("pulled forward", sale_lift.render(self.result))

    def test_post_days_past_the_data_are_counted_as_missing(self):
        values = merge(flat(21), span(21, 28, 160.0), span(28, 30, 80.0))
        pull = build(rows_for(values), 21, 27, post_days=5)["pull_forward"]
        self.assertEqual((pull["days_used"], pull["days_missing"]), (2, 3))

    def test_no_days_after_the_sale(self):
        values = merge(flat(21), span(21, 28, 160.0))
        result = build(rows_for(values), 21, 27, post_days=5)
        self.assertEqual(result["pull_forward"]["note"], "n/a (no days after the sale in the data)")
        self.assertFalse(result["net"]["includes_post"])
        self.assertEqual(result["net"]["conversion_value"]["lift"], 420)


class ContributionTest(unittest.TestCase):
    def setUp(self):
        values = merge(flat(21), span(21, 28, 160.0))
        self.rows = rows_for(values, spend=50.0)
        self.rows = [dict(r, spend=70.0) if r["date"] >= day(21).isoformat() else r for r in self.rows]

    def test_contribution_on_hand_checked_numbers(self):
        # 1120 * 0.40 - 700 * 0.55 - (490 - 350) = 448 - 385 - 140
        result = build(self.rows, 21, 27, post_days=0, margin=40, baseline_margin=55)
        self.assertAlmostEqual(result["contribution"]["sale"], -77)
        self.assertEqual(result["contribution"]["sale_and_post_note"], "n/a (no days after the sale in the data)")

    def test_baseline_margin_defaults_to_margin_with_a_note(self):
        result = build(self.rows, 21, 27, post_days=0, margin=40)
        self.assertAlmostEqual(result["contribution"]["sale"], 1120 * 0.4 - 700 * 0.4 - 140)
        self.assertIn("understates a discount's cost", result["contribution"]["baseline_margin_note"])

    def test_sale_and_post_window_adds_the_post_days(self):
        values = merge(flat(21), span(21, 28, 160.0), span(28, 30, 80.0))
        rows = rows_for(values, spend=50.0)
        result = build(rows, 21, 27, post_days=2, margin=40, baseline_margin=55)
        # sale: 1120*.4 - 700*.55 - (350-350) = 63; post, back at full price: 160*.55 - 200*.55 - 0 = -22
        self.assertAlmostEqual(result["contribution"]["sale"], 63)
        self.assertAlmostEqual(result["contribution"]["sale_and_post"], 41)

    def test_post_days_with_no_dip_add_nothing(self):
        values = merge(flat(21), span(21, 28, 160.0), span(28, 30, 100.0))
        result = build(rows_for(values, spend=50.0), 21, 27, post_days=2, margin=40, baseline_margin=55)
        self.assertAlmostEqual(result["contribution"]["sale_and_post"], result["contribution"]["sale"])

    def test_without_margin_the_line_is_not_available(self):
        result = build(self.rows, 21, 27, post_days=0)
        self.assertIn("contribution: n/a (give --margin to judge profit, not just revenue)", sale_lift.render(result))


class NewCustomerTest(unittest.TestCase):
    def test_missing_new_customers_is_not_zero(self):
        values = merge(flat(21), span(21, 28, 160.0))
        result = build(rows_for(values), 21, 27, post_days=0)
        self.assertIsNone(result["new_customers"]["sale"]["share"])
        self.assertEqual(result["new_customers"]["sale"]["note"], "n/a (missing new_customers)")
        self.assertIn("n/a (missing new_customers)", sale_lift.render(result))
        proc = run(FIXTURE, "--sale-from", "2026-03-16", "--sale-to", "2026-03-22",
                   "--baseline-days", 13, "--json")
        self.assertIsNone(json.loads(proc.stdout)["new_customers"]["sale"]["share"])

    def test_extended_fixture_has_a_share(self):
        proc = run(EXTENDED, "--sale-from", "2026-03-16", "--sale-to", "2026-03-22", "--baseline-days", 13, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        share = json.loads(proc.stdout)["new_customers"]["sale"]["share"]
        self.assertIsInstance(share, float)
        self.assertGreater(share, 0)


class BaselineAndValueTest(unittest.TestCase):
    def test_too_little_baseline_gives_no_lift(self):
        values = merge(flat(5), span(5, 12, 160.0))
        result = build(rows_for(values), 5, 11, post_days=0, min_baseline_days=7)
        self.assertFalse(result["judged"])
        self.assertNotIn("measures", result)
        text = sale_lift.render(result)
        self.assertIn("Too little baseline to judge: 5 dated days", text)
        self.assertNotIn("lift +", text)

    def test_a_revenue_column_leads_with_store_revenue(self):
        values = merge(flat(21), span(21, 28, 160.0))
        with_revenue = build(rows_for(values, revenue=lambda i: 300.0 if i >= 21 else 200.0), 21, 27, post_days=0)
        self.assertEqual(with_revenue["lead_value"], "revenue")
        self.assertIn("store revenue +700.00", with_revenue["lead"][0])
        self.assertNotIn("not store revenue", with_revenue["lead"][2])
        without = build(rows_for(values), 21, 27, post_days=0)
        self.assertIn("platform-attributed purchase value, not store revenue", without["lead"][2])

    def test_incremental_roas_needs_extra_spend(self):
        values = merge(flat(21), span(21, 28, 160.0))
        result = build(rows_for(values), 21, 27, post_days=0)
        self.assertIsNone(result["incremental_roas"]["value"])
        self.assertIn("n/a (", result["incremental_roas"]["note"])

    def test_incremental_roas_against_the_baseline_roas(self):
        values = merge(flat(21), span(21, 28, 160.0))
        rows = [dict(r, spend=60.0) if r["date"] >= day(21).isoformat() else r for r in rows_for(values)]
        result = build(rows, 21, 27, post_days=0)
        self.assertAlmostEqual(result["incremental_roas"]["value"], 6)
        self.assertEqual(result["incremental_roas"]["versus_baseline"], "beat")


class CliTest(unittest.TestCase):
    base = ["--sale-from", "2026-03-16", "--sale-to", "2026-03-22"]

    def test_filtered_read_prints_the_note(self):
        proc = run(FIXTURE, *self.base, "--baseline-days", 6, "--min-baseline-days", 5, "--where", "ad_type=promo")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cannot see the sale's effect on the other ads", proc.stdout)

    def test_unfiltered_read_has_no_filter_note(self):
        proc = run(FIXTURE, *self.base, "--baseline-days", 13)
        self.assertNotIn("filtered read", proc.stdout)
        self.assertIn("USD", proc.stdout)

    def test_basis_labels_each_window_flag_on_its_own(self):
        plain = run(FIXTURE, *self.base)
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertIn("--post-days 9 (default, arbitrary)", plain.stdout)
        self.assertIn("--gap-days 0 (default)", plain.stdout)
        self.assertNotIn("(yours)", plain.stdout)
        passed = run(FIXTURE, *self.base, "--post-days", 9)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("--post-days 9 (yours)", passed.stdout)
        self.assertIn("--baseline-days 21 (default, arbitrary)", passed.stdout)

    def test_json_carries_settings(self):
        proc = run(FIXTURE, *self.base, "--baseline-days", 13, "--margin", 40, "--json")
        data = json.loads(proc.stdout)
        self.assertEqual(data["settings"]["baseline_days"], 13)
        self.assertEqual(data["settings"]["baseline_margin"], 40)

    def test_sale_from_after_sale_to_exits_2(self):
        proc = run(FIXTURE, "--sale-from", "2026-03-22", "--sale-to", "2026-03-16")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("after --sale-to", proc.stderr)

    def test_dates_outside_the_data_exit_2_naming_the_window(self):
        proc = run(FIXTURE, "--sale-from", "2026-05-01", "--sale-to", "2026-05-07")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("2026-03-01 to 2026-03-30", proc.stderr)

    def test_a_bad_date_exits_2(self):
        proc = run(FIXTURE, "--sale-from", "soon", "--sale-to", "2026-03-22")
        self.assertEqual(proc.returncode, 2)

    def test_no_dated_rows_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "undated.json"
            path.write_text(json.dumps([{"Ad name": "a", "Ad ID": "1", "Amount spent (USD)": 5, "Impressions": 100}]))
            proc = run(path, *self.base)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no dated rows", proc.stderr)

    def test_baseline_margin_without_margin_exits_2(self):
        proc = run(FIXTURE, *self.base, "--baseline-margin", 40)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
