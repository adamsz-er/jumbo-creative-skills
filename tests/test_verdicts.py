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
# Targets no ad reaches, so a never-worked ad may be paused (a pause needs the user's own target).
MISSED = {"cpa": 0.01, "roas": 1000.0, "cpc": 0.0001, "ctr": 99.0}


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
    def test_fatiguing_ad_is_iterated(self):
        verdict = fixture_verdicts()["120000000001"]
        self.assertTrue(verdict["fatiguing"])
        self.assertEqual(verdict["verdict_id"], "iterate")

    def test_young_ad_is_too_early_and_nothing_else(self):
        verdict = fixture_verdicts()["120000000030"]
        self.assertEqual(verdict["verdict_id"], "too_early")
        self.assertEqual(verdict["verdict"], "Too early (learning)")
        self.assertTrue(verdict["learning"])
        self.assertEqual(verdict["confidence"], "Can't judge yet")
        self.assertNotIn("pause", " ".join(verdict["reasons"]).lower())

    def test_never_worked_ad_is_paused_as_never_worked(self):
        verdict = fixture_verdicts(targets=MISSED)["120000000017"]
        self.assertEqual(verdict["verdict"], "Pause: never worked")
        self.assertEqual(verdict["verdict_id"], "pause_never_worked")

    def test_every_pause_carries_the_check_line(self):
        results = fixture_verdicts(targets=MISSED)
        pauses = [r for r in results.values() if r["verdict_id"].startswith("pause")]
        self.assertTrue(pauses)
        for entry in pauses:
            self.assertIn(CHECK, entry["check"])
        for entry in results.values():
            if not entry["verdict_id"].startswith("pause"):
                self.assertIsNone(entry["check"])

    def test_every_verdict_lists_reasons_a_sentence_and_a_confidence(self):
        for entry in fixture_verdicts().values():
            self.assertTrue(entry["reasons"], entry["ad"])
            self.assertTrue(entry["sentence"], entry["ad"])
            self.assertIn(entry["confidence"], ("Confident", "Early read", "Can't judge yet"))
            self.assertTrue(entry["confidence_reason"])
            self.assertEqual(entry["spend_at_stake"], entry["spend"])

    def test_no_user_facing_text_says_kill(self):
        rows = cm.load_rows(str(FIXTURE))
        results = verdicts.judge_ads(rows)
        args = type("A", (), dict(top_n=3, young_days=5, window=6, min_impressions=1000, protect_top=3, min_change=8.0))()
        text = verdicts.render(results, args, rows) + " ".join(r["verdict"] + r["sentence"] for r in results)
        self.assertNotIn("kill", text.lower())

    def test_small_wobbles_are_not_fatigue(self):
        self.assertFalse(fixture_verdicts()["120000000026"]["fatiguing"])

    def test_young_days_is_a_parameter(self):
        self.assertNotEqual(fixture_verdicts(young_days=5)["120000000025"]["verdict_id"], "too_early")
        self.assertEqual(fixture_verdicts(young_days=13)["120000000025"]["verdict_id"], "too_early")

    def test_summary_counts_and_concentration(self):
        rows = cm.load_rows(str(FIXTURE))
        results = verdicts.judge_ads(rows)
        summary = verdicts.summarise(results)
        self.assertEqual(sum(summary["counts"].values()), 30)
        self.assertIn("120000000030", summary["too_young"])
        self.assertIn("top 3 ads (N=3, an arbitrary default: set your own) hold", summary["concentration_line"])
        self.assertIn("top 2 ads (N=2", verdicts.summarise(results, top_n=2)["concentration_line"])


