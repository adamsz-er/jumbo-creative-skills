import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "ad-transcript" / "scripts"
sys.path.insert(0, str(SCRIPT))

import beats  # noqa: E402

SRT = """1
00:00:00,000 --> 00:00:02,800
Your tent leaks and you only find out at night.

2
00:00:02,900 --> 00:00:08,000
Most shells fail at the seams because they are taped once and forgotten.

3
00:00:08,000 --> 00:00:14,000
The Acme rain shell is welded, not taped, and I've tested it through three weeks of storms.

4
00:00:14,000 --> 00:00:18,000
Right now it is 9% off with code TRAIL.

5
00:00:18,000 --> 00:00:20,000
Tap shop now.
"""

PLAIN_NO_CTA = "Your tent leaks. Most shells fail at the seams. The rain shell is welded instead."


def labels(result):
    return [s["beat"] for s in result["sentences"]]


class BeatsTest(unittest.TestCase):
    def test_srt_timestamps_are_parsed(self):
        cues = beats.parse_transcript(SRT)
        self.assertEqual(len(cues), 5)
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertAlmostEqual(cues[2]["start"], 8.0)

    def test_vtt_is_parsed(self):
        vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello there.\n\n00:00:02.000 --> 00:00:04.000\nShop now.\n"
        cues = beats.parse_transcript(vtt)
        self.assertEqual([c["text"] for c in cues], ["Hello there.", "Shop now."])
        self.assertAlmostEqual(cues[1]["start"], 2.0)

    def test_hook_and_cta_are_labelled(self):
        result = beats.analyse(SRT, products=("rain shell",))
        found = labels(result)
        self.assertEqual(found[0], "hook")
        self.assertEqual(found[-1], "cta")
        self.assertNotIn("CTA missing", result["flags"])

    def test_offer_and_proof_are_labelled(self):
        result = beats.analyse(SRT, products=("rain shell",))
        found = labels(result)
        self.assertIn("offer", found)
        self.assertIn("proof", found)

    def test_time_to_product_and_cta(self):
        result = beats.analyse(SRT, products=("rain shell",))
        self.assertAlmostEqual(result["time_to_product"], 8.0)
        self.assertAlmostEqual(result["time_to_cta"], 18.0)
        self.assertTrue(any(f.startswith("no product in the first 3 s") for f in result["flags"]))

    def test_words_per_second_when_timed(self):
        result = beats.analyse(SRT, products=("rain shell",))
        self.assertGreater(result["words_per_second"], 0)

    def test_untimed_text_has_no_timing(self):
        result = beats.analyse(PLAIN_NO_CTA)
        self.assertFalse(result["timed"])
        self.assertIsNone(result["time_to_cta"])
        self.assertIsNone(result["words_per_second"])
        self.assertEqual(labels(result)[0], "hook")

    def test_cta_missing_is_flagged(self):
        result = beats.analyse(PLAIN_NO_CTA)
        self.assertIn("CTA missing", result["flags"])
        self.assertIn("cta", result["missing"])

    def test_two_ctas_are_flagged(self):
        result = beats.analyse("Your tent leaks. Shop now. Then tap the link below.")
        self.assertIn("more than one CTA", result["flags"])

    def test_claim_word_is_flagged(self):
        result = beats.analyse("It is guaranteed to keep you dry. Shop now.")
        self.assertTrue(any("guaranteed" in f for f in result["flags"]))

    def test_clean_script_has_no_claim_flag(self):
        result = beats.analyse("It kept me dry for three weeks. Shop now.")
        self.assertFalse(any(f.startswith("claim") for f in result["flags"]))

    def test_hash_note_lines_are_not_beats(self):
        result = beats.analyse("# Illustrative script: not real.\nYour tent leaks. Shop now.")
        self.assertEqual(labels(result)[0], "hook")
        self.assertNotIn("Illustrative", " ".join(s["text"] for s in result["sentences"]))

    def test_cli_prints_table_and_json(self):
        path = ROOT / "examples" / "acme" / "transcript.txt"
        if not path.exists():
            self.skipTest("example transcript not written yet")
        for extra in ([], ["--json"]):
            out = subprocess.run([sys.executable, str(SCRIPT / "beats.py"), str(path)] + extra,
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("hook", out.stdout)


if __name__ == "__main__":
    unittest.main()
