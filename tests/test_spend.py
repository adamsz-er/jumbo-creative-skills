import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "spend-analysis" / "scripts"
VERDICTS = ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"
sys.path.insert(0, str(SCRIPTS))

import creative_metrics as cm  # noqa: E402
import spend  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
SCRIPT = SCRIPTS / "spend.py"


def run_cli(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True)


def verdict(ad, spend_, verdict_id, confidence="Confident", sentence="s"):
    return {"ad": ad, "spend": spend_, "verdict_id": verdict_id, "verdict": verdict_id, "confidence": confidence,
            "sentence": sentence}


def small_rows(days=4):
    rows = []
    for ad, daily, conv in (("a1", 100, 5), ("a2", 200, 8), ("a3", 300, 6), ("a4", 50, 0)):
        for d in range(days):
            rows.append({"Day": "2026-04-%02d" % (d + 1), "Ad name": "name-" + ad, "Ad ID": ad,
                         "Amount spent (USD)": daily, "Impressions": 5000, "Link clicks": 100,
                         "Purchases": conv, "Purchase conversion value": conv * 40})
    return rows


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.ads = cm.aggregate_by_ad(cls.rows)
        out = subprocess.run([sys.executable, "-I", str(VERDICTS), str(FIXTURE), "--json"],
                             capture_output=True, text=True, check=True).stdout
        cls.verdicts = json.loads(out)
        cls.plain = spend.build_spend(cls.rows, path=str(FIXTURE))
        cls.full = spend.build_spend(cls.rows, verdicts=cls.verdicts, path=str(FIXTURE))

    def test_totals_equal_the_csv_spend_column(self):
        with open(FIXTURE, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            column = next(c for c in reader.fieldnames if c.lower().startswith("amount spent"))
            expected = sum(float(r[column]) for r in reader)
        self.assertAlmostEqual(self.plain["totals"]["spend"], expected, places=4)
        self.assertEqual(self.plain["currency"], "USD")
        self.assertEqual(self.plain["window"]["days"], 30)

    def test_pareto_is_the_fewest_ads_holding_the_share(self):
        p = self.plain["concentration"]["spend_pareto"]
        shares = cm.spend_share(self.ads)
        self.assertGreaterEqual(shares[p["ads"] - 1]["cumulative"], 80)
        self.assertLess(shares[p["ads"] - 2]["cumulative"], 80)
        value = self.plain["concentration"]["value_pareto"]
        self.assertIsNotNone(value["ads"])

    def test_top_n_matches_concentration(self):
        self.assertEqual(self.plain["concentration"]["top_n_spend_share"], cm.concentration(self.ads, 3))
        again = spend.build_spend(self.rows, top_n=5)
        self.assertEqual(again["concentration"]["top_n_spend_share"], cm.concentration(self.ads, 5))

    def test_dimension_shares_sum_to_100_and_account_is_100(self):
        for field, rows in self.full["dimensions"].items():
            self.assertAlmostEqual(sum(r["spend_share"] for r in rows), 100, places=6, msg=field)
            spends = [r["spend"] for r in rows]
            self.assertEqual(spends, sorted(spends, reverse=True))
        everyone = spend._group_row("all", self.ads, self.plain["totals"]["spend"], spend._pooled(self.ads))
        self.assertAlmostEqual(everyone["roas_vs_account"], 100)

    def test_age_bands_partition_all_ads(self):
        bands = self.plain["dimensions"]["age_band"]
        self.assertEqual(sum(b["ads"] for b in bands), len(self.ads))
        self.assertEqual(spend.age_labels([9, 18, 36]), ["under 9 days", "9-17 days", "18-35 days", "36+ days"])
        self.assertEqual(self.plain["age_note"], spend.AGE_NOTE)

    def test_verdict_lists_match_verdict_ids(self):
        by_id = {a["ad"]: a["verdict_id"] for a in self.verdicts["ads"]}
        for group in ("scale", "keep"):
            listed = {e["ad"] for e in self.full["room"][group]}
            self.assertEqual(listed, {ad for ad, v in by_id.items() if v == group})
        self.assertTrue(all(e["room"] for e in self.full["room"]["scale"]))
        self.assertIn("verdict_group", self.full["dimensions"])

    def test_room_reads_frequency_against_format_median(self):
        reads = {e["room"].split(":")[0] for e in self.full["room"]["scale"] + self.full["room"]["keep"]}
        self.assertTrue(reads <= {"room", "watch", "frequency between the format median and the top quarter of its format"})

    def test_no_verdicts_gives_the_hint_and_no_moves(self):
        self.assertIsNone(self.plain["budget"])
        self.assertEqual(self.plain["budget_note"], spend.NEEDS_VERDICTS)
        self.assertIn("Budget moves need verdicts", spend.render(self.plain))
        self.assertNotIn("verdict_group", self.plain["dimensions"])

    def test_zero_purchase_ad_gives_na_cpa_never_zero(self):
        row = spend._group_row("x", [a for a in self.ads if not a["conversions"]], 1, spend._pooled(self.ads))
        self.assertIsNone(row["cpa"])
        self.assertIn("zero conversions", row["cpa_note"])
        text = spend.render(self.plain)
        self.assertIn("cpa n/a (zero conversions)", text)

    def test_text_leads_with_three_lines(self):
        lines = spend.render(self.full).splitlines()
        self.assertTrue(lines[0].startswith("Where the money goes"))
        self.assertTrue(lines[1].startswith("Spend on ads judged pause"))
        self.assertTrue(lines[2].startswith("Top move"))
        self.assertEqual(lines[3], "")


class MovesTest(unittest.TestCase):
    def setUp(self):
        self.rows = cm.load_rows(small_rows())

    def build(self, entries):
        return spend.build_spend(self.rows, verdicts={"ads": entries})

    def test_move_a_splits_in_proportion_and_takes_the_lower_confidence(self):
        result = self.build([verdict("a1", 400, "pause_never_worked", "Confident", "Stop it."),
                             verdict("a2", 800, "scale", "Confident"),
                             verdict("a3", 1200, "scale", "Early read")])
        move = result["budget"]["moves"][0]
        self.assertEqual(move["from"], "a1")
        self.assertAlmostEqual(move["amount_per_day"], 100)
        amounts = {t["ad"]: t["amount_per_day"] for t in move["to"]}
        self.assertAlmostEqual(amounts["a2"], 40)
        self.assertAlmostEqual(amounts["a3"], 60)
        self.assertEqual(move["confidence"], "Early read")
        self.assertEqual(move["evidence"][0], "Stop it.")
        self.assertEqual(len(move["evidence"]), 3)
        self.assertTrue(result["pause"]["ads"][0]["never_worked"])
        self.assertIn("Top move: shift", result["headline"][2])
        self.assertIn(spend.STEP_ADVICE, spend.render(result))

    def test_source_confidence_can_be_the_lower_one(self):
        result = self.build([verdict("a1", 400, "pause_fatigued", "Can't judge yet"),
                             verdict("a2", 800, "scale", "Confident")])
        self.assertEqual(result["budget"]["moves"][0]["confidence"], "Can't judge yet")
        self.assertFalse(result["pause"]["ads"][0]["never_worked"])

    def test_a_missing_confidence_renders_as_not_available(self):
        result = self.build([verdict("a1", 400, "pause_fatigued", None),
                             verdict("a2", 800, "scale", "Confident")])
        text = spend.render(result)
        self.assertNotIn("[None]", text)
        self.assertIn("[confidence n/a]", text)

    def test_no_scale_ad_holds_the_money_back(self):
        result = self.build([verdict("a1", 400, "pause_never_worked"), verdict("a2", 800, "keep")])
        self.assertEqual(result["budget"]["moves"], [])
        self.assertEqual(result["budget"]["note"], spend.NO_SCALE_AD)
        self.assertIn(spend.NO_SCALE_AD, result["headline"][2])

    def test_no_pause_ad_means_no_move_supported(self):
        result = self.build([verdict("a2", 800, "scale")])
        self.assertEqual(result["budget"]["note"], spend.NO_MOVE)

    def test_check_and_iterate_ads_are_held_not_moved(self):
        result = self.build([verdict("a1", 400, "check_mixed", sentence="Look first."), verdict("a2", 800, "iterate"),
                             verdict("a3", 1200, "scale")])
        actions = {h["ad"]: h["action"] for h in result["budget"]["held"]}
        self.assertEqual(actions["a1"], "check before moving money")
        self.assertEqual(actions["a2"], "refresh the creative before changing its budget")
        self.assertEqual(result["budget"]["moves"], [])

    def test_pause_spend_and_per_day_rate(self):
        result = self.build([verdict("a1", 400, "pause_fatigued"), verdict("a3", 1200, "scale")])
        self.assertAlmostEqual(result["pause"]["spend"], 400)
        self.assertAlmostEqual(result["pause"]["spend_share"], 400 / 2600 * 100)
        self.assertAlmostEqual(result["pause"]["per_day"], 100)

    def test_mismatched_verdicts_raise(self):
        with self.assertRaises(ValueError):
            self.build([verdict("zzz", 1, "scale")])

    def test_missing_reach_gives_na_frequency(self):
        result = self.build([verdict("a2", 800, "scale")])
        self.assertEqual(result["room"]["scale"][0]["room"], "n/a (missing reach)")
        self.assertIsNone(result["room"]["scale"][0]["frequency"])

    def test_no_purchases_gives_null_cpa_in_json(self):
        rows = cm.load_rows([r for r in small_rows() if r["Ad ID"] == "a4"])
        result = spend.build_spend(rows)
        self.assertIsNone(result["totals"]["cpa"])
        self.assertEqual(result["totals"]["cpa_note"], "zero conversions")
        self.assertIn("cpa n/a (zero conversions)", spend.render(result))

    def test_missing_conversions_column_gives_na_text(self):
        rows = cm.load_rows([{k: v for k, v in r.items() if k not in ("Purchases", "Purchase conversion value")}
                             for r in small_rows()])
        result = spend.build_spend(rows)
        self.assertIsNone(result["totals"]["cpa"])
        self.assertIn("missing conversions", result["totals"]["cpa_note"])
        self.assertIn("n/a (missing conversions)", spend.render(result))


class AgeBandsTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(spend.parse_age_bands("9,18,36"), [9, 18, 36])
        for bad in ("", "a,b", "5,5", "9,3", "0,4"):
            with self.assertRaises(ValueError, msg=bad):
                spend.parse_age_bands(bad)

    def test_band_edges(self):
        labels = spend.age_labels([9, 18, 36])
        edges = [9, 18, 36]
        self.assertEqual([spend._age_band(a, edges, labels) for a in (0, 8, 9, 17, 18, 35, 36, 90)],
                         ["under 9 days", "under 9 days", "9-17 days", "9-17 days", "18-35 days", "18-35 days", "36+ days", "36+ days"])
        self.assertEqual(spend._age_band(None, edges, labels), "age unknown")


class CliTest(unittest.TestCase):
    def test_text_and_json_exit_zero(self):
        out = run_cli(str(FIXTURE))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Budget moves need verdicts", out.stdout)
        data = json.loads(run_cli(str(FIXTURE), "--json", "--pareto-share", "75").stdout)
        self.assertEqual(data["settings"]["pareto_share"], 75)
        self.assertEqual(data["settings"]["age_bands"], [9, 18, 36])

    def test_with_verdicts_file(self):
        verdicts = subprocess.run([sys.executable, "-I", str(VERDICTS), str(FIXTURE), "--json"],
                                  capture_output=True, text=True, check=True).stdout
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verdicts.json"
            path.write_text(verdicts, encoding="utf-8")
            out = run_cli(str(FIXTURE), "--verdicts", str(path))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Room to scale", out.stdout)

    def test_mismatched_verdicts_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verdicts.json"
            path.write_text(json.dumps({"ads": [verdict("nope", 1, "scale")]}), encoding="utf-8")
            out = run_cli(str(FIXTURE), "--verdicts", str(path))
            self.assertEqual(out.returncode, 2)
            self.assertIn("matches", out.stderr)
            self.assertNotIn("Traceback", out.stderr)

    def test_bad_verdicts_file_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verdicts.json"
            path.write_text("[1]", encoding="utf-8")
            self.assertEqual(run_cli(str(FIXTURE), "--verdicts", str(path)).returncode, 2)

    def test_header_only_csv_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.csv"
            path.write_text("Day,Ad name,Ad ID,Amount spent (USD),Impressions\n", encoding="utf-8")
            out = run_cli(str(path))
            self.assertEqual(out.returncode, 2)
            self.assertNotIn("Traceback", out.stderr)
            self.assertTrue(out.stderr.strip())

    def test_bad_age_bands_exit_2(self):
        out = run_cli(str(FIXTURE), "--age-bands", "9,x")
        self.assertEqual(out.returncode, 2)
        self.assertIn("--age-bands", out.stderr)

    def test_bad_pareto_share_exit_2(self):
        self.assertEqual(run_cli(str(FIXTURE), "--pareto-share", "0").returncode, 2)


if __name__ == "__main__":
    unittest.main()
