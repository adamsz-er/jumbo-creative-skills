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


if __name__ == "__main__":
    unittest.main()