def make_rows(ad_id, days=8, spend=100.0, impressions=20000, clicks=200, conv=5, value=400, fmt="static",
              ad_type="bau", objective=None, shaped=None):
    """Synthetic daily rows for a fictional ad: constant per-day rates unless `shaped` rewrites a row."""
    rows = []
    for day in range(days):
        row = {"Day": "2026-03-%02d" % (day + 1), "Ad name": ad_id, "Ad ID": ad_id,
               "Amount spent (USD)": spend / days, "Impressions": impressions / days, "Link clicks": clicks / days,
               "format": fmt, "ad_type": ad_type}
        if conv is not None:
            row["Purchases"] = conv / days
            row["Purchases conversion value"] = value / days
        if objective:
            row["objective"] = objective
        rows.append(row)
    return rows


def crowd(count, prefix="acme-ad", **kwargs):
    """`count` ads of rising quality: ad 1 is the weakest on cost per sale and return, the last the best."""
    rows = []
    for i in range(1, count + 1):
        rows += make_rows("%s-%02d" % (prefix, i), conv=3 + i, value=(3 + i) * (60 + 4 * i), **kwargs)
    return rows


def judge(rows, **kwargs):
    kwargs.setdefault("young_days", 2)
    kwargs.setdefault("window", 3)
    kwargs.setdefault("currency", "USD")
    return {r["ad"]: r for r in verdicts.judge_ads(cm.load_rows(rows), **kwargs)}


