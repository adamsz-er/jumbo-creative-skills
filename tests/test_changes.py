import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "creative-review" / "scripts"))

import json
import unittest

import changes
import creative_metrics as cm
from review_support import Scratch


def row(ad, spend=100.0, purchases=2.0, value=300.0):
    return {"ad_id": ad, "ad_name": "ad " + ad, "date": "2026-03-01", "spend": spend, "conversions": purchases, "conversion_value": value}


def entry(ad, verdict_id, verdict, stake=100.0):
    return {"ad": ad, "ad_name": "ad " + ad, "verdict_id": verdict_id, "verdict": verdict, "spend_at_stake": stake}


def make_run(root, name, rows, entries):
    folder = root / name
    folder.mkdir(parents=True)
    lines = ["Day,Ad name,Ad ID,Amount spent (USD),Impressions,Purchases,Purchases conversion value"]
    lines += ["%s,%s,%s,%s,1000,%s,%s" % (r["date"], r["ad_name"], r["ad_id"], r["spend"], r["conversions"], r["conversion_value"]) for r in rows]
    (folder / "ads.csv").write_text("\n".join(lines) + "\n")
    (folder / "verdicts.json").write_text(json.dumps({"ads": entries}))
    return folder


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.root = Scratch(self).path

    def test_no_previous_run_is_a_first_run(self):
        self.assertEqual(changes.compare(None, {"rows": [], "verdicts": {}}), {"first_run": True})

    def test_verdict_changes_new_and_gone_ads_sorted_by_spend_at_stake(self):
        before = make_run(self.root, "2026-03-01_090000", [row("1"), row("2"), row("3")],
                          [entry("1", "scale", "Scale"), entry("2", "keep", "Keep"), entry("3", "keep", "Keep", 5)])
        now = {"rows": [row("1"), row("2"), row("4")], "currency": "USD",
               "verdicts": {"ads": [entry("1", "pause", "Pause", 900), entry("2", "keep", "Keep"), entry("4", "keep", "Keep", 40)]}}
        found = changes.compare(before, now)
        self.assertFalse(found["first_run"])
        self.assertEqual([m["kind"] for m in found["ads"]], ["verdict", "new", "gone"])
        self.assertEqual([m["ad"] for m in found["ads"]], ["1", "4", "3"])
        self.assertIn("Scale to Pause", found["ads"][0]["sentence"])
        self.assertIn("USD 900 at stake", found["ads"][0]["sentence"])

    def test_account_moves_are_ratios_of_sums_not_averages_of_ratios(self):
        before_rows = [row("1", spend=100, value=100), row("2", spend=900, value=2700)]
        now_rows = [row("1", spend=100, value=100), row("2", spend=100, value=100)]
        before = make_run(self.root, "2026-03-01_090000", before_rows, [])
        found = changes.compare(before, {"rows": now_rows, "verdicts": {"ads": []}, "currency": "USD"})
        roas = next(m for m in found["account"] if m["metric"] == "ROAS")
        self.assertAlmostEqual(roas["previous"], 2800 / 1000)
        self.assertAlmostEqual(roas["current"], 200 / 200)
        self.assertIn("down", roas["sentence"])

    def test_a_missing_operand_reads_na_never_zero(self):
        before = make_run(self.root, "2026-03-01_090000", [row("1")], [])
        stripped = [{"ad_id": "1", "ad_name": "ad 1", "date": "2026-03-01", "spend": 50.0}]
        found = changes.compare(before, {"rows": stripped, "verdicts": {"ads": []}, "currency": "USD"})
        roas = next(m for m in found["account"] if m["metric"] == "ROAS")
        self.assertIsNone(roas["change_pct"])
        self.assertIn("n/a (missing purchase value or spend)", roas["sentence"])

    def test_latest_earlier_run_ignores_later_and_incomplete_folders(self):
        make_run(self.root, "2026-03-01_090000", [row("1")], [])
        keep = make_run(self.root, "2026-03-02_090000", [row("1")], [])
        make_run(self.root, "2026-03-09_090000", [row("1")], [])
        (self.root / "2026-03-03_090000").mkdir()
        self.assertEqual(changes.latest_earlier_run(self.root, "2026-03-05_000000"), keep)
        self.assertIsNone(changes.latest_earlier_run(self.root, "2026-03-01_000000"))
        self.assertIsNone(changes.latest_earlier_run(self.root / "none", "x"))

    def test_the_fallback_name_refuses_a_comparison_when_few_ads_are_shared(self):
        before = make_run(self.root, "2026-03-01_090000", [row(str(i)) for i in range(10)], [])
        mostly_new = {"rows": [row("0")] + [row("9%d" % i) for i in range(9)], "verdicts": {"ads": []}, "fallback_slug": True}
        refused = changes.compare(before, mostly_new)
        self.assertEqual(refused["not_compared"], changes.DIFFERENT_ACCOUNT)
        self.assertNotIn("ads", refused)
        named = dict(mostly_new, fallback_slug=False)
        self.assertIsNone(changes.compare(before, named)["not_compared"])

    def test_the_overlap_floor_is_decided_by_the_smaller_run(self):
        a = [row(str(i)) for i in range(10)]
        self.assertEqual(changes.overlap_percent(a, a[:2]), 100.0)
        self.assertEqual(changes.overlap_percent(a, [row("x")]), 0.0)
        self.assertEqual(changes.overlap_percent([], a), 0.0)


if __name__ == "__main__":
    unittest.main()
