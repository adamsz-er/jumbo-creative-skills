"""The report's post-click "ways to improve" row says what the grader says: ads weak only after the cart point at checkout."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))

import creative_metrics as cm  # noqa: E402
import interact  # noqa: E402
import panels  # noqa: E402

ACME = ROOT / "examples" / "acme"


class CartRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        done = subprocess.run([sys.executable, "-I", str(ROOT / "skills" / "creative-grader" / "scripts" / "grade.py"), str(ACME / "ads_daily.csv"),
                               "--profile", str(ACME / "brand-profile.md"), "--json"], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        cls.grade = json.loads(done.stdout)
        cls.ctx = panels.Ctx(rows=cm.load_rows(str(ACME / "ads_daily.csv")), grade=cls.grade, currency="USD")

    def test_the_acme_post_click_row_points_at_checkout_as_its_ads_do(self):
        html, _ = panels.ways_to_improve(self.ctx)
        row = [r for r in re.findall(r"<tr>(.*?)</tr>", html, re.S) if 'data-weak="post-click"' in r]
        self.assertEqual(len(row), 1, html)
        self.assertIn("People add to cart but do not buy", row[0])
        self.assertIn("Check checkout, price and shipping costs first.", row[0])
        self.assertNotIn("landing page", row[0])
        members = [r["id"] for r in self.ctx.records if r["weak"] == "post-click"]
        self.assertTrue(members)
        for ad in self.grade["ads"]:
            if ad["ad"] in members:
                self.assertTrue(ad["diagnosis"]["action"].startswith("People add to cart but do not buy: check checkout"), ad["diagnosis"])

    def test_a_mixed_post_click_row_keeps_the_landing_page_and_names_the_checkout_check(self):
        records = [{"id": "1", "weak": "post-click", "spend": 10, "cart_only": True}, {"id": "2", "weak": "post-click", "spend": 5, "cart_only": False}]
        row = interact.weak_groups(records)[0]
        self.assertEqual(row["words"], interact.STEP_WORDS["post-click"])
        self.assertTrue(row["fix"].startswith(interact.STEP_FIX["post-click"]), row["fix"])
        self.assertIn("For the ads weak only after the cart, check checkout, price and shipping costs first.", row["fix"])
        landing = interact.weak_groups([dict(records[1], id="3")])[0]
        self.assertEqual((landing["words"], landing["fix"]), (interact.STEP_WORDS["post-click"], interact.STEP_FIX["post-click"]))


if __name__ == "__main__":
    unittest.main()
