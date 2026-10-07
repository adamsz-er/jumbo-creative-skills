import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "creative-review" / "scripts"))

import json
import re
import unittest

from review_support import FIXTURE, FLIP_AD, ROOT, Scratch, flip_scale_ad, make_repo_copy, run, write_variant

FILES = {"ads.csv", "grade.json", "verdicts.json", "mix.json", "changes.json", "report.html", "summary.md"}


def run_folders(base):
    return sorted(p for account in (base / "creative-review-runs").iterdir() for p in account.iterdir())


class ReviewRunTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def test_run_on_the_acme_csv_writes_every_file_and_prints_three_bullets_and_the_path(self):
        done = run(["run", FIXTURE, "--profile", ROOT / "examples" / "acme" / "brand-profile.md"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        folder = run_folders(self.work)[-1]
        self.assertEqual({p.name for p in folder.iterdir()}, FILES)
        bullets = [l for l in done.stdout.splitlines() if l.startswith("- ")]
        self.assertEqual(len(bullets), 3, done.stdout)
        self.assertIn("Full dashboard: %s" % (folder / "report.html").resolve(), done.stdout)
        self.assertEqual((folder / "summary.md").read_text(), done.stdout)
        self.assertRegex(bullets[0], r"USD [\d,]+ spent, [\d,]+ purchases, ROAS \d\.\d\d")
        self.assertIn("at stake", bullets[1])
        self.assertNotIn("Traceback", done.stdout + done.stderr)

    def test_demo_labels_every_output_as_sample_data(self):
        done = run(["run", "--demo"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        folder = run_folders(self.work)[-1]
        self.assertIn("sample data", done.stdout.splitlines()[0])
        self.assertIn("sample data", (folder / "report.html").read_text().split("</title>")[0])
        self.assertIn("sample-data", folder.parent.name)

    def test_first_run_shows_the_empty_state_in_the_report(self):
        run(["run", "--demo"], self.work)
        page = (run_folders(self.work)[-1] / "report.html").read_text()
        self.assertIn("What changed since last time", page)
        self.assertIn("First review of this account: next time this shows what changed.", page)
        self.assertEqual(json.loads((run_folders(self.work)[-1] / "changes.json").read_text()), {"first_run": True})

    def test_second_run_reports_the_verdict_that_flipped(self):
        run(["run", FIXTURE], self.work)
        flipped = write_variant(self.work / "flipped.csv", change=flip_scale_ad)
        done = run(["run", flipped], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        folder = run_folders(self.work)[-1]
        found = json.loads((folder / "changes.json").read_text())
        self.assertFalse(found["first_run"])
        moves = [m for m in found["ads"] if m["ad"] == FLIP_AD]
        self.assertEqual(len(moves), 1, found["ads"])
        self.assertIn("Scale", moves[0]["sentence"])
        self.assertIn("Check before cutting", moves[0]["sentence"])
        self.assertIn("since the last review", done.stdout)
        page = (folder / "report.html").read_text()
        self.assertIn("What changed since last time", page)
        self.assertIn("Check before cutting", page.split('id="panel-changes"')[1].split("</section>")[0])
        self.assertEqual(run(["--help"], self.work).returncode, 0)

    def test_the_changes_panel_sits_at_the_top_of_overview_and_the_report_still_checks(self):
        run(["run", "--demo"], self.work)
        folder = run_folders(self.work)[-1]
        page = (folder / "report.html").read_text()
        overview = page.split('id="tab-overview"')[1]
        self.assertLess(overview.index('id="panel-changes"'), overview.index('id="panel-kpis"'))
        checked = run(["--check", folder / "report.html"], self.work, script=ROOT / "skills" / "creative-report" / "scripts" / "report.py")
        self.assertEqual(checked.returncode, 0, checked.stdout)

    def test_missing_sibling_skill_stops_with_e_skill_naming_it(self):
        copy = self.work / "copy"
        copy.mkdir()
        script = make_repo_copy(copy, leave_out=("creative-mix",))
        done = run(["run", "--demo"], self.work, script=script)
        self.assertEqual(done.returncode, 15)
        self.assertIn("creative-mix", done.stderr)
        self.assertIn("How to fix it", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_flags_go_only_to_the_scripts_that_define_them(self):
        done = run(["run", FIXTURE, "--target", "cpa=40", "--where", "market=US"], self.work)
        self.assertIn(done.returncode, (0, 12, 19), done.stderr)
        self.assertNotIn("unrecognized arguments", done.stderr)


class AccountSlugTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def test_a_different_account_under_the_bare_name_is_not_compared(self):
        first = write_variant(self.work / "a.csv")
        other = write_variant(self.work / "b.csv", id_offset=500)
        run(["run", first], self.work)
        done = run(["run", other], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertIn("looks like a different account", found["not_compared"].lower())
        self.assertIn("not compared", found["not_compared"])
        self.assertNotIn("account", found)
        self.assertIn("different account", done.stdout)

    def test_the_same_data_twice_is_compared(self):
        run(["run", FIXTURE], self.work)
        run(["run", FIXTURE], self.work)
        found = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertIsNone(found["not_compared"])
        self.assertEqual(len(found["account"]), 3)

    def test_slug_order_profile_then_data_name_then_account_id_then_bare(self):
        import review
        rows = [{"ad_id": "1", "ad_name": "x", "Account ID": "act_9"}]
        self.assertEqual(review.account_slug("Acme Outdoor", rows, None)["slug"], "acme-outdoor")
        named = [{"ad_id": "1", "account_name": "Beta Shop"}]
        self.assertEqual(review.account_slug(None, named, None)["slug"], "beta-shop")
        self.assertEqual(review.account_slug(None, [{"ad_id": "1"}], {"name": "From File"})["slug"], "from-file")
        hashed = review.account_slug(None, rows, None)
        self.assertTrue(hashed["slug"].startswith("acct-") and not hashed["fallback"])
        bare = review.account_slug(None, [{"ad_id": "1"}], None)
        self.assertEqual((bare["slug"], bare["fallback"]), ("account", True))


if __name__ == "__main__":
    unittest.main()
