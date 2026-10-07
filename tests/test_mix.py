import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "skills" / "creative-mix" / "scripts"))

import creative_metrics as cm  # noqa: E402
import mix  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"


def row(name, spend=100.0):
    return {"Day": "2026-03-01", "Ad name": name, "Ad ID": name, "Amount spent": spend,
            "Impressions": 10000, "Link clicks": 100, "Purchases": 4, "Purchases conversion value": 300}


class UnclassifiedTest(unittest.TestCase):
    def test_unparseable_names_are_kept_and_counted(self):
        rows = cm.load_rows([
            row("durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01"),
            row("social-proof | static | house | bau | day-pack | polished | 2026-03-01"),
            row("sale-bundle | carousel | house | promo | camp-stove | polished | 2026-03-09"),
            row("Ad 1 - copy"), row("weird_name"),
        ])
        result = mix.analyse_mix(rows)
        self.assertEqual(result["unclassified"]["count"], 2)
        self.assertEqual(sorted(result["unclassified"]["ads"]), ["Ad 1 - copy", "weird_name"])
        self.assertEqual(result["classified"], 3)
        self.assertEqual(sum(r["ads"] for r in result["by_format"]), 3)

    def test_unclassified_spend_is_not_dropped(self):
        rows = cm.load_rows([row("Ad 1 - copy", spend=40.0),
                             row("a | static | house | bau | p | polished | 2026-03-01", spend=60.0)])
        self.assertAlmostEqual(mix.analyse_mix(rows)["unclassified"]["spend"], 40.0)


class FamilyTest(unittest.TestCase):
    def test_variants_of_one_concept_are_one_family(self):
        self.assertEqual(mix.concept_families(["gift-guide", "gift-guide-two", "social-proof",
                                                "social-proof-reviews", "problem-first"]),
                         {"gift-guide": "gift-guide", "gift-guide-two": "gift-guide",
                          "social-proof": "social-proof", "social-proof-reviews": "social-proof",
                          "problem-first": "problem-first"})


class NoFamilyTest(unittest.TestCase):
    def test_families_list_their_members_and_can_be_turned_off(self):
        rows = cm.load_rows(str(FIXTURE))
        on = mix.analyse_mix(rows)
        self.assertIn({"concept": "gift-guide", "variants": ["gift-guide", "gift-guide-two"],
                       "ads": ["120000000005", "120000000029"]}, on["duplicates"])
        off = mix.analyse_mix(rows, families=False)
        self.assertEqual(off["duplicates"], [])
        self.assertGreater(len(off["by_concept"]), len(on["by_concept"]))


class FixtureMixTest(unittest.TestCase):
    def setUp(self):
        self.result = mix.analyse_mix(cm.load_rows(str(FIXTURE)))

    def test_grid_has_gaps(self):
        gaps = [cell for line in self.result["grid"]["cells"] for cell in line.values() if cell["ads"] == 0]
        self.assertTrue(gaps)
        self.assertIn("gap", mix.render(self.result))

    def test_nothing_unclassified_in_the_fixture(self):
        self.assertEqual(self.result["unclassified"]["count"], 0)
        self.assertIn("unclassified: 0", mix.render(self.result))

    def test_promo_and_bau_are_separate_rows(self):
        types = {r["ad_type"] for r in self.result["by_type"]}
        self.assertTrue({"bau", "promo", "launch"} <= types)

    def test_spend_totals_agree_across_tables(self):
        total = sum(r["spend"] for r in self.result["by_format"])
        self.assertAlmostEqual(total, sum(r["spend"] for r in self.result["by_type"]))
        self.assertAlmostEqual(total, sum(r["spend"] for r in self.result["by_concept"]))

    def test_funnel_stage_absent_is_stated(self):
        self.assertIn("funnel stage", mix.render(self.result).lower())

    def test_funnel_stage_view_with_pattern(self):
        rows = cm.load_rows([
            row("a | static | house | bau | p | polished | cold"),
            row("b | static | house | bau | p | polished | warm"),
        ])
        pattern = ["concept", "format", "creator", "ad_type", "product", "tone", "funnel_stage"]
        result = mix.analyse_mix(rows, pattern=pattern)
        self.assertEqual({r["stage"] for r in result["by_stage"]}, {"cold", "warm"})


if __name__ == "__main__":
    unittest.main()
