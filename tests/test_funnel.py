import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "funnel-diagnosis" / "scripts"
sys.path.insert(0, str(SCRIPT))

import creative_metrics as cm  # noqa: E402
import funnel  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
EXTENDED = ROOT / "examples" / "acme" / "ads_daily_extended.csv"
BROKEN_PAGE_AD = "120000000002"
FATIGUING_AD = "120000000001"


def synthetic(days: int = 20, ads: int = 6, checkout_after=None, site_fields: bool = True):
    """Daily rows for a few steady ads; checkouts can halve after a given day."""
    rows = []
    for ad in range(ads):
        for day in range(days):
            checkouts = 40
            if checkout_after is not None and day >= checkout_after:
                checkouts = 20
            row = {"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad,
                   "Ad ID": "9000%d" % ad, "Amount spent (USD)": 100, "Impressions": 20000,
                   "Link clicks": 300}
            if site_fields:
                row.update({"Purchases": 10, "Adds to cart": 90, "Landing page views": 280,
                            "Checkouts initiated": checkouts})
            rows.append(row)
    return cm.load_rows(rows)


def build(rows, **kw):
    args = dict(key_map=None, wanted=[], group_by=["format"], window=6, min_change=8.0, min_impressions=1000,
                z=cm.FUNNEL_Z)
    args.update(kw)
    return funnel.build_funnel(rows, **args)


def run_cli(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT / "funnel.py"), *args], capture_output=True, text=True)


class ExtendedFixtureTest(unittest.TestCase):
    def setUp(self):
        self.rows = cm.load_rows(str(EXTENDED))
        self.result = build(self.rows)

    def test_broken_landing_page_is_a_site_call_and_listed_first(self):
        first = self.result["ads"][0]
        self.assertEqual(first["ad"], BROKEN_PAGE_AD)
        self.assertEqual(first["call"], "site")
        self.assertIn("landing_page_view_rate", first["weak_steps"])

    def test_lead_names_the_ad_and_the_fall(self):
        text = funnel.render(self.result)
        lead = text.splitlines()[1]
        self.assertIn("ctr holds", lead)
        self.assertIn("landing page view rate fell", lead)
        self.assertIn("check the page before touching the creative", lead)

    def test_fatiguing_ad_is_a_creative_call(self):
        reads = {r["ad"]: r for r in self.result["ads"]}
        self.assertEqual(reads[FATIGUING_AD]["call"], "creative")

    def test_calls_equal_the_shared_rule(self):
        ads = cm.aggregate_by_ad(self.rows)
        for read in self.result["ads"]:
            ad = next(a for a in ads if a["ad_id"] == read["ad"])
            self.assertEqual(read["call"], cm.funnel_read(self.rows, ad, ads)["call"])

    def test_ordered_site_both_creative_neither_unreadable(self):
        order = [funnel.CALL_ORDER.index(r["call"]) for r in self.result["ads"]]
        self.assertEqual(order, sorted(order))

    def test_checklist_pointer_printed_for_a_site_call(self):
        self.assertIn(funnel.CHECKLIST, funnel.render(self.result))

    def test_counts_add_up(self):
        self.assertEqual(sum(self.result["counts"].values()), len(self.result["ads"]))


class BaseFixtureTest(unittest.TestCase):
    def setUp(self):
        self.rows = cm.load_rows(str(FIXTURE))
        self.result = build(self.rows)
        self.text = funnel.render(self.result)

    def test_no_ad_is_a_site_call_because_of_landing_pages(self):
        for read in self.result["ads"]:
            self.assertNotIn("landing_page_view_rate", read["weak_steps"])
            self.assertNotIn("cart_to_checkout_rate", read["weak_steps"])

    def test_missing_site_steps_are_named_with_the_export_column(self):
        self.assertIn("n/a (missing landing_page_views", self.text)
        self.assertIn('add the export column "Landing page views"', self.text)
        self.assertIn('"Checkouts initiated"', self.text)
        self.assertEqual(self.result["missing_columns"]["landing_page_view_rate"], ["Landing page views"])
        read = self.result["ads"][0]
        steps = {s["metric"]: s for s in read["steps"]}
        self.assertIsNone(steps["landing_page_view_rate"]["value"])
        self.assertIn("missing landing_page_views", steps["landing_page_view_rate"]["note"])

    def test_fatiguing_ad_is_creative(self):
        reads = {r["ad"]: r for r in self.result["ads"]}
        self.assertEqual(reads[FATIGUING_AD]["call"], "creative")