class SafetyTest(unittest.TestCase):
    def test_true_pause_in_a_big_group_is_confident(self):
        weakest = judge(crowd(11), targets=MISSED)["acme-ad-01"]
        self.assertEqual(weakest["verdict_id"], "pause_never_worked")
        self.assertEqual(weakest["verdict"], "Pause: never worked")
        self.assertEqual(weakest["confidence"], "Confident")
        self.assertFalse(weakest["thin"])
        self.assertTrue(weakest["sentence"].startswith("Pause it:"))
        self.assertIn("per sale", weakest["sentence"])
        self.assertIn("USD", weakest["sentence"])
        self.assertNotIn("quartile", weakest["sentence"])
        self.assertIn(CHECK, weakest["check"])

    def test_thin_group_may_pause_but_only_as_an_early_read(self):
        weakest = judge(crowd(7), targets=MISSED)["acme-ad-01"]
        self.assertEqual(weakest["verdict_id"], "pause_never_worked")
        self.assertTrue(weakest["thin"])
        self.assertEqual(weakest["confidence"], "Early read")
        self.assertIn("small comparison group", weakest["sentence"])
        self.assertIn("small comparison group", weakest["confidence_reason"])

    def test_header_warns_about_thin_groups(self):
        rows = cm.load_rows(crowd(7))
        results = verdicts.judge_ads(rows, young_days=2, window=3)
        args = type("A", (), dict(top_n=3, young_days=2, window=3, min_impressions=1000, protect_top=3, min_change=8.0))()
        text = verdicts.render(results, args, rows, ("format", "ad_type"))
        self.assertIn("WARNING small comparison groups", text)
        self.assertIn("static / bau, sales objective n=7", text)

    def test_biggest_seller_in_a_small_group_is_not_paused(self):
        rows = crowd(4)
        rows += make_rows("acme-big", spend=1000.0, impressions=200000, clicks=2000, conv=20, value=5000)
        big = judge(rows)["acme-big"]
        self.assertNotIn(big["verdict_id"], ("pause_never_worked", "pause_fatigued"))
        self.assertEqual(big["verdict"], "Check before cutting")
        self.assertIn("cost per sale", " ".join(big["reasons"]).lower() + " cpa")
        self.assertTrue(big["payback"]["mixed"])
        self.assertEqual(big["confidence"], "Early read")

    def test_cheap_per_sale_but_small_sales_asks_about_order_value(self):
        rows = crowd(7)
        rows += make_rows("acme-small-orders", conv=40, value=120)
        entry = judge(rows)["acme-small-orders"]
        self.assertEqual(entry["verdict_id"], "check_mixed")
        self.assertIn("order value", entry["sentence"])
        self.assertEqual(entry["payback"]["bands"], {"cpa": cm.BAND_TOP, "roas": cm.BAND_BOTTOM})

    def test_a_top_seller_that_is_weak_everywhere_is_checked_not_paused(self):
        rows = crowd(11)
        rows += make_rows("acme-seller", spend=5000.0, impressions=900000, clicks=9000, conv=60, value=2400)
        entry = judge(rows)["acme-seller"]
        self.assertEqual(entry["payback"]["bands"], {"cpa": cm.BAND_BOTTOM, "roas": cm.BAND_BOTTOM})
        self.assertEqual(entry["verdict_id"], "check_top_seller")
        self.assertIn("biggest sellers", entry["sentence"])
        self.assertIsNone(entry["check"])

    def test_protect_top_zero_lets_it_be_paused(self):
        rows = crowd(11) + make_rows("acme-seller", spend=5000.0, impressions=900000, clicks=9000, conv=60, value=2400)
        self.assertEqual(judge(rows, protect_top=0, targets=MISSED)["acme-seller"]["verdict_id"], "pause_never_worked")

    def test_no_conversion_data_is_cant_judge_never_a_decision(self):
        rows = []
        for i in range(1, 8):
            rows += make_rows("acme-nodata-%d" % i, conv=None, clicks=100 + 10 * i)
        results = judge(rows)
        for entry in results.values():
            self.assertEqual(entry["verdict_id"], "cant_judge", entry["ad"])
            self.assertTrue(entry["verdict"].startswith("Can't judge: missing"), entry["verdict"])
            self.assertEqual(entry["confidence"], "Can't judge yet")
            self.assertTrue(entry["sentence"].startswith("Can't judge yet:"))
            self.assertIn("purchase", entry["sentence"])
            self.assertIsNone(entry["check"])

    def test_traffic_ads_are_judged_on_clicks_not_purchases(self):
        rows = crowd(6, prefix="acme-sale")
        for i in range(1, 12):
            rows += make_rows("acme-traffic-%02d" % i, conv=0, value=0, spend=100.0, clicks=60 + 25 * i,
                              impressions=20000, objective="OUTCOME_TRAFFIC")
        results = judge(rows, targets=MISSED)
        weakest = results["acme-traffic-01"]
        self.assertEqual(weakest["objective"], "traffic")
        self.assertEqual(set(weakest["payback"]["bands"]), {"cpc", "ctr"})
        self.assertEqual(weakest["group_size"], 11)
        self.assertEqual(weakest["verdict_id"], "pause_never_worked")
        self.assertIn("per click", weakest["sentence"])
        self.assertNotIn("per sale", weakest["sentence"])
        self.assertIn("click", weakest["payback_basis"])
        for ad, entry in results.items():
            if ad.startswith("acme-traffic"):
                self.assertNotIn("cpa", entry["payback"]["bands"])

    def test_an_unknown_objective_is_judged_as_sales_and_says_so(self):
        entry = judge(crowd(7))["acme-ad-01"]
        self.assertEqual(entry["objective"], "sales")
        self.assertTrue(entry["objective_assumed"])
        self.assertIn("judged as sales", " ".join(entry["reasons"]))

    def test_group_falls_back_from_format_and_type_to_format(self):
        rows = crowd(7)
        rows += make_rows("acme-promo", conv=9, value=700, ad_type="promo")
        entry = judge(rows)["acme-promo"]
        self.assertEqual(entry["payback"]["group_by"], ["format"])
        self.assertIn("format / ad_type has 1 comparable ads, under 5", " ".join(entry["reasons"]))


