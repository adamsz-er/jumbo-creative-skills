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


def entry(ad, verdict_id, verdict, stake=100.0):  # verdict is the script's full text, e.g. "Scale: raise budget in steps"
    return {"ad": ad, "ad_name": "ad " + ad, "verdict_id": verdict_id, "verdict": verdict, "spend_at_stake": stake}


def make_run(root, name, rows, entries, created="2026-03-01T09:00:00+10:00", complete=True, window_days=1, where=None):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"created_at": created, "window_days": window_days, "where": where, "complete": complete}))
    lines = ["Day,Ad name,Ad ID,Amount spent (USD),Impressions,Purchases,Purchases conversion value"]
    lines += ["%s,%s,%s,%s,1000,%s,%s" % (r["date"], r["ad_name"], r["ad_id"], r["spend"], r["conversions"], r["conversion_value"]) for r in rows]
    (folder / "ads.csv").write_text("\n".join(lines) + "\n")
    (folder / "verdicts.json").write_text(json.dumps({"ads": entries}))
    return folder


def current(rows, verdicts=None, **more):
    return dict({"rows": rows, "verdicts": verdicts or {"ads": []}, "currency": "USD", "window_days": 1, "where": None}, **more)


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.root = Scratch(self).path

    def test_no_previous_run_is_a_first_run(self):
        self.assertEqual(changes.compare(None, {"rows": [], "verdicts": {}}), {"first_run": True})

    def test_verdict_changes_new_and_gone_ads_sorted_by_spend_at_stake(self):
        before = make_run(self.root, "a", [row("1"), row("2"), row("3")],
                          [entry("1", "scale", "Scale: raise budget in steps"), entry("2", "keep", "Keep"), entry("3", "keep", "Keep", 5)])
        now = current([row("1"), row("2"), row("4")],
                      {"ads": [entry("1", "pause", "Pause: never worked", 900), entry("2", "keep", "Keep"), entry("4", "keep", "Keep", 40)]})
        found = changes.compare(before, now)
        self.assertFalse(found["first_run"])
        self.assertEqual([m["kind"] for m in found["ads"]], ["verdict", "new", "gone"])
        self.assertEqual([m["ad"] for m in found["ads"]], ["1", "4", "3"])
        self.assertEqual(found["ads"][0]["sentence"], "ad 1: was Scale, now Pause (USD 900 at stake)")

    def test_account_moves_are_ratios_of_sums_not_averages_of_ratios(self):
        before = make_run(self.root, "a", [row("1", spend=100, value=100), row("2", spend=900, value=2700)], [])
        found = changes.compare(before, current([row("1", spend=100, value=100), row("2", spend=100, value=100)]))
        roas = next(m for m in found["account"] if m["metric"] == "ROAS")
        self.assertAlmostEqual(roas["previous"], 2800 / 1000)
        self.assertAlmostEqual(roas["current"], 200 / 200)
        self.assertIn("down", roas["sentence"])

    def test_a_missing_operand_reads_na_never_zero(self):
        before = make_run(self.root, "a", [row("1")], [])
        found = changes.compare(before, current([{"ad_id": "1", "ad_name": "ad 1", "date": "2026-03-01", "spend": 50.0}]))
        roas = next(m for m in found["account"] if m["metric"] == "ROAS")
        self.assertIsNone(roas["change_pct"])
        self.assertIn("n/a (missing purchase value or spend)", roas["sentence"])

    def test_previous_run_is_the_newest_finished_one_strictly_older_by_created_at(self):
        make_run(self.root, "old", [row("1")], [], created="2026-03-01T09:00:00+10:00")
        keep = make_run(self.root, "keep", [row("1")], [], created="2026-03-02T09:00:00+10:00")
        make_run(self.root, "later", [row("1")], [], created="2026-03-09T09:00:00+10:00")
        make_run(self.root, "failed", [row("1")], [], created="2026-03-03T09:00:00+10:00", complete=False)
        (self.root / "no-run-json").mkdir()
        self.assertEqual(changes.latest_earlier_run(self.root, "2026-03-05T00:00:00+10:00"), keep)
        self.assertIsNone(changes.latest_earlier_run(self.root, "2026-03-01T09:00:00+10:00"))
        self.assertIsNone(changes.latest_earlier_run(self.root / "none", "2026-03-05T00:00:00+10:00"))

    def test_order_comes_from_created_at_not_from_the_folder_name(self):
        make_run(self.root, "2026-10-02_20261008-090000", [row("1")], [], created="2026-10-08T09:00:00+10:00")
        newer = make_run(self.root, "2026-10-01_20261008-150000", [row("1")], [], created="2026-10-08T15:00:00+10:00")
        self.assertEqual(changes.latest_earlier_run(self.root, "2026-10-08T16:00:00+10:00"), newer)

    def test_the_overlap_check_always_runs_and_counts_against_the_larger_run(self):
        a = [row(str(i)) for i in range(100)]
        self.assertEqual(changes.overlap_percent(a, a[:1]), 1.0)
        self.assertEqual(changes.overlap_percent([], a), 0.0)
        before = make_run(self.root, "a", a, [])
        self.assertEqual(changes.compare(before, current([row("0")]))["not_compared"], changes.DIFFERENT_ACCOUNT)

    def test_the_boundary_17_of_100_refuses_and_18_of_100_compares(self):
        a = [row(str(i)) for i in range(100)]
        before = make_run(self.root, "a", a, [])
        seventeen = [row(str(i)) for i in range(17)] + [row("x%d" % i) for i in range(83)]
        eighteen = [row(str(i)) for i in range(18)] + [row("x%d" % i) for i in range(82)]
        self.assertEqual(changes.compare(before, current(seventeen))["not_compared"], changes.DIFFERENT_ACCOUNT)
        self.assertIsNone(changes.compare(before, current(eighteen))["not_compared"])

    def test_a_different_window_length_or_filter_is_not_compared(self):
        before = make_run(self.root, "a", [row("1")], [], window_days=30, where=["market=us"])
        self.assertEqual(changes.compare(before, current([row("1")], window_days=15, where=["market=us"]))["not_compared"], changes.DIFFERENT_SCOPE)
        self.assertEqual(changes.compare(before, current([row("1")], window_days=30, where=None))["not_compared"], changes.DIFFERENT_SCOPE)
        self.assertIsNone(changes.compare(before, current([row("1")], window_days=30, where=["market=us"]))["not_compared"])

    def test_the_previous_runs_data_is_scoped_before_it_is_compared(self):
        before = make_run(self.root, "a", [row("1", spend=100), row("2", spend=900)], [])
        only_one = lambda rows: [r for r in rows if r["ad_id"] == "1"]  # noqa: E731
        found = changes.compare(before, current([row("1", spend=100)], scope=only_one))
        spend = next(m for m in found["account"] if m["metric"] == "Spend")
        self.assertEqual(spend["previous"], 100)


if __name__ == "__main__":
    unittest.main()
