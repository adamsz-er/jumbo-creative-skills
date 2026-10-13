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


class ProvenSpendTest(unittest.TestCase):
    def rows(self):
        rows = []
        names = [("alpha", "static"), ("bravo", "static"), ("charlie", "static"), ("delta", "static"), ("echo", "static"),
                 ("foxtrot", "carousel"), ("golf", "carousel"), ("hotel", "carousel"), ("india", "carousel")]
        for i, (concept, fmt) in enumerate(names):
            for variant in range(4):
                name = "%s | %s | house | bau | p%d | polished | 2026-03-01" % (concept, fmt, variant)
                rows.append(dict(row(name, spend=100.0),
                                 **{"Purchases": 4, "Purchases conversion value": 100 + 20 * i}))
        # a concept with negligible spend and the best return in the account
        rows.append(dict(row("zulu | video | house | bau | p | polished | 2026-03-01", spend=2.0),
                         **{"Purchases": 1, "Purchases conversion value": 900}))
        return rows

    def test_negligible_spend_concept_never_leads_the_gap_list(self):
        result = mix.analyse_mix(cm.load_rows(self.rows()))
        self.assertIn("zulu", result["top_concepts"])
        self.assertIn("zulu", result["unproven"]["concepts"])
        self.assertNotIn("zulu", [g["concept"] for g in result["gaps"]])
        self.assertTrue(result["gaps"])
        self.assertEqual(result["gaps"][0]["concept"] != "zulu", True)

    def test_floor_is_three_times_median_ad_spend_and_settable(self):
        result = mix.analyse_mix(cm.load_rows(self.rows()))
        self.assertAlmostEqual(result["min_proven_spend"], 300.0)
        low = mix.analyse_mix(cm.load_rows(self.rows()), min_proven_spend=1.0)
        self.assertEqual(low["unproven"]["concepts"], [])
        self.assertIn("zulu", [g["concept"] for g in low["gaps"]])
        self.assertIn("--min-proven-spend", mix.render(result))


class WeakConceptGapTest(unittest.TestCase):
    """A gap ports a concept into a format: the account's weakest concepts never lead one."""

    def setUp(self):
        self.result = mix.analyse_mix(cm.load_rows(str(FIXTURE)))

    def bau_roas(self):
        rows = cm.load_rows(str(FIXTURE))
        ads = [a for a in cm.aggregate_by_ad(rows) if a.get("ad_type") == "bau"]
        family = {c: f for c, f in mix.concept_families([a["concept"] for a in ads]).items()}
        pooled = {}
        for name in set(family.values()):
            members = [a for a in ads if family[a["concept"]] == name]
            pooled[name] = sum(a["conversion_value"] for a in members) / sum(a["spend"] for a in members)
        return pooled

    def test_bottom_quartile_concepts_are_left_out_of_the_gaps_and_listed(self):
        left_out = {g["concept"] for g in self.result["gaps_left_out"]}
        self.assertIn("before-after", left_out)
        self.assertFalse(left_out & {g["concept"] for g in self.result["gaps"]})
        roas = self.bau_roas()
        import statistics
        p25 = statistics.quantiles(list(roas.values()), n=4, method="inclusive")[0]
        with_cell = {g["concept"] for g in self.result["gaps"]} | left_out
        self.assertEqual(left_out, {c for c, v in roas.items() if v < p25} & with_cell)
        text = mix.render(self.result)
        self.assertIn("Left out of the gaps", text)
        self.assertIn("before-after", text.split("Left out of the gaps")[1].splitlines()[0])

    def test_equal_gaps_are_ordered_by_the_concepts_own_return_not_by_name(self):
        gaps = self.result["gaps"]
        self.assertNotEqual("before-after", gaps[0]["concept"])
        for a, b in zip(gaps, gaps[1:]):
            if (a["strength"], a["ads"]) == (b["strength"], b["ads"]):
                self.assertGreaterEqual(a["concept_roas"] if a["concept_roas"] is not None else -1,
                                        b["concept_roas"] if b["concept_roas"] is not None else -1, (a, b))



class GapEdgeTest(unittest.TestCase):
    def rows(self, returns):
        out = []
        for i, value in enumerate(returns):
            fmt = "static" if i % 2 else "carousel"
            out.append(dict(row("c%02d | %s | house | bau | p | polished | 2026-03-01" % (i, fmt), spend=100.0),
                            **{"Purchases conversion value": value}))
        return cm.load_rows(out)

    def test_tied_returns_leave_no_concept_out(self):
        result = mix.analyse_mix(self.rows([300] * 9), min_proven_spend=1.0)
        self.assertEqual([], result["gaps_left_out"])

    def test_a_gap_without_a_regular_price_return_says_so(self):
        names = []
        for i, fmt in enumerate(("f1", "f2", "f3", "f4", "f5")):
            for j in range(2):
                names.append(("c%d%d | %s | house | bau | p | polished | 2026-03-01" % (i, j, fmt), 200 + 100 * i + 10 * j))
        names.append(("launchy | f1 | house | launch | p | polished | 2026-03-01", 300))
        rows = cm.load_rows([dict(row(n, spend=100.0), **{"Purchases conversion value": v}) for n, v in names])
        result = mix.analyse_mix(rows, min_proven_spend=1.0)
        unknown = [g for g in result["gaps"] if g["concept"] == "launchy"]
        self.assertTrue(unknown, result["gaps"])
        self.assertIsNone(unknown[0]["concept_roas"])
        judged = [n for n, g in enumerate(result["gaps"]) if g["concept_roas"] is not None]
        unjudged = [n for n, g in enumerate(result["gaps"]) if g["concept_roas"] is None]
        self.assertTrue(judged and unjudged)
        self.assertLess(max(judged), min(unjudged))
        self.assertTrue(any(g["strength"] < max(j["strength"] for j in result["gaps"]) for g in result["gaps"] if g["concept_roas"] is not None))
        # render just the unjudged gap to read its line
        line = next(l for l in mix.render(dict(result, gaps=unknown)).splitlines() if l.strip().startswith("launchy in"))
        self.assertIn("no regular-price return to judge yet", line)


if __name__ == "__main__":
    unittest.main()