class TargetTest(unittest.TestCase):
    def test_never_worked_without_a_target_is_a_check_that_asks_for_one(self):
        weakest = judge(crowd(11))["acme-ad-01"]
        self.assertEqual(weakest["verdict_id"], "check_no_target")
        self.assertEqual(weakest["verdict"], "Check before cutting")
        self.assertIn("Set a target", weakest["sentence"])
        self.assertIn("no target is set", " ".join(weakest["reasons"]))
        self.assertIsNone(weakest["check"])

    def test_a_target_set_for_another_objective_does_not_count(self):
        self.assertEqual(judge(crowd(11), targets={"cpc": 0.0001})["acme-ad-01"]["verdict_id"], "check_no_target")

    def test_meeting_any_target_keeps_it_from_a_pause(self):
        weakest = judge(crowd(11), targets={"cpa": 1000.0})["acme-ad-01"]
        self.assertEqual(weakest["verdict_id"], "check_meets_target")
        self.assertIn("still meets your cpa target", weakest["sentence"])

    def test_missing_the_target_pauses_and_says_so(self):
        weakest = judge(crowd(11), targets={"cpa": 0.01})["acme-ad-01"]
        self.assertEqual(weakest["verdict_id"], "pause_never_worked")
        reasons = " ".join(weakest["reasons"])
        self.assertIn("it misses your target: cpa: it costs USD", reasons)
        self.assertIn("target USD 0.01", reasons)

    def test_parse_targets_reads_aliases_and_refuses_bad_values(self):
        self.assertEqual(cm.parse_targets("CPA=40,roas=3"), {"cpa": 40.0, "roas": 3.0})
        for bad in ("cpa=abc", "cpa=0", "nonsense=3"):
            with self.assertRaises((ValueError, KeyError)):
                cm.parse_targets(bad)


class ReviewFixesTest(unittest.TestCase):
    def tie_rows(self, order):
        rows = []
        conv = {"A": 2, "B": 5, "C": 4, "D": 3, "E": 3}
        for name in order:
            rows += make_rows("acme-%s" % name, conv=conv[name], value=conv[name] * 60)
        return rows

    def test_ties_at_the_protected_place_are_protected_whatever_the_row_order(self):
        first = judge(self.tie_rows("ABCDE"))
        second = judge(self.tie_rows("ABCED"))
        for name in ("acme-D", "acme-E"):
            self.assertEqual(first[name]["verdict_id"], "check_top_seller", name)
            self.assertEqual(second[name]["verdict_id"], "check_top_seller", name)

    def test_cost_per_click_follows_the_click_type_ctr_uses(self):
        rows = []
        for i in range(1, 7):
            ad = make_rows("acme-traffic-%d" % i, conv=None, clicks=60 + 20 * i, objective="OUTCOME_TRAFFIC")
            for r in ad:
                r["Clicks (all)"] = (600 - 20 * i) / len(ad)
            rows += ad
        results = judge(rows)
        for entry in results.values():
            self.assertFalse(entry["payback"]["mixed"], entry["ad"])
        ad = cm.aggregate_by_ad(cm.load_rows(rows))[0]
        self.assertEqual(cm.metric_basis(ad, "cpc")["denominator"], "link_clicks")
        self.assertIn("link_clicks", " ".join(results["acme-traffic-1"]["reasons"]))

    def test_comparable_count_is_true_for_tiny_accounts(self):
        one = judge(make_rows("acme-solo"))["acme-solo"]
        self.assertEqual(one["verdict_id"], "cant_judge")
        self.assertIn("only 1 comparable", one["sentence"])
        three = judge(crowd(3))["acme-ad-01"]
        self.assertIn("only 3 comparable", three["sentence"])
        ads = cm.aggregate_by_ad(cm.load_rows(crowd(3)))
        self.assertEqual(cm.grade_against(ads[0], ads, "cpa")["n_comparable"], 3)

    def test_thin_group_pause_needs_two_windows_of_delivery(self):
        rows = []
        for i in range(2, 8):
            rows += make_rows("acme-ad-%02d" % i, conv=3 + i, value=(3 + i) * (60 + 4 * i))
        rows += make_rows("acme-short", days=3, conv=4, value=4 * 64)
        short = judge(rows)["acme-short"]
        self.assertTrue(short["thin"])
        self.assertEqual(short["verdict_id"], "check_immature")
        self.assertEqual(short["verdict"], "Check before cutting")
        self.assertIn("only delivered 3 days", short["sentence"])
        self.assertIsNone(short["check"])

    def test_pause_sentence_counts_delivery_days(self):
        entry = judge(crowd(11), targets=MISSED)["acme-ad-01"]
        self.assertEqual(entry["active_days"], len(set(r["Day"] for r in make_rows("x"))))
        self.assertIn("after %d days" % entry["active_days"], entry["sentence"])

    def test_zero_spend_ad_cannot_be_judged_on_cost(self):
        rows = crowd(7) + make_rows("acme-zero", spend=0.0, conv=5, value=400)
        entry = judge(rows)["acme-zero"]
        self.assertEqual(entry["verdict_id"], "cant_judge")
        self.assertIn("missing spend", entry["verdict"])
        self.assertNotIn("USD 0.00", entry["sentence"])

    def test_group_with_no_spread_cannot_grade_an_outlier(self):
        rows = []
        for i in range(5):
            rows += make_rows("acme-same-%d" % i, conv=5, value=400)
        rows += make_rows("acme-worse", conv=1, value=50)
        entry = judge(rows)["acme-worse"]
        self.assertEqual(entry["verdict_id"], "cant_judge")
        self.assertIn("no spread in group", entry["verdict"])
        ads = cm.aggregate_by_ad(cm.load_rows(rows))
        worse = next(a for a in ads if a["ad_name"] == "acme-worse")
        self.assertEqual(cm.grade_against(worse, ads, "cpa")["band"], "not graded (no spread in group)")


