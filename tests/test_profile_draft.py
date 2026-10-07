import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "creative-review" / "scripts"))

import subprocess
import unittest

import creative_metrics as cm
import profile_draft
from review_support import FIXTURE, Scratch

ROWS = cm.load_rows(str(FIXTURE))
NAMES = sorted({r["ad_name"] for r in ROWS})


class ProfileDraftTest(unittest.TestCase):
    def setUp(self):
        self.text = profile_draft.draft(ROWS, NAMES, name="Acme Outdoor Co.", currency="USD")

    def line(self, label):
        return next(l for l in self.text.splitlines() if l.startswith("- " + label))

    def test_data_facts_are_filled_from_the_ads(self):
        self.assertIn("ugc-video", self.line("Formats in use"))
        self.assertIn("carousel", self.line("Formats in use"))
        self.assertIn("2026-03-01 to 2026-03-30, USD", self.line("Window and currency"))
        self.assertRegex(self.line("Naming convention"), r"\d+ of \d+ ad names read \(\d+%\)")
        self.assertIn("concept", self.line("Naming convention"))
        self.assertIn("durability-test", self.line("Concepts in use"))
        self.assertEqual(self.line("currency:"), "- currency: USD")

    def test_brand_voice_offers_personas_and_the_rest_are_never_filled(self):
        for label in ("Brand tone", "Standing offers", "Persona 1", "Sale and launch calendar", "Primary goal",
                      "Hero products", "Claims that need approval", "Category"):
            self.assertTrue(self.line(label).endswith(": not stated"), label)

    def test_it_follows_the_template_headings_and_names_the_brand(self):
        template = (HERE.parent / "skills" / "creative-context" / "references" / "brand-profile-template.md").read_text()
        for heading in ("## Brand", "## Products", "## Offers and calendar", "## Personas", "## Funnel and goals", "## Data",
                        "## Script settings", "## Constraints"):
            self.assertIn(heading, template)
            self.assertIn(heading, self.text)
        self.assertTrue(self.text.startswith("# Creative profile: Acme Outdoor Co."))

    def test_names_in_no_style_are_reported_as_unread_not_invented(self):
        text = profile_draft.draft([], ["Summer sale 1", "banner final v2"], name=None)
        self.assertIn("# Creative profile: unknown", text)
        self.assertIn("Window and currency: n/a (no dates), not stated", text)
        self.assertIn("Naming convention: 0 of 2 ad names read (0%): no fields found", text)

    def test_the_cli_writes_the_draft(self):
        work = Scratch(self).path
        done = subprocess.run([sys.executable, "-I", str(HERE.parent / "skills" / "creative-review" / "scripts" / "profile_draft.py"),
                               str(FIXTURE), "--name", "Acme", "-o", str(work / "creative-profile.md")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("USD", (work / "creative-profile.md").read_text())


if __name__ == "__main__":
    unittest.main()
