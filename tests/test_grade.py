import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "skills" / "creative-grader" / "scripts"))

import creative_metrics as cm  # noqa: E402
import grade  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
TOP, MID, BOTTOM = cm.BAND_TOP, cm.BAND_MID, cm.BAND_BOTTOM


def hand_ads():
    """Eight static ads: ctr 1..7 (the eighth has none), cpm 10..80."""
    ads = []
    for i in range(1, 9):
        ads.append({"ad_name": "ad%d" % i, "format": "static", "impressions": 10000,
                    "ctr": None if i == 8 else float(i), "cpm": 10.0 * i})
    return ads


class PercentileRankTest(unittest.TestCase):
    def test_none_and_too_few_values(self):
        self.assertIsNone(cm.percentile_rank(None, [1, 2, 3, 4, 5]))
        self.assertIsNone(cm.percentile_rank(3, [1, 2, 3, 4]))

    def test_ranks_run_zero_to_hundred(self):
        values = [1, 2, 3, 4, 5]
        self.assertLess(cm.percentile_rank(1, values), cm.percentile_rank(3, values))
        self.assertLess(cm.percentile_rank(3, values), cm.percentile_rank(5, values))
        self.assertAlmostEqual(cm.percentile_rank(3, values), 50.0)


class GradeAgainstTest(unittest.TestCase):
    def band(self, index, metric):
        ads = hand_ads()
        return cm.grade_against(ads[index], ads, metric)["band"]

    def test_higher_is_better_bands(self):
        self.assertEqual(self.band(0, "ctr"), BOTTOM)
        self.assertEqual(self.band(3, "ctr"), MID)
        self.assertEqual(self.band(6, "ctr"), TOP)

    def test_lower_is_better_bands_are_inverted(self):
        self.assertEqual(self.band(0, "cpm"), TOP)
        self.assertEqual(self.band(3, "cpm"), MID)
        self.assertEqual(self.band(7, "cpm"), BOTTOM)

    def test_none_value_is_not_graded(self):
        graded = cm.grade_against(hand_ads()[7], hand_ads(), "ctr")
        self.assertTrue(graded["band"].startswith("not graded"))
        self.assertIsNone(graded["value"])
        self.assertIsNone(graded["percentile"])

    def test_frequency_is_not_banded(self):
        ads = hand_ads()
        for ad in ads:
            ad["frequency"] = 1.5
        self.assertEqual(cm.grade_against(ads[0], ads, "frequency")["band"], "not banded")

    def test_too_few_comparable_ads_is_not_graded(self):
        ads = hand_ads()[:4]
        self.assertTrue(cm.grade_against(ads[0], ads, "ctr")["band"].startswith("not graded"))

    def test_result_states_its_basis(self):
        ads = hand_ads()
        graded = cm.grade_against(ads[0], ads, "ctr")
        self.assertEqual(graded["group"], "static")
        self.assertIn("basis", graded)


def day_row(name, fmt, impressions, spend=100.0, link_clicks=100.0, **extra):
    row = {"Day": "2026-03-01", "Ad name": name, "Ad ID": name, "Amount spent (USD)": spend,
           "Impressions": impressions, "Link clicks": link_clicks, "Purchases": 5,
           "Purchases conversion value": 400, "format": fmt}
    row.update(extra)
    return row


def synthetic_rows():
    rows = []
    for i in range(1, 9):
        rows.append(day_row("ad%d" % i, "static", 10000, spend=100.0, link_clicks=50.0 * i))
    return rows


