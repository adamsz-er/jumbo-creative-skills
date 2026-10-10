import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "competitor-scan" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scan  # noqa: E402

SCRIPT = SCRIPTS / "scan.py"
FIXTURE = ROOT / "tests" / "fixtures" / "competitor_ads.csv"
AS_OF = dt.date(2026, 3, 30)
EVIDENCE = {"angles": [
    {"concept": "comparison", "label": "losing", "ads": 3, "spend_share": 0.1},
    {"concept": "problem-first", "label": "winning", "ads": 4, "spend_share": 0.4},
]}
TOP_KEYS = ["source", "as_of", "advertisers", "ads", "skipped_urls", "no_text", "clusters", "crowded", "open_ground",
            "worth_testing", "not_to_chase", "rows", "settings"]


def run_fixture(evidence=None, keep_text=False, long_days=36, crowded_share=60.0):
    records, skipped = scan.canonical_rows(scan.read_input(str(FIXTURE)))
    return scan.build_scan(records, skipped, AS_OF, long_days, crowded_share, evidence=evidence, keep_text=keep_text)


def labels(items):
    return [i["label"] for i in items]


def cli(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True)


class KeywordRuleTest(unittest.TestCase):
    def test_each_angle(self):
        cases = {
            "problem": "We know the struggle.", "proof": "Rated by customers.", "offer": "Big sale now.",
            "comparison": "Better than the usual.", "story": "Why we started.", "education": "Tips for the trail.",
            "identity": "Made for night owls.", "feature": "Waterproof shell.", "urgency": "Hurry, ends soon.",
        }
        for angle, text in cases.items():
            self.assertIn(angle, scan.find_angles(text), angle)

    def test_an_ad_can_have_several_angles_or_none(self):
        self.assertEqual({"proof", "feature"}, set(scan.find_angles("Tested and waterproof.")))
        self.assertEqual(["unclassified"], scan.find_angles("Hello there."))

    def test_percent_sign_keyword_needs_the_phrase(self):
        self.assertIn("offer", scan.find_angles("Get 9% off today."))
        self.assertNotIn("offer", scan.find_angles("Get 9 percent more."))

    def test_each_hook_type(self):
        cases = {
            "question": "Where does the trail end?", "number": "9 tips for the trail.",
            "negative": "Avoid soggy boots.", "how-to": "How we pack light.", "testimonial": "\"Loved it,\" said Sam.",
            "pov": "POV: you wake up warm.", "claim": "A tent that packs small.",
        }
        for expected, text in cases.items():
            self.assertEqual(expected, scan.hook_type(text), expected)

    def test_hook_reads_only_the_first_sentence_and_when_you_is_pov(self):
        self.assertEqual("claim", scan.hook_type("A tent that packs small. Never settle."))
        self.assertEqual("pov", scan.hook_type("When you reach the summit, you smile."))
        self.assertEqual("claim", scan.hook_type("A tent that packs small and light and tough and bright 9 times."))

    def test_each_offer_type(self):
        cases = {
            "percent off": "Take 9% off.", "money off": "Take $9 off.", "free shipping": "Free shipping today.",
            "gift with purchase": "A free gift for you.", "bundle": "Grab the camp kit.",
            "tiered": "Spend more save more.", "none": "A tent that packs small.",
        }
        for expected, text in cases.items():
            self.assertEqual(expected, scan.offer_type(text), expected)

    def test_format_is_normalised(self):
        self.assertEqual("video", scan.normalise_format("Video"))
        self.assertEqual("image", scan.normalise_format("Static image"))
        self.assertEqual("carousel", scan.normalise_format("CAROUSEL"))
        self.assertEqual("other", scan.normalise_format("collection"))
        self.assertEqual("unknown", scan.normalise_format(""))

    def test_dates_iso_and_day_first(self):
        self.assertEqual(dt.date(2026, 3, 25), scan.parse_date("25/03/2026"))
        self.assertEqual(dt.date(2026, 3, 5), scan.parse_date("2026-03-05"))
        self.assertIsNone(scan.parse_date("last week"))


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.result = run_fixture()

    def test_json_keys_are_exactly_the_contract(self):
        self.assertEqual(TOP_KEYS, list(self.result))
        self.assertEqual(["angle", "hook_type", "offer", "format"], list(self.result["clusters"]))
        self.assertEqual("Meta Ad Library (public)", self.result["source"])
        self.assertEqual("2026-03-30", self.result["as_of"])

    def test_counts(self):
        self.assertEqual((6, 18, 0), (self.result["advertisers"], self.result["ads"], self.result["no_text"]))

    def test_fixture_covers_every_rule(self):
        for dim, expected in (("angle", set(scan.ANGLE_KEYWORDS)),
                              ("hook_type", {"question", "number", "negative", "how-to", "testimonial", "pov", "claim"}),
                              ("offer", {"percent off", "money off", "free shipping", "gift with purchase", "bundle",
                                         "tiered", "none"}),
                              ("format", {"image", "video", "carousel"})):
            self.assertTrue(expected <= {c["value"] for c in self.result["clusters"][dim]}, dim)

    def test_cluster_fields(self):
        offer = next(c for c in self.result["clusters"]["angle"] if c["value"] == "offer")
        self.assertEqual((7, 6, 1), (offer["ads"], offer["advertisers"], offer["long_running"]))
        self.assertEqual(6, len(offer["advertiser_names"]))
        self.assertEqual(round(100.0 * 7 / 18, 1), offer["share"])

    def test_crowded_and_open_ground(self):
        self.assertEqual(["offer"], labels(self.result["crowded"]))
        self.assertEqual({"education", "problem", "proof", "story", "identity"}, set(labels(self.result["open_ground"])))
        self.assertEqual(["advertisers", "brand", "label", "long_running", "why"], sorted(self.result["crowded"][0]))

    def test_crowded_share_is_a_setting(self):
        self.assertEqual(["offer"], labels(run_fixture(crowded_share=100.0)["crowded"]))
        self.assertIn("comparison", labels(run_fixture(crowded_share=33.0)["crowded"]))

    def test_without_evidence_brand_fields_are_na_and_worth_testing_uses_rivals_only(self):
        for key in ("crowded", "open_ground", "worth_testing", "not_to_chase"):
            for entry in self.result[key]:
                self.assertTrue(entry["brand"].startswith("n/a (no evidence file"))
        self.assertEqual([], self.result["not_to_chase"])
        self.assertEqual({"comparison", "education", "feature", "offer", "problem", "proof", "story"},
                         set(labels(self.result["worth_testing"])))

    def test_evidence_moves_losing_to_not_to_chase_and_winning_open_ground_to_worth_testing(self):
        result = run_fixture(EVIDENCE)
        self.assertEqual(["comparison"], labels(result["not_to_chase"]))
        self.assertIn("has not worked for you", result["not_to_chase"][0]["why"])
        self.assertEqual("comparison: losing", result["not_to_chase"][0]["brand"])
        worth = result["worth_testing"]
        self.assertNotIn("comparison", labels(worth))
        self.assertEqual(1, labels(worth).count("problem"))
        problem = next(w for w in worth if w["label"] == "problem")
        self.assertIn("your own ads win", problem["why"])
        self.assertEqual("problem-first: winning", problem["brand"])
        self.assertIn("education", labels(worth))
        self.assertEqual("not tried", next(w for w in worth if w["label"] == "education")["brand"])

    def test_longevity_with_fixed_as_of(self):
        rows = self.result["rows"]
        self.assertEqual((77, True), (rows[0]["days_running"], rows[0]["long_running"]))
        self.assertEqual((28, False), (rows[1]["days_running"], rows[1]["long_running"]))
        self.assertEqual(5, rows[17]["days_running"])
        self.assertEqual(7, sum(1 for r in rows if r["long_running"]))

    def test_long_days_setting(self):
        self.assertEqual(9, sum(1 for r in run_fixture(long_days=28)["rows"] if r["long_running"]))

    def test_rows_carry_no_text_unless_asked(self):
        self.assertNotIn("ad_text", self.result["rows"][0])
        self.assertNotIn("headline", self.result["rows"][0])
        kept = run_fixture(keep_text=True)["rows"][0]
        self.assertTrue(kept["ad_text"].startswith("Tired of wet socks"))
        self.assertEqual("Dry feet all day", kept["headline"])

    def test_urls_are_skipped_counted_and_never_output(self):
        self.assertEqual(18, self.result["skipped_urls"])
        self.assertNotIn("http", json.dumps(run_fixture(EVIDENCE, keep_text=True)))
        self.assertIn("Removed 18 URLs from the text; images and videos are not downloaded or kept.", scan.render(self.result))

    def test_text_leads_with_three_lines(self):
        lines = scan.render(self.result).splitlines()
        self.assertTrue(lines[0].startswith("Most crowded angle: offer"))
        self.assertTrue(lines[1].startswith("Best open ground:"))
        self.assertTrue(lines[2].startswith("Top worth testing:"))
        self.assertEqual("", lines[3])


