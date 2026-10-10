import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "creative-brief" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import creative_metrics as cm  # noqa: E402
import evidence  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
FATIGUING_AD = "120000000001"


def _without_spend(ad_id):
    rows = cm.load_rows(str(FIXTURE))
    for row in rows:
        if str(row.get("ad_id")) == ad_id:
            row["spend"] = None
    return rows


class MissingSpendTest(unittest.TestCase):
    def test_reported_spend_of_zero_is_not_n_a(self):
        self.assertEqual(evidence._spend_text(None, 2, 2), "0 spend reported")

    def test_an_ad_without_spend_has_no_share_and_says_why(self):
        result = evidence.build_evidence(_without_spend(FATIGUING_AD))
        found = next(r for r in result["records"] if r["ad"] == FATIGUING_AD)
        self.assertIsNone(found["spend_share"])
        self.assertEqual(found["spend_share_note"], "n/a (missing spend)")
        other = next(r for r in result["records"] if r["ad"] != FATIGUING_AD)
        self.assertIsNotNone(other["spend_share"])
        self.assertIsNone(other["spend_share_note"])

    def test_group_spend_counts_only_ads_that_report_it(self):
        result = evidence.build_evidence(_without_spend(FATIGUING_AD))
        member = next(a for a in result["angles"] if FATIGUING_AD in [str(i) for i in a["ads"]])
        self.assertLess(member["spend_reported"], len(member["ads"]))

    def test_a_partial_report_says_how_many_ads_report_spend(self):
        self.assertEqual(evidence._spend_text(7.0, 1, 2), "7% of spend (1 of 2 ads report spend)")
        self.assertEqual(evidence._spend_text(7.0, 2, 2), "7% of spend")

    def test_a_group_with_no_spend_at_all_has_no_share(self):
        rows = cm.load_rows(str(FIXTURE))
        for row in rows:
            row["spend"] = None
        result = evidence.build_evidence(rows)
        self.assertTrue(all(a["spend_share"] is None and a["spend_reported"] == 0 for a in result["angles"]))
        self.assertIn("spend share n/a (missing spend)", evidence.render_ideation(result))


class FixtureEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.result = evidence.build_evidence(cm.load_rows(str(FIXTURE)))
        self.text = evidence.render(self.result)

    def test_lists_top_quartile_ads_with_parsed_fields(self):
        top = self.result["top_quartile"]
        self.assertTrue(top)
        self.assertTrue(all(ad["concept"] and ad["format"] for ad in top))
        self.assertIn("Top-quartile ads", self.text)

    def test_lists_the_fatiguing_ad(self):
        self.assertIn(FATIGUING_AD, [ad["ad"] for ad in self.result["fatiguing"]])
        self.assertIn(FATIGUING_AD, self.text)

    def test_lists_at_least_one_gap(self):
        self.assertTrue(self.result["gaps"])
        self.assertIn("Coverage gaps", self.text)

    def test_a_fatiguing_ad_is_not_also_never_worked(self):
        fatiguing = {ad["ad"] for ad in self.result["fatiguing"]}
        never = {ad["ad"] for ad in self.result["never_worked"]}
        self.assertFalse(fatiguing & never)

    def test_states_the_basis(self):
        self.assertIn("never a benchmark", self.text.lower())

    def test_hook_text_is_stated_as_absent(self):
        self.assertIn("hook", self.text.lower())

    def test_header_names_the_ad_types_used_and_the_top_quartile_rule(self):
        self.assertIn("ad types bau", self.text)
        self.assertIn("all available payback metrics", self.text)

    def test_include_types_widens_the_gap_seeds(self):
        rows = cm.load_rows(str(FIXTURE))
        default = evidence.build_evidence(rows, max_gaps=1000)
        wider = evidence.build_evidence(rows, max_gaps=1000, include_types=("bau", "promo"))
        self.assertGreater(len(wider["gaps"]), len(default["gaps"]))
        self.assertIn("sale-bundle", {g["concept"] for g in wider["gaps"]})
        self.assertNotIn("sale-bundle", {g["concept"] for g in default["gaps"]})
        self.assertIn("ad types bau, promo", evidence.render(wider))

    def test_cli_accepts_include_types(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "evidence.py"), str(FIXTURE),
                              "--include-types", "bau,promo"], capture_output=True, text=True, check=True).stdout
        self.assertIn("ad types bau, promo", out)

    def test_json_round_trips(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "evidence.py"), str(FIXTURE), "--json"],
                             capture_output=True, text=True, check=True).stdout
        self.assertTrue(json.loads(out)["top_quartile"])