class BottomHookAndCtrTest(unittest.TestCase):
    def rows(self):
        rows = []
        for i in range(1, 9):
            rows.append(day_row("vid%d" % i, "ugc-video", 10000, link_clicks=50.0 * i,
                                **{"3-second video plays": 1000.0 * i, "ThruPlays": 400.0 * i}))
        return rows

    def test_bottom_on_hook_and_ctr_diagnoses_hook(self):
        results = {r["ad"]: r for r in grade.grade_ads(cm.load_rows(self.rows()))}
        weakest = results["vid1"]
        self.assertEqual(weakest["grades"]["hook_rate"]["band"], BOTTOM)
        self.assertEqual(weakest["grades"]["ctr"]["band"], BOTTOM)
        self.assertEqual(weakest["diagnosis"]["step"], "hook")
        self.assertIn("first 3 seconds", weakest["diagnosis"]["action"])

    def test_diagnose_reads_the_funnel_in_order(self):
        bands = {"cpm": BOTTOM, "hook_rate": BOTTOM, "ctr": BOTTOM}
        self.assertEqual(grade.diagnose(bands)["step"], "reach cost")
        bands = {"cpm": MID, "hook_rate": MID, "hold_rate": BOTTOM, "ctr": BOTTOM}
        self.assertEqual(grade.diagnose(bands)["step"], "hold")
        bands = {"cpm": MID, "hook_rate": MID, "hold_rate": MID, "ctr": BOTTOM}
        self.assertEqual(grade.diagnose(bands)["step"], "click")

    def test_post_click_needs_a_healthy_ctr(self):
        diagnosis = grade.diagnose({"ctr": MID, "cvr": BOTTOM})
        self.assertEqual(diagnosis["step"], "post-click")
        self.assertIn("not the creative", diagnosis["action"])

    def test_payback_is_last_and_nothing_broken_says_so(self):
        self.assertEqual(grade.diagnose({"ctr": MID, "roas": BOTTOM})["step"], "pays back")
        self.assertEqual(grade.diagnose({"ctr": MID, "roas": TOP})["step"], "none")
        self.assertIn("no broken step", grade.diagnose({"ctr": MID})["summary"])

    def test_skipped_steps_are_named(self):
        diagnosis = grade.diagnose({"ctr": MID}, notes=("hook_rate n/a (missing video_views_3s)",))
        self.assertIn("hook_rate", " ".join(diagnosis["skipped"]))


class VolumeAndMissingFieldsTest(unittest.TestCase):
    def test_low_volume_ad_is_not_graded(self):
        rows = synthetic_rows() + [day_row("tiny", "static", 500, spend=5.0, link_clicks=1.0)]
        results = {r["ad"]: r for r in grade.grade_ads(cm.load_rows(rows))}
        tiny = results["tiny"]
        self.assertFalse(tiny["graded"])
        self.assertEqual(tiny["diagnosis"]["summary"], "not graded (low volume)")
        self.assertEqual(tiny["grades"]["ctr"]["band"], "not graded (low volume)")

    def test_static_ad_hook_is_na_and_diagnosis_says_it_skipped(self):
        results = grade.grade_ads(cm.load_rows(synthetic_rows()))
        first = results[0]
        self.assertEqual(first["grades"]["hook_rate"]["display"], "n/a (missing video_views_3s)")
        self.assertTrue(any("hook_rate" in note for note in first["diagnosis"]["skipped"]))


class FixtureTest(unittest.TestCase):
    def test_every_graded_ad_has_a_diagnosis_and_a_basis_header(self):
        rows = cm.load_rows(str(FIXTURE))
        results = grade.grade_ads(rows)
        self.assertEqual(len(results), 30)
        for entry in results:
            self.assertTrue(entry["diagnosis"]["summary"])
        header = grade.basis_header(rows, results)
        self.assertIn("2026-03-01", header)
        self.assertIn("2026-03-30", header)
        self.assertIn("Purchases", header)
        self.assertIn("link_clicks", header)


