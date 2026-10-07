import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "creative-review" / "scripts"))

import json
import re
import unittest

from review_support import FIXTURE, FLIP_AD, ROOT, Scratch, flip_scale_ad, make_repo_copy, run, write_variant

FILES = {"ads.csv", "grade.json", "verdicts.json", "mix.json", "changes.json", "report.html", "summary.md", "run.json"}


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
        self.assertIn("was Scale, now Check before cutting", moves[0]["sentence"])
        self.assertIn("since the last review", done.stdout)
        page = (folder / "report.html").read_text()
        self.assertIn("What changed since last time", page)
        self.assertIn("Check before cutting", page.split('id="panel-changes"')[1].split("</section>")[0])

    def test_run_json_records_the_run_and_is_marked_complete_last(self):
        run(["run", FIXTURE, "--where", "format=ugc-video"], self.work)
        info = json.loads((run_folders(self.work)[-1] / "run.json").read_text())
        self.assertTrue(info["complete"])
        self.assertEqual((info["window_from"], info["window_to"], info["window_days"]), ("2026-03-01", "2026-03-30", 30))
        self.assertEqual(info["where"], ["format=ugc-video"])
        self.assertRegex(info["created_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d.*[+-]\d\d:\d\d$")
        for key in ("account_slug", "account_name", "source"):
            self.assertIn(key, info)
        self.assertRegex(run_folders(self.work)[-1].name, r"^2026-03-30_\d{8}-\d{6}$")

    def test_a_run_that_failed_is_never_the_previous_run(self):
        copy = self.work / "copy"
        copy.mkdir()
        script = make_repo_copy(copy)
        stub = copy / "skills" / "creative-report" / "scripts" / "report.py"
        real = stub.read_text()
        stub.write_text('import sys\nif "--check" in sys.argv:\n    print("problem: x")\n    sys.exit(1)\nopen(sys.argv[sys.argv.index("-o") + 1], "w").write("<html></html>")\n')
        self.assertEqual(run(["run", FIXTURE], self.work, script=script).returncode, 18)
        failed = json.loads((run_folders(self.work)[-1] / "run.json").read_text())
        self.assertFalse(failed["complete"])
        stub.write_text(real)
        done = run(["run", FIXTURE], self.work, script=script)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads((run_folders(self.work)[-1] / "changes.json").read_text()), {"first_run": True})

    def test_a_narrowed_window_is_not_compared_and_summary_and_panel_agree(self):
        run(["run", "--demo"], self.work)
        done = run(["run", "--demo", "--from", "2026-03-15"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        folder = run_folders(self.work)[-1]
        found = json.loads((folder / "changes.json").read_text())
        self.assertIn("different window or filter", found["not_compared"])
        self.assertNotIn("Spend unchanged", done.stdout)
        self.assertIn("different window or filter", done.stdout)
        page = (folder / "report.html").read_text()
        self.assertIn("different window or filter", page.split('id="panel-changes"')[1].split("</section>")[0])
        self.assertNotIn("USD 119,506", done.stdout)

    def test_summary_panel_and_tiles_show_the_same_totals_on_the_second_run(self):
        run(["run", FIXTURE], self.work)
        done = run(["run", write_variant(self.work / "flipped.csv", change=flip_scale_ad)], self.work)
        page = (run_folders(self.work)[-1] / "report.html").read_text()
        panel = page.split('id="panel-changes"')[1].split("</section>")[0]
        tiles = page.split('id="panel-kpis"')[1].split("</section>")[0]
        roas_summary = re.search(r"ROAS (\d\.\d\d)", done.stdout).group(1)
        self.assertIn("to %s (was" % roas_summary, panel)
        self.assertIn("%sx" % roas_summary, tiles)
        spend_summary = re.search(r"(USD [\d,]+) spent", done.stdout).group(1)
        self.assertIn(spend_summary, panel)
        self.assertIn(spend_summary, tiles)
        self.assertIn("vs last review (", tiles)
        self.assertNotIn("No prior period supplied", tiles)
        self.assertIn("ROAS down", done.stdout.splitlines()[2])

    def test_a_filtered_run_is_compared_with_the_same_filter_of_the_last_run(self):
        run(["run", FIXTURE, "--where", "format=ugc-video"], self.work)
        done = run(["run", FIXTURE, "--where", "format=ugc-video"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertIsNone(found["not_compared"])
        spend = next(m for m in found["account"] if m["metric"] == "Spend")
        self.assertEqual(spend["previous"], spend["current"])
        self.assertIn("Spend unchanged", done.stdout)
        self.assertEqual(run(["run", FIXTURE, "--where", "format=carousel"], self.work).returncode, 0)
        other = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertIn("different window or filter", other["not_compared"])

    def test_an_explicit_prior_file_still_wins_the_caption(self):
        run(["run", FIXTURE], self.work)
        done = run(["run", FIXTURE, "--prior", FIXTURE], self.work)
        tiles = (run_folders(self.work)[-1] / "report.html").read_text().split('id="panel-kpis"')[1].split("</section>")[0]
        self.assertIn("against the prior-period file", done.stdout)
        self.assertIn("vs last review (", tiles)

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

    def test_an_all_non_ascii_name_still_gets_the_overlap_guard(self):
        import review
        self.assertEqual(review.slugify("日本の店"), "account")
        profile = self.work / "creative-profile.md"
        profile.write_text("# Creative profile: 日本の店\n\n- Name: 日本の店\n")
        run(["run", write_variant(self.work / "a.csv"), "--profile", profile], self.work)
        done = run(["run", write_variant(self.work / "b.csv", id_offset=500), "--profile", profile], self.work)
        found = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertEqual(found["not_compared"], "This looks like a different account from the last review filed here: not compared.")
        self.assertIn("different account", done.stdout)

    def test_two_names_sharing_a_folder_are_still_told_apart_by_their_ads(self):
        import review
        self.assertEqual(review.slugify("Acme!"), review.slugify("ACME"))
        for name, offset in (("Acme!", 0), ("ACME", 500)):
            profile = self.work / "p.md"
            profile.write_text("# Creative profile: %s\n\n- Name: %s\n" % (name, name))
            run(["run", write_variant(self.work / "d.csv", id_offset=offset), "--profile", profile], self.work)
        self.assertEqual(len(list((self.work / "creative-review-runs").iterdir())), 1)
        found = json.loads((run_folders(self.work)[-1] / "changes.json").read_text())
        self.assertIn("different account", found["not_compared"])

    def test_the_run_folder_never_bumps_the_clock_on_a_collision(self):
        import datetime as dt
        import review
        moment = dt.datetime(2026, 3, 30, 23, 59, 59).astimezone()
        first = review.run_folder(self.work, "acme", "2026-03-30", moment)
        second = review.run_folder(self.work, "acme", "2026-03-30", moment)
        self.assertEqual(first.name, "2026-03-30_20260330-235959")
        self.assertEqual(second.name, "2026-03-30_20260330-235959-2")

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