class EdgeCaseTest(unittest.TestCase):
    def build(self, raw, **kwargs):
        records, skipped = scan.canonical_rows(raw)
        return scan.build_scan(records, skipped, AS_OF, 36, 60.0, **kwargs)

    def test_missing_started_is_na_text(self):
        result = self.build([{"advertiser": "Rival A", "ad_text": "Big sale now."}])
        row = result["rows"][0]
        self.assertIsNone(row["days_running"])
        self.assertIsNone(row["long_running"])
        self.assertEqual("n/a (missing started date)", row["days_running_note"])
        self.assertIn("n/a (missing started date)", scan.render(result))

    def test_empty_text_row_is_kept_for_format_and_longevity(self):
        result = self.build([{"advertiser": "Rival A", "ad_text": "", "format": "video", "started": "2026-01-01"},
                             {"advertiser": "Rival B", "ad_text": "Big sale now.", "format": "image"}])
        self.assertEqual(1, result["no_text"])
        self.assertEqual("n/a (no text)", result["rows"][0]["hook_type"])
        self.assertTrue(result["rows"][0]["long_running"])
        self.assertEqual({"video", "image"}, {c["value"] for c in result["clusters"]["format"]})
        self.assertEqual(["offer"], [c["value"] for c in result["clusters"]["angle"]])

    def test_header_aliases_and_a_url_in_text(self):
        result = self.build([{"Advertiser": "Rival A", "Primary Text": "https://example.com/x", "Media-Type": "Reel",
                              "Start Date": "01/02/2026"}])
        self.assertEqual(1, result["skipped_urls"])
        self.assertEqual(1, result["no_text"])
        self.assertEqual(("video", 57), (result["rows"][0]["format"], result["rows"][0]["days_running"]))

    def test_urls_inside_text_are_stripped_and_each_one_counted(self):
        raw = [{"advertiser": "Rival A", "ad_text": "Shop now at https://example.com/sale today www.example.com"}]
        records, removed = scan.canonical_rows(raw)
        self.assertEqual(2, removed)
        self.assertEqual("Shop now at today", records[0]["ad_text"])
        result = self.build(raw, keep_text=True)
        self.assertEqual(2, result["skipped_urls"])
        self.assertNotIn("example.com", json.dumps(result))
        self.assertNotIn("example.com", scan.render(result))
        self.assertIn("Removed 2 URLs from the text", scan.render(result))

    def test_started_after_as_of_is_na_not_negative(self):
        row = self.build([{"advertiser": "Rival A", "ad_text": "Big sale.", "started": "2026-04-30"}])["rows"][0]
        self.assertIsNone(row["days_running"])
        self.assertIn("after the as-of date", row["days_running_note"])

    def test_missing_advertiser_column_raises(self):
        with self.assertRaisesRegex(ValueError, "advertiser"):
            scan.canonical_rows([{"ad_text": "Big sale."}])

    def test_missing_text_column_raises(self):
        with self.assertRaisesRegex(ValueError, "ad_text"):
            scan.canonical_rows([{"advertiser": "Rival A"}])

    def test_blank_advertiser_and_empty_input_raise(self):
        with self.assertRaisesRegex(ValueError, "row 1 has no advertiser"):
            scan.canonical_rows([{"advertiser": "", "ad_text": "Big sale."}])
        with self.assertRaisesRegex(ValueError, "no ads"):
            scan.canonical_rows([])

    def test_bad_evidence_raises(self):
        with self.assertRaisesRegex(ValueError, "angles"):
            self.build([{"advertiser": "Rival A", "ad_text": "Big sale."}], evidence={"ads": []})

    def test_concept_names_map_to_angles(self):
        for concept, angle in (("social-proof", "proof"), ("founder-story", "story"), ("sale-countdown", "offer"),
                               ("behind-the-scenes", "story"), ("reviews", "proof"), ("gift-bundle", "offer"),
                               ("percent-off", "offer"), ("problem-first", "problem")):
            self.assertIn(angle, scan.concept_angles(concept), concept)
        self.assertEqual([], scan.concept_angles("lifestyle"))

    def test_a_losing_angle_that_also_wins_is_not_to_chase_free(self):
        evidence = {"angles": [{"concept": "sale-countdown", "label": "losing"}, {"concept": "gift-bundle", "label": "winning"}]}
        result = self.build([{"advertiser": "Rival A", "ad_text": "Big sale."}], evidence=evidence)
        self.assertEqual([], result["not_to_chase"])

    def test_line_breaks_inside_quoted_ad_text_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            path.write_text('advertiser,ad_text\nRival A,"Tired of leaks?\nOur jacket is waterproof."\n'
                            'Rival B,"Line one\u2028Save on every tent today."\n', encoding="utf-8")
            records, _ = scan.canonical_rows(scan.read_input(str(path)))
        self.assertEqual(2, len(records))
        self.assertEqual("Tired of leaks?\nOur jacket is waterproof.", records[0]["ad_text"])
        self.assertEqual("question", scan.hook_type(records[0]["ad_text"]))
        self.assertIn("\u2028", records[1]["ad_text"])

    def test_json_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.json"
            path.write_text(json.dumps({"ads": [{"advertiser": "Rival A", "body": "Big sale."}]}))
            records, _ = scan.canonical_rows(scan.read_input(str(path)))
        self.assertEqual("Big sale.", records[0]["ad_text"])