class MissingMetricTest(unittest.TestCase):
    def test_an_ad_with_one_ungradable_payback_metric_still_qualifies_on_the_other(self):
        rows = []
        for i in range(6):
            roas_value = 100.0 * (i + 1)
            rows.append({"Day": "2026-03-01", "Ad name": "c%d | static | house | bau | p | polished | 2026-03-01" % i,
                         "Ad ID": str(i), "Amount spent (USD)": 100.0, "Impressions": 5000,
                         "Link clicks": 50, "Purchases": 0, "Purchases conversion value": roas_value})
        result = evidence.build_evidence(cm.load_rows(rows))
        self.assertEqual(sorted(a["ad"] for a in result["top_quartile"]), ["4", "5"])


class EmptyEvidenceTest(unittest.TestCase):
    def _run(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            path.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPTS / "evidence.py"), str(path)],
                                  capture_output=True, text=True)

    def test_header_only_csv_prints_none_available(self):
        done = self._run("Day,Ad name,Ad ID,Amount spent (USD),Impressions\n")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "Evidence: none available")

    def test_empty_file_prints_none_available(self):
        done = self._run("")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "Evidence: none available")

    def test_unparseable_names_do_not_invent_evidence(self):
        done = self._run("Day,Ad name,Ad ID,Amount spent (USD),Impressions,Link clicks\n"
                         "2026-03-01,Ad 1 copy,1,10,5000,50\n")
        self.assertEqual(done.returncode, 0)
        self.assertNotIn("Top-quartile", done.stdout)



class AngleLabelAndPoolingTest(unittest.TestCase):
    """Labels that claim a result only when one was graded; a missing field never pools as a zero."""

    @staticmethod
    def _rec(ad, bands, top=False, bottom=False):
        return {"ad": ad, "concept": "trail", "format": "static", "spend": 100.0, "judged": True, "bands": bands,
                "payback_top": top, "payback_bottom": bottom, "never_worked": False, "fatigue": {}, "age_days": 9}

    def _label(self, *recs):
        return evidence._angles(list(recs), 100.0 * len(recs))[0]["label"]

    def test_middle_only_concept_is_middle_not_mixed(self):
        self.assertEqual(self._label(self._rec("a", {"roas": cm.BAND_MID, "cpa": cm.BAND_MID})), "middle")

    def test_ungraded_concept_is_ungraded_not_mixed(self):
        bands = {"roas": "not graded (too little comparison data)"}
        self.assertEqual(self._label(self._rec("a", bands)), "ungraded")

    def test_mixed_still_needs_a_top_and_a_weak_ad(self):
        self.assertEqual(self._label(self._rec("a", {"roas": cm.BAND_TOP}, top=True),
                                     self._rec("b", {"roas": cm.BAND_BOTTOM}, bottom=True)), "mixed")

    def test_no_angles_says_none(self):
        self.assertEqual(evidence._angle_lines({"angles": []})[-1], "  none")

    def test_partial_new_customer_data_pools_over_the_ads_that_report_it(self):
        ads = [{"ad_id": "a", "persona": "hiker", "spend": 50.0, "conversions": 10, "new_customers": 5},
               {"ad_id": "b", "persona": "hiker", "spend": 50.0, "conversions": 10, "new_customers": None}]
        for ad in ads:
            ad.update(cm.compute_metrics(ad))
        records = {"a": {"payback_top": False, "payback_bottom": False},
                   "b": {"payback_top": False, "payback_bottom": False}}
        row = evidence._segments(ads, records, "persona", 100.0)["rows"][0]
        self.assertAlmostEqual(row["new_customer_purchase_share"], 50.0)
        self.assertEqual(row["new_customer_note"], "over the 1 of 2 ads that report new customers")

    def test_reporting_ads_with_no_purchases_say_so(self):
        ads = [{"ad_id": "a", "persona": "hiker", "spend": 50.0, "conversions": 0, "new_customers": 0},
               {"ad_id": "b", "persona": "hiker", "spend": 50.0, "conversions": 10, "new_customers": None}]
        for ad in ads:
            ad.update(cm.compute_metrics(ad))
        records = {"a": {"payback_top": False, "payback_bottom": False},
                   "b": {"payback_top": False, "payback_bottom": False}}
        row = evidence._segments(ads, records, "persona", 100.0)["rows"][0]
        self.assertIsNone(row["new_customer_purchase_share"])
        self.assertTrue(row["new_customer_note"].startswith("n/a (missing purchases"))


class ZeroSalesStillCountTest(unittest.TestCase):
    def test_an_ad_with_no_sales_still_pools_into_cost_per_sale(self):
        ads = [{"ad_id": "a", "spend": 50.0, "conversions": 10}, {"ad_id": "b", "spend": 50.0, "conversions": 0}]
        for ad in ads:
            ad.update(cm.compute_metrics(ad))
        rate, reporting = evidence._rate_over_reporting(ads, "cpa")
        self.assertAlmostEqual(rate, 10.0)
        self.assertEqual(reporting, 2)


if __name__ == "__main__":
    unittest.main()
