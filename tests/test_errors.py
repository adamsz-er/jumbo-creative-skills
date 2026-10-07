import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "creative-review" / "scripts"))

import json
import unittest

import errors
from review_support import FIXTURE, ROOT, Scratch, make_repo_copy, run, write_variant

MCP = ROOT / "tests" / "fixtures" / "mcp_rows.json"


class ErrorTableTest(unittest.TestCase):
    def test_every_code_has_its_own_exit_status_a_message_and_a_fix(self):
        statuses = [status for status, _, _ in errors.TABLE.values()]
        self.assertEqual(len(statuses), len(set(statuses)))
        self.assertNotIn(errors.UNEXPECTED_EXIT, statuses)
        for code, (status, message, fix) in errors.TABLE.items():
            self.assertTrue(message.strip() and fix.strip(), code)
        for code in ("E-NODATA", "E-COLUMNS", "E-EMPTY", "E-RECONCILE", "E-CURRENCY", "E-SKILL", "E-PROFILE", "E-TARGET", "E-REPORT"):
            self.assertIn(code, errors.TABLE)

    def test_columns_error_names_each_missing_column_and_its_recipe_step(self):
        error = errors.columns_error("x.csv", ["spend", "date"])
        self.assertIn("missing 2 columns", error.message)
        self.assertIn("Amount spent", error.fix)
        self.assertIn("By time > Day", error.fix)


class ErrorTriggerTest(unittest.TestCase):
    """Each known failure, triggered with a fixture: plain message, the fix, its own exit code, no traceback."""

    def setUp(self):
        self.work = Scratch(self).path

    def expect(self, done, code, *fragments):
        self.assertEqual(done.returncode, errors.TABLE[code][0], done.stdout + done.stderr)
        self.assertIn(code, done.stderr)
        self.assertIn("How to fix it:", done.stderr)
        for fragment in fragments:
            self.assertIn(fragment, done.stderr)
        self.assertNotIn("Traceback", done.stdout + done.stderr)

    def test_no_data_offers_the_demo_and_the_export_recipe(self):
        self.expect(run(["run"], self.work), "E-NODATA", "--demo", "export-recipe.md", "steps 1 to 4")

    def test_a_data_path_that_does_not_exist_is_no_data(self):
        self.expect(run(["run", "missing.csv"], self.work), "E-NODATA", "missing.csv does not exist")

    def test_missing_columns_are_named_with_the_step_that_adds_them(self):
        path = write_variant(self.work / "bad.csv", drop_columns=("Impressions",))
        self.expect(run(["run", path], self.work), "E-COLUMNS", "missing 1 column", "impressions", "Customize columns")

    def test_a_file_with_no_ad_name_column_is_a_column_error_not_a_traceback(self):
        path = self.work / "noname.csv"
        path.write_text("Day,Amount spent (USD),Impressions\n2026-03-01,5,100\n")
        self.expect(run(["run", path], self.work), "E-COLUMNS", "ad name")

    def test_a_window_with_no_rows_names_the_window_and_the_dates_covered(self):
        self.expect(run(["run", FIXTURE, "--from", "2031-01-01"], self.work), "E-EMPTY", "2031-01-01", "2026-03-01 to 2026-03-30")

    def test_no_currency_in_the_header_asks_for_the_flag(self):
        path = self.work / "nocurrency.csv"
        text = FIXTURE.read_text().replace("Amount spent (USD)", "Amount spent", 1)
        path.write_text(text)
        self.expect(run(["run", path], self.work), "E-CURRENCY", "--currency")
        self.assertEqual(run(["run", path, "--currency", "usd"], self.work).returncode, 0)

    def test_a_short_pull_gives_the_percent_and_points_at_pagination(self):
        done = run(["pull", MCP, "-o", self.work / "ads.csv", "--expect-spend", "1000000"], self.work)
        self.expect(done, "E-RECONCILE", "spend", "pagination", "data-inputs.md")

    def test_a_pull_with_no_expected_totals_says_completeness_is_not_checked(self):
        first = run(["pull", MCP, "-o", self.work / "ads.csv"], self.work)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("completeness: not checked", first.stdout)

    def test_a_missing_sibling_names_it_and_the_install_command(self):
        copy = self.work / "copy"
        copy.mkdir()
        script = make_repo_copy(copy, leave_out=("keep-or-kill",))
        self.expect(run(["run", "--demo"], self.work, script=script), "E-SKILL", "keep-or-kill", "claude plugin install")

    def test_an_unreadable_profile_gives_the_path_and_never_says_to_delete_it(self):
        done = run(["run", FIXTURE, "--profile", "nope-profile.md"], self.work)
        self.expect(done, "E-PROFILE", "nope-profile.md", "Fix the line named above in nope-profile.md", "pass a different --profile")
        self.assertNotIn("elete", done.stderr)
        self.assertNotIn("elete it", (ROOT / "skills" / "creative-review" / "SKILL.md").read_text().split("E-PROFILE")[1].split("\n")[0])

    def test_a_bad_target_keeps_the_scripts_message_and_adds_the_accepted_metrics(self):
        done = run(["run", FIXTURE, "--target", "foo=3"], self.work)
        self.expect(done, "E-TARGET", "bad --target foo", "Accepted metrics:", "roas", "cpa")

    def test_a_bad_target_number_is_the_same_error(self):
        self.expect(run(["run", FIXTURE, "--target", "cpa=lots"], self.work), "E-TARGET", "must be a number")

    def test_a_dashboard_that_fails_its_own_check_is_e_report_with_the_first_failing_line(self):
        copy = self.work / "copy"
        copy.mkdir()
        script = make_repo_copy(copy)
        stub = copy / "skills" / "creative-report" / "scripts" / "report.py"
        stub.write_text('import sys\nif "--check" in sys.argv:\n    print("problem: tab pareto (Pareto) is missing")\n    sys.exit(1)\n'
                        'open(sys.argv[sys.argv.index("-o") + 1], "w").write("<html></html>")\n')
        self.expect(run(["run", "--demo"], self.work, script=script), "E-REPORT", "tab pareto (Pareto) is missing")

    def test_an_analysis_step_that_stops_names_the_step_and_keeps_the_folder(self):
        copy = self.work / "copy"
        copy.mkdir()
        script = make_repo_copy(copy)
        (copy / "skills" / "creative-mix" / "scripts" / "mix.py").write_text('import sys\nprint("the mix broke", file=sys.stderr)\nsys.exit(2)\n')
        done = run(["run", "--demo"], self.work, script=script)
        self.expect(done, "E-ANALYSIS", "mix step stopped", "the mix broke", "creative-review-runs")

    def test_an_unexpected_failure_is_one_line_and_debug_shows_the_traceback(self):
        account = self.work / "account.json"
        account.write_text("{not json")
        plain = run(["run", FIXTURE, "--account", account], self.work)
        self.assertEqual(plain.returncode, errors.UNEXPECTED_EXIT)
        self.assertIn("Something unexpected went wrong", plain.stderr)
        self.assertIn("Rerun with --debug", plain.stderr)
        self.assertNotIn("Traceback", plain.stderr)
        loud = run(["--debug", "run", FIXTURE, "--account", account], self.work)
        self.assertIn("Traceback", loud.stderr)


if __name__ == "__main__":
    unittest.main()