class CliTest(unittest.TestCase):
    def test_json_output_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence.json"
            evidence.write_text(json.dumps(EVIDENCE))
            proc = cli(str(FIXTURE), "--as-of", "2026-03-30", "--evidence", str(evidence), "--json", "--source", "Test")
        self.assertEqual(0, proc.returncode, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(TOP_KEYS, list(data))
        self.assertEqual("Test", data["source"])
        self.assertEqual(["comparison"], labels(data["not_to_chase"]))
        self.assertEqual(36, data["settings"]["long_days"])

    def test_text_output_exit_0(self):
        proc = cli(str(FIXTURE), "--as-of", "2026-03-30")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(proc.stdout.startswith("Most crowded angle:"))

    def test_missing_advertiser_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            path.write_text("ad_text,format\nBig sale.,image\n")
            proc = cli(str(path))
        self.assertEqual(2, proc.returncode)
        self.assertIn("advertiser", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_bad_inputs_exit_2(self):
        self.assertEqual(2, cli("no-such-file.csv").returncode)
        self.assertEqual(2, cli(str(FIXTURE), "--as-of", "yesterday").returncode)
        self.assertEqual(2, cli(str(FIXTURE), "--evidence", str(FIXTURE)).returncode)
        self.assertEqual(2, cli(str(FIXTURE), "--long-days", "0").returncode)


if __name__ == "__main__":
    unittest.main()