class ObjectiveAndGroupingTest(unittest.TestCase):
    def rows(self):
        rows = []
        for i in range(1, 10):
            rows.append(day_row("acme-traffic-%02d" % i, "static", 20000, spend=100.0, link_clicks=60.0 + 25 * i,
                                objective="OUTCOME_TRAFFIC", ad_type="bau", **{"Purchases": 0, "Purchases conversion value": 0}))
        for i in range(1, 10):
            rows.append(day_row("acme-sale-%02d" % i, "static", 20000, spend=100.0, link_clicks=100.0,
                                objective="OUTCOME_SALES", ad_type="bau",
                                **{"Purchases": 3 + i, "Purchases conversion value": (3 + i) * 70}))
        return rows

    def test_payback_metrics_follow_the_objective(self):
        self.assertEqual(cm.payback_metrics("OUTCOME_TRAFFIC")["metrics"], ("cpc", "ctr"))
        self.assertEqual(cm.payback_metrics("LINK_CLICKS")["objective"], "traffic")
        self.assertEqual(cm.payback_metrics("REACH")["metrics"], ("cpm", "hook_rate"))
        self.assertEqual(cm.payback_metrics("LEAD_GENERATION")["metrics"], ("cost_per_lead",))
        self.assertEqual(cm.payback_metrics("POST_ENGAGEMENT")["metrics"], ("engagement_rate", "cpm"))
        for sales in ("OUTCOME_SALES", "CONVERSIONS", "PRODUCT_CATALOG_SALES"):
            self.assertEqual(cm.payback_metrics(sales)["metrics"], ("cpa", "roas"))

    def test_unknown_objective_is_sales_with_a_note(self):
        for value in (None, "", "SOMETHING_NEW"):
            info = cm.payback_metrics(value)
            self.assertEqual(info["objective"], "sales")
            self.assertTrue(info["assumed"])
            self.assertIn("judged as sales", info["note"])

    def test_traffic_ads_are_graded_only_against_traffic_ads(self):
        results = {r["ad"]: r for r in grade.grade_ads(cm.load_rows(self.rows()))}
        traffic = results["acme-traffic-01"]
        self.assertEqual(traffic["objective"], "traffic")
        self.assertEqual(traffic["payback_metrics"], ["cpc", "ctr"])
        self.assertEqual(traffic["grades"]["cpc"]["band"], BOTTOM)
        self.assertEqual(traffic["diagnosis"]["step"], "click")
        self.assertEqual(traffic["graded_in_size"], 9)
        self.assertNotIn("pays back", traffic["diagnosis"]["summary"])
        self.assertTrue(traffic["grades"]["cpa"]["band"].startswith("not graded"))

    def test_basis_names_the_group_each_ad_was_graded_in_and_warns_when_thin(self):
        rows = cm.load_rows(self.rows())
        results = grade.grade_ads(rows)
        header = grade.basis_header(rows, results, ("format", "ad_type"))
        self.assertIn("static / bau (traffic) n=9", header)
        self.assertIn("WARNING small comparison groups", header)
        self.assertIn("Payback is read by objective", header)

    def test_default_group_by_is_format_then_ad_type_and_widens(self):
        rows = cm.load_rows(self.rows() + [day_row("acme-odd", "static", 20000, ad_type="promo", objective="OUTCOME_SALES")])
        odd = {r["ad"]: r for r in grade.grade_ads(rows)}["acme-odd"]
        self.assertEqual(odd["group_by"], ["format", "ad_type"])
        self.assertEqual(odd["graded_in"], "static")
        self.assertIn("format / ad_type has 1 comparable ads, under 5", odd["grades"]["ctr"]["fallback"])

    def test_missing_ad_type_column_drops_out_with_a_note_but_a_named_one_still_errors(self):
        rows = cm.load_rows([dict(r, ad_type=None) for r in self.rows()])
        ads = cm.aggregate_by_ad(rows)
        columns, note = cm.default_group_by(ads)
        self.assertEqual(columns, ("format",))
        self.assertIn("ad_type not in the data", note)
        with self.assertRaises(cm.GroupColumnError):
            cm.default_group_by(ads, ("nope",))

    def test_engagement_rate_and_cost_per_lead_follow_the_schema(self):
        ad = cm.aggregate_by_ad(cm.load_rows([{"ad_name": "a", "spend": 10, "impressions": 1000, "post_shares": 2,
                                               "post_save": 3, "comment": 5, "lead": 4}]))[0]
        self.assertAlmostEqual(ad["engagement_rate"], 1.0)
        self.assertAlmostEqual(ad["cost_per_lead"], 2.5)
        partial = cm.aggregate_by_ad(cm.load_rows([{"ad_name": "b", "spend": 10, "impressions": 1000, "post_shares": 2}]))[0]
        self.assertIsNone(partial["engagement_rate"])
        self.assertIn("missing saves and comments", cm.format_value(partial, "engagement_rate"))
        self.assertIsNone(partial["cost_per_lead"])


if __name__ == "__main__":
    unittest.main()
