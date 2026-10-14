"""An ad whose only issue is an after-click step that could not be tested is its own row in the report and dashboard, never "none"."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))

import creative_metrics as cm  # noqa: E402
import dashboard  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402

TARGET = "90003"


def raw_rows():
    """Eight static ads; ad 90003 buys 8 of its 20 daily adds to cart while its peers buy more than they add, so its gap can't be tested."""
    out = []
    for ad in range(8):
        for day in range(20):
            out.append({"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad, "Ad ID": "9000%d" % ad,
                        "Amount spent (USD)": 25 if ad == 3 else 100 + ad, "Impressions": 20000, "Link clicks": 300,
                        "Adds to cart": 20, "Purchases": 8 if ad == 3 else 30 + ad})
    return out


class UntestedGroupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.json"
            path.write_text(json.dumps(raw_rows()), encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(ROOT / "skills" / "creative-grader" / "scripts" / "grade.py"), str(path), "--json"],
                                  capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        cls.grade = json.loads(done.stdout)
        cls.rows = cm.load_rows(raw_rows())
        cls.ctx = panels.Ctx(rows=cls.rows, grade=cls.grade, currency="USD")

    def test_the_ways_to_improve_table_gives_it_its_own_row_never_none(self):
        html, _ = panels.ways_to_improve(self.ctx)
        rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
        untested = [r for r in rows if 'data-weak="untested"' in r]
        self.assertEqual(len(untested), 1, rows)
        self.assertIn("Not known: cart to purchase rate could not be tested (its group has more purchases than adds to cart)", untested[0])
        self.assertIn("Check that the add-to-cart event is tracked", untested[0])
        self.assertIn('<td class="num" data-label="Ads">1</td>', untested[0])
        self.assertIn('data-weak="untested"', report.build_html(rows=self.rows, grade=self.grade, currency="USD"))
        record = next(r for r in self.ctx.records if r["id"] == TARGET)
        self.assertEqual(record["weak"], "untested")
        self.assertNotIn(TARGET, [r["id"] for r in self.ctx.records if r["weak"] == "none"])

    def test_the_dashboard_rows_carry_the_untested_step(self):
        rows = {r["ad_id"]: r for r in dashboard.build_datasets(self.ctx)[0]["verdicts"]}
        self.assertEqual(rows[TARGET].get("weak_step"), "untested")
        self.assertIsNone(rows[TARGET].get("weak_step_note"))
        self.assertEqual(sum(1 for r in rows.values() if r.get("weak_step") == "untested"), 1)
        self.assertIn("untested", panels.interact.WEAK_VALUES)


if __name__ == "__main__":
    unittest.main()