class OrderingTest(unittest.TestCase):
    def test_do_first_is_by_spend_at_stake_and_never_cant_judge(self):
        rows = crowd(11)
        rows += make_rows("acme-nodata-huge", spend=99999.0, impressions=900000, clicks=9000, conv=None)
        results = verdicts.judge_ads(cm.load_rows(rows), young_days=2, window=3)
        by_id = {r["ad"]: r for r in results}
        self.assertEqual(by_id["acme-nodata-huge"]["verdict_id"], "cant_judge")
        first = verdicts.do_first(results)
        self.assertTrue(first)
        self.assertLessEqual(len(first), 5)
        self.assertNotIn("acme-nodata-huge", [f["ad"] for f in first])
        self.assertEqual([f["spend_at_stake"] for f in first], sorted((f["spend_at_stake"] for f in first), reverse=True))
        for item in first:
            self.assertNotEqual(item["verdict_id"], "cant_judge")
            self.assertIn("sentence", item)

    def test_verdict_lists_are_sorted_by_spend_at_stake(self):
        rows = cm.load_rows(str(FIXTURE))
        results = verdicts.judge_ads(rows)
        args = type("A", (), dict(top_n=3, young_days=5, window=6, min_impressions=1000, protect_top=3, min_change=8.0))()
        text = verdicts.render(results, args, rows, ("format", "ad_type"))
        block = text.split("Verdicts (largest spend at stake first within each):")[1]
        scale = [r for r in sorted(results, key=lambda r: -(r["spend"] or 0)) if r["verdict_id"] == "scale"]
        order = [block.index("\n%s  [" % r["ad"]) for r in scale]
        self.assertEqual(order, sorted(order))

    def test_json_keeps_old_fields_and_adds_new_ones(self):
        entry = fixture_verdicts()["120000000001"]
        for field in ("ad", "ad_id", "ad_name", "format", "spend", "age_days", "learning", "verdict", "fatiguing",
                      "fatigue", "payback", "reasons", "check", "verdict_id", "confidence", "confidence_reason",
                      "sentence", "spend_at_stake", "payback_basis", "objective"):
            self.assertIn(field, entry)
        self.assertIn("bands", entry["payback"])
        self.assertIn("known", entry["payback"])


if __name__ == "__main__":
    unittest.main()
