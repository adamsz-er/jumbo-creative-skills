import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "skills" / "creative-mix" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "creative-review" / "scripts"))

import creative_metrics as cm  # noqa: E402
import errors  # noqa: E402
import mix  # noqa: E402
import report  # noqa: E402
from review_support import REVIEW, Scratch, run  # noqa: E402

MCP = json.loads((ROOT / "tests" / "fixtures" / "mcp_rows.json").read_text())
UNREAD_MESSAGE = ("Concepts could not be read from your ad names, so gaps were not checked. "
                  "Add key-map: %s=concept to the Script settings of creative-profile.md (or pass --key-map).")


def write_pull(path, change=None):
    data = copy.deepcopy(MCP)
    for index, raw in enumerate(data["data"]):
        if change:
            change(index, raw)
    Path(path).write_text(json.dumps(data), encoding="utf-8")
    return Path(path)


def keyed_csv(path, key="ZQ", other="WX"):
    """Ads named KEY:value where neither free-text key is a built-in concept key, so no concept can be read."""
    fieldnames = ["Day", "Ad name", "Ad ID", "Amount spent (USD)", "Impressions", "Link clicks", "Purchases", "Purchases conversion value"]
    rows = []
    for number in range(1, 7):
        name = "%s:idea-%d | %s:theme-%d | FMT:%s | TYPE:bau" % (key, number, other, number, "video" if number % 2 else "static")
        for day in ("2026-03-01", "2026-03-02"):
            rows.append({"Day": day, "Ad name": name, "Ad ID": str(1000 + number), "Amount spent (USD)": 100 + number,
                         "Impressions": 10000, "Link clicks": 100, "Purchases": 4, "Purchases conversion value": 300})
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return Path(path)


class MoneyUnitTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def test_a_pull_whose_money_carries_a_unit_names_it_in_the_spend_header(self):
        responses = write_pull(self.work / "page.json")
        done = run(["pull", responses, "-o", self.work / "ads.csv"], self.work)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        header = (self.work / "ads.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("Amount spent (USD)", header.split(","))
        self.assertEqual(cm.detect_currency(self.work / "ads.csv"), "USD")

    def test_run_on_such_a_pull_needs_no_currency_flag(self):
        responses = write_pull(self.work / "page.json")
        run(["pull", responses, "-o", self.work / "ads.csv"], self.work)
        done = run(["run", self.work / "ads.csv"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("E-CURRENCY", done.stderr)

    def test_a_pull_without_units_keeps_the_plain_header(self):
        def strip(_, raw):
            for key in ("spend", "omni_purchase_values", "cost_per_action_type:video_view"):
                if isinstance(raw.get(key), dict):
                    raw[key] = raw[key]["value"]
        responses = write_pull(self.work / "page.json", strip)
        run(["pull", responses, "-o", self.work / "ads.csv"], self.work)
        self.assertEqual((self.work / "ads.csv").read_text(encoding="utf-8").splitlines()[0].split(",")[3], "Amount spent")

    def test_two_units_in_one_pull_stop_with_the_mixed_currency_error(self):
        def second_unit(index, raw):
            if index == 0:
                raw["spend"]["unit"] = "EUR"
        responses = write_pull(self.work / "page.json", second_unit)
        done = run(["pull", responses, "-o", self.work / "ads.csv"], self.work)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("E-MIXED-CURRENCY", done.stderr)
        self.assertIn("EUR", done.stderr)
        self.assertIn("USD", done.stderr)

    def test_the_error_is_in_the_table_with_its_own_exit_code(self):
        self.assertIn("E-MIXED-CURRENCY", errors.TABLE)
        self.assertEqual(len({v[0] for v in errors.TABLE.values()}), len(errors.TABLE))


class UnitEdgeTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def pull(self, *files):
        import from_mcp
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = from_mcp.main([str(f) for f in files] + ["-o", str(self.work / "ads.csv")])
        return code, out.getvalue()

    def test_some_rows_with_a_unit_and_some_without_warns_with_the_count(self):
        def strip_first(index, raw):
            if index == 0:
                raw["spend"] = raw["spend"]["value"]
        code, out = self.pull(write_pull(self.work / "a.json", strip_first))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"WARNING: 1 rows? state no currency")
        self.assertEqual((self.work / "ads.csv").read_text(encoding="utf-8").splitlines()[0].split(",")[3], "Amount spent")

    def test_a_mixed_currency_hidden_by_deduplication_is_still_caught(self):
        def eur(index, raw):
            if index == 0:
                raw["spend"]["unit"] = "EUR"
        first = write_pull(self.work / "a.json", eur)
        second = write_pull(self.work / "b.json")
        code, out = self.pull(first, second)
        self.assertEqual(code, 4, out)
        self.assertIn("mixed currency", out)

    def test_a_unit_that_is_not_a_three_letter_code_counts_as_no_unit(self):
        def dollar(_, raw):
            raw["spend"]["unit"] = "US$"
        code, out = self.pull(write_pull(self.work / "a.json", dollar))
        self.assertEqual(code, 0, out)
        self.assertEqual((self.work / "ads.csv").read_text(encoding="utf-8").splitlines()[0].split(",")[3], "Amount spent")

    def test_a_purchase_value_in_another_currency_is_mixed_too(self):
        def other(index, raw):
            if index == 0:
                raw["omni_purchase_values"]["unit"] = "EUR"
        code, out = self.pull(write_pull(self.work / "a.json", other))
        self.assertEqual(code, 4, out)


class UnreadConceptsTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def test_the_mix_flags_unread_concepts_and_names_the_most_common_unmapped_key(self):
        result = mix.analyse_mix(cm.load_rows(str(keyed_csv(self.work / "ads.csv"))))
        self.assertTrue(result["concepts_unread"])
        self.assertEqual(result["concept_key"], "WX")
        self.assertEqual(result["concepts_unread_message"], UNREAD_MESSAGE % "WX")

    def test_without_a_keyed_convention_the_message_uses_the_generic_words(self):
        rows = cm.load_rows([{"Day": "2026-03-01", "Ad name": "ad %d" % n, "Ad ID": str(n), "Amount spent": 50,
                              "Impressions": 1000} for n in range(4)])
        result = mix.analyse_mix(rows, pattern=["concept"])
        self.assertTrue(result["concepts_unread"])
        self.assertIsNone(result["concept_key"])
        self.assertEqual(result["concepts_unread_message"], UNREAD_MESSAGE % "your concept key")

    def test_a_mapped_key_reads_concepts_and_nothing_is_flagged(self):
        rows = cm.load_rows(str(keyed_csv(self.work / "ads.csv")))
        result = mix.analyse_mix(rows, key_map={"WX": "concept"})
        self.assertFalse(result["concepts_unread"])
        self.assertNotIn("concepts_unread_message", result)

    def test_the_acme_fixture_is_not_flagged(self):
        result = mix.analyse_mix(cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv")))
        self.assertFalse(result["concepts_unread"])

    def test_the_run_never_says_no_clear_gap_and_marks_the_summary_and_changes(self):
        done = run(["run", keyed_csv(self.work / "ads.csv")], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("No clear gap", done.stdout)
        self.assertIn(UNREAD_MESSAGE % "WX", done.stdout)
        folder = next(p for a in (self.work / "creative-review-runs").iterdir() for p in a.iterdir())
        self.assertTrue(json.loads((folder / "changes.json").read_text())["concepts_unread"])
        self.assertTrue(json.loads((folder / "mix.json").read_text())["concepts_unread"])

    def test_the_white_space_panel_shows_the_message_as_an_empty_state(self):
        done = run(["run", keyed_csv(self.work / "ads.csv")], self.work)
        folder = next(p for a in (self.work / "creative-review-runs").iterdir() for p in a.iterdir())
        page = (folder / "report.html").read_text(encoding="utf-8")
        self.assertIn(UNREAD_MESSAGE % "WX", page)
        self.assertNotIn("Concept by format: ads and spend", page)
        self.assertEqual(done.returncode, 0)

    def test_no_surface_claims_there_is_no_gap_or_names_unknown_as_a_value(self):
        rows = cm.load_rows(str(keyed_csv(self.work / "ads.csv")))
        result = mix.analyse_mix(rows)
        self.assertEqual(result["gaps"], [])
        self.assertFalse([o for o in result["over_reliance"] if o["name"] == "unknown"])
        text = mix.render(result)
        done = run(["run", self.work / "ads.csv"], self.work)
        folder = next(p for a in (self.work / "creative-review-runs").iterdir() for p in a.iterdir())
        page = (folder / "report.html").read_text(encoding="utf-8")
        for surface in (page, text, done.stdout):
            for phrase in ("no gap", "none found", "unknown in "):
                self.assertNotIn(phrase, surface.lower())
        self.assertGreaterEqual(page.count(UNREAD_MESSAGE % "WX"), 3)
        self.assertIn(UNREAD_MESSAGE % "WX", text)

    def test_the_mapped_run_keeps_its_gaps_line(self):
        done = run(["run", keyed_csv(self.work / "ads.csv"), "--key-map", "WX=concept"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("could not be read from your ad names", done.stdout)
        folder = next(p for a in (self.work / "creative-review-runs").iterdir() for p in a.iterdir())
        self.assertNotIn("concepts_unread", json.loads((folder / "changes.json").read_text()))

    def test_the_demo_prints_no_unread_line(self):
        done = run(["run", "--demo"], self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("could not be read from your ad names", done.stdout)


class AccountFigureTest(unittest.TestCase):
    def setUp(self):
        self.work = Scratch(self).path

    def account(self, **fields):
        path = self.work / "account.json"
        path.write_text(json.dumps(fields), encoding="utf-8")
        return str(path)

    def test_frequency_is_computed_from_impressions_and_reach(self):
        loaded = report.load_account(self.account(reach=1000, impressions=2500))
        self.assertEqual(loaded["frequency"], 2.5)
        self.assertTrue(loaded["frequency_computed"])

    def test_a_given_frequency_wins_and_is_not_marked_computed(self):
        loaded = report.load_account(self.account(reach=1000, impressions=2500, frequency=3))
        self.assertEqual(loaded["frequency"], 3.0)
        self.assertFalse(loaded["frequency_computed"])

    def test_reach_alone_says_exactly_what_is_missing(self):
        with self.assertRaises(ValueError) as caught:
            report.load_account(self.account(reach=1000))
        self.assertEqual(str(caught.exception), '--account needs "frequency", or "impressions" so frequency can be computed as impressions / reach.')

    def test_a_non_numeric_reach_keeps_the_friendly_message(self):
        with self.assertRaises(ValueError) as caught:
            report.load_account(self.account(reach="lots", frequency=2))
        self.assertEqual(str(caught.exception), '--account must be a JSON object with numeric "reach" and "frequency"')

    def test_reach_that_is_not_positive_has_its_own_error(self):
        for fields in ({"reach": 0, "impressions": 100}, {"reach": -5, "frequency": 2}):
            with self.assertRaises(ValueError) as caught:
                report.load_account(self.account(**fields))
            self.assertEqual(str(caught.exception), '--account "reach" must be a positive number.')

    def test_a_null_frequency_with_impressions_is_computed(self):
        loaded = report.load_account(self.account(reach=1000, frequency=None, impressions=3000))
        self.assertEqual(loaded["frequency"], 3.0)
        self.assertTrue(loaded["frequency_computed"])

    def test_a_computed_frequency_is_labelled_on_the_tile(self):
        loaded = report.load_account(self.account(reach=1000, impressions=2500))
        page = report.build_html(rows=cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv")), account=loaded)
        self.assertIn("(computed)", page)

    def test_a_scoped_report_with_an_unscoped_account_file_carries_the_caption(self):
        loaded = report.load_account(self.account(reach=1000, frequency=2))
        rows = cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv"))
        page = report.build_html(rows=rows, account=loaded, scope="market US")
        self.assertIn("account-wide figure, not filtered to market US", page)

    def test_a_matching_scope_key_removes_the_caption(self):
        loaded = report.load_account(self.account(reach=1000, frequency=2, scope="market US"))
        rows = cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv"))
        page = report.build_html(rows=rows, account=loaded, scope="market US")
        self.assertNotIn("account-wide figure, not filtered to", page)

    def test_no_scope_means_no_caption(self):
        loaded = report.load_account(self.account(reach=1000, frequency=2))
        page = report.build_html(rows=cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv")), account=loaded)
        self.assertNotIn("account-wide figure, not filtered to", page)


if __name__ == "__main__":
    unittest.main()