class AccountReadTest(unittest.TestCase):
    def test_halved_checkouts_everywhere_is_a_site_call(self):
        account = build(synthetic(checkout_after=13))["account"]
        self.assertEqual(account["call"], "site")
        self.assertIn("cart_to_checkout_rate", account["weak_steps"])
        self.assertNotIn("ctr", account["weak_steps"])

    def test_without_the_drop_the_account_is_neither(self):
        self.assertEqual(build(synthetic())["account"]["call"], "neither")

    def test_attention_only_drop_with_steady_site_rates(self):
        rows = synthetic()
        for row in rows:
            if row["date"] >= "2026-04-14":
                row["link_clicks"] = 200
                row["landing_page_views"] = 280 * 200 / 300
        account = build(rows)["account"]
        self.assertEqual(account["call"], "creative")
        self.assertEqual(account["weak_steps"], ["ctr"])

    def test_no_site_fields_is_unreadable(self):
        result = build(synthetic(site_fields=False))
        self.assertEqual(result["account"]["call"], "unreadable")
        self.assertTrue(result["ads"])
        self.assertTrue(all(r["call"] == "unreadable" for r in result["ads"]))
        self.assertNotIn(funnel.CHECKLIST, funnel.render(result))

    def test_a_short_run_cannot_be_compared(self):
        account = build(synthetic(days=8))["account"]
        self.assertFalse(account["trend_readable"])
        self.assertIn("n/a (fewer than twice the window (2 x 6 delivery days)", funnel.render(build(synthetic(days=8))))

    def test_account_steps_missing_a_field_are_null(self):
        steps = {s["metric"]: s for s in build(synthetic(site_fields=False))["account"]["steps"]}
        self.assertIsNone(steps["landing_page_view_rate"]["first"])
        self.assertFalse(steps["landing_page_view_rate"]["readable"])


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.rows = cm.load_rows(str(EXTENDED))

    def test_ad_by_id_and_by_name(self):
        by_id = build(self.rows, wanted=[BROKEN_PAGE_AD])
        self.assertEqual([r["ad"] for r in by_id["ads"]], [BROKEN_PAGE_AD])
        name = by_id["ads"][0]["ad_name"]
        self.assertEqual([r["ad"] for r in build(self.rows, wanted=[name])["ads"]], [BROKEN_PAGE_AD])

    def test_unknown_ad_raises(self):
        with self.assertRaises(ValueError):
            build(self.rows, wanted=["nope"])

    def test_unknown_group_column_raises(self):
        with self.assertRaises(cm.GroupColumnError):
            build(self.rows, group_by=["nonsense"])

    def test_thin_ads_are_listed_not_judged(self):
        result = build(self.rows, min_impressions=10 ** 9)
        self.assertEqual(result["ads"], [])
        self.assertEqual(len(result["too_little_delivery"]), 30)
        self.assertIn("too little delivery to judge", funnel.render(result))

    def test_empty_input(self):
        self.assertEqual(funnel.render(build([])), "Funnel diagnosis: no ads to judge.")


class CliTest(unittest.TestCase):
    def test_text_exit_zero(self):
        done = run_cli(str(EXTENDED))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("account-wide", done.stdout)

    def test_json_round_trips(self):
        done = run_cli(str(EXTENDED), "--json", "--ad", BROKEN_PAGE_AD)
        self.assertEqual(done.returncode, 0, done.stderr)
        data = json.loads(done.stdout)
        self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertEqual(data["ads"][0]["call"], "site")
        self.assertEqual(data["settings"]["window"], 6)
        for key in ("settings", "window", "account", "ads", "too_little_delivery", "counts", "missing_columns"):
            self.assertIn(key, data)

    def test_unknown_ad_exits_two(self):
        done = run_cli(str(EXTENDED), "--ad", "nope")
        self.assertEqual(done.returncode, 2)
        self.assertIn("nope", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_unknown_group_by_exits_two(self):
        done = run_cli(str(EXTENDED), "--group-by", "nonsense")
        self.assertEqual(done.returncode, 2)
        self.assertNotIn("Traceback", done.stderr)

    def test_missing_file_exits_two(self):
        self.assertEqual(run_cli(str(ROOT / "no-such.csv")).returncode, 2)



class TooLittleEvidenceTest(unittest.TestCase):
    def test_short_history_and_a_small_group_is_unjudged_not_neither(self):
        result = build(synthetic(days=5, ads=3))
        self.assertEqual({r["call"] for r in result["ads"]}, {"unjudged"})
        self.assertEqual(result["account"]["call"], "unjudged")
        self.assertEqual(result["counts"]["neither"], 0)

    def test_short_history_never_asks_for_columns_that_are_there(self):
        result = build(synthetic(days=5, ads=3))
        self.assertTrue(all(s["readable"] for s in result["account"]["steps"] if s["side"] == "site"))
        self.assertNotIn("could not be read", funnel.render(result))

    def test_unjudged_is_a_real_call_with_its_own_reason(self):
        self.assertIn("unjudged", funnel.CALL_ORDER)
        self.assertIn("no call", cm.FUNNEL_CALLS["unjudged"])


class DayFirstDatesTest(unittest.TestCase):
    def test_day_first_dates_across_a_month_end_pick_the_same_windows(self):
        iso = synthetic(days=19, checkout_after=12)
        day_first = []
        for row in iso:
            copy = dict(row)
            day = cm._parse_date(row["date"]) - (cm._parse_date(iso[0]["date"]) - cm._parse_date("2026-02-20"))
            copy["date"] = day.strftime("%d/%m/%Y")
            day_first.append(copy)
        a, b = build(iso)["account"], build(day_first)["account"]
        self.assertEqual(a["call"], "site")
        self.assertEqual(b["call"], a["call"])
        self.assertEqual([s["first"] for s in b["steps"]], [s["first"] for s in a["steps"]])


class PooledPeersTest(unittest.TestCase):
    def test_a_peer_missing_the_numerator_is_left_out_of_the_pooled_rate(self):
        raw = []
        for ad in range(9):
            for day in range(20):
                row = {"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad,
                       "Ad ID": "9000%d" % ad, "Amount spent (USD)": 100, "Impressions": 20000, "Link clicks": 300,
                       "Purchases": 10, "Adds to cart": 90, "Checkouts initiated": 40}
                if ad < 6:
                    row["Landing page views"] = 200 if ad == 0 else 280 - ad
                raw.append(row)
        rows = cm.load_rows(raw)
        ads = cm.aggregate_by_ad(rows)
        weak = next(a for a in ads if a["ad_id"] == "90000")
        step = next(s for s in cm.funnel_read(rows, weak, ads)["steps"] if s["metric"] == "landing_page_view_rate")
        peers = [a for a in ads if a is not weak and a.get("landing_page_views") is not None]
        expected = cm.proportion_z(sum(a["landing_page_views"] for a in peers), sum(a["link_clicks"] for a in peers),
                                   weak["landing_page_views"], weak["link_clicks"])
        self.assertAlmostEqual(step["gap_z"], expected)


if __name__ == "__main__":
    unittest.main()
