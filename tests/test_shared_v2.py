"""Package v2 additions to the shared module: new funnel fields and metrics, the delivery curve and the evidence views."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))

import creative_metrics as cm  # noqa: E402
import dashboard  # noqa: E402
import panels  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
EXTENDED = ROOT / "examples" / "acme" / "ads_daily_extended.csv"
EVIDENCE = ROOT / "shared" / "evidence.py"


class FunnelPooledZeroTest(unittest.TestCase):
    def test_peers_that_all_report_a_real_zero_still_give_a_gap_test(self):
        def ad(ad_id, landing):
            return {"ad_id": ad_id, "format": "static", "impressions": 5000, "link_clicks": 100, "clicks": 100,
                    "landing_page_views": landing}
        ads = [dict(a, **cm.compute_metrics(a)) for a in [ad("1", 30)] + [ad(str(i), 0) for i in range(2, 8)]]
        real = cm.grade_against
        cm.grade_against = lambda *a, **k: dict(real(*a, **k), band=cm.BAND_BOTTOM, basis="account")
        try:
            read = cm.funnel_read([], ads[0], ads)
        finally:
            cm.grade_against = real
        step = next(s for s in read["steps"] if s["metric"] == "landing_page_view_rate")
        self.assertIsNotNone(step["gap_z"])


class NewMetricsTest(unittest.TestCase):
    def test_export_headers_map_to_the_schema_ids(self):
        rows = cm.load_rows([{"Day": "2026-03-01", "Ad ID": "1", "Ad name": "a", "Amount spent (USD)": "9",
                              "Impressions": "900", "Link clicks": "40", "Landing page views": "31",
                              "Adds to cart": "8", "Checkouts initiated": "5", "Purchases": "3",
                              "New customer purchases": "2"}])
        row = rows[0]
        self.assertEqual((row["landing_page_views"], row["checkouts"], row["new_customers"]), (31, 5, 2))
        values = cm.compute_metrics(row)
        self.assertAlmostEqual(values["landing_page_view_rate"], 31 / 40 * 100)
        self.assertAlmostEqual(values["cart_to_checkout_rate"], 5 / 8 * 100)
        self.assertAlmostEqual(values["new_customer_purchase_share"], 2 / 3 * 100)

    def test_a_missing_operand_is_named_never_zero(self):
        row = {"link_clicks": 40, "add_to_carts": 0, "conversions": 3}
        self.assertEqual(cm.format_value(row, "landing_page_view_rate"), "n/a (missing landing_page_views)")
        self.assertEqual(cm.format_value(row, "cart_to_checkout_rate"), "n/a (missing checkouts)")
        self.assertEqual(cm.format_value(dict(row, checkouts=2), "cart_to_checkout_rate"), "n/a (zero add_to_carts)")
        self.assertEqual(cm.format_value(row, "new_customer_purchase_share"), "n/a (missing new_customers)")

    def test_the_metrics_doc_defines_every_new_id(self):
        text = (ROOT / "skills" / "creative-context" / "references" / "metrics.md").read_text(encoding="utf-8")
        for metric in ("landing_page_view_rate", "cart_to_checkout_rate", "new_customer_purchase_share"):
            self.assertIn("| `%s` |" % metric, text)
        for field in ("`landing_page_views`", "`checkouts`", "`new_customers`"):
            self.assertIn(field, text)

    def test_new_name_keys_read_persona_hook_offer_and_version(self):
        fields = cm.parse_name("CONCEPT:trail | FMT:video | PERSONA:weekend-hiker | HOOK:question | OFFER:gwp | VER:v2")
        self.assertEqual((fields["persona"], fields["hook"], fields["offer"], fields["version"]),
                         ("weekend-hiker", "question", "gwp", "v2"))


class DeliveryCurveParityTest(unittest.TestCase):
    """The shared curve must equal the report's age curve, so the fatigue planner and the dashboard agree."""

    def test_matches_the_dashboard_age_curve_on_the_fixture(self):
        rows = cm.load_rows(str(FIXTURE))
        ctx = panels.Ctx(rows)
        report = {(r["metric"], r["delivery_day"]): r for r in dashboard.age_curve_rows(ctx, "cpa")}
        shared = cm.delivery_curve(rows, ("hook_rate", "ctr", "frequency"))
        compared = 0
        for metric, days in shared.items():
            for day in days:
                theirs = report[(metric, day["delivery_day"])]
                self.assertEqual(theirs["ads"], day["ads"])
                for key in ("median", "p25", "p75"):
                    if day[key] is None:
                        self.assertIsNone(theirs[key])
                    else:
                        self.assertAlmostEqual(theirs[key], day[key], places=5)  # the report rounds to 6 places
                compared += 1
        self.assertEqual(compared, sum(1 for k in report if k[0] != "payback"))

    def test_ads_running_before_the_window_are_left_out(self):
        rows = cm.load_rows(str(FIXTURE))
        self.assertEqual(cm.launched_in_window(rows, "120000000001"), (None, cm.BEFORE_WINDOW))
        self.assertEqual(cm.launched_in_window(rows, "120000000030")[0], "2026-03-27")

    def test_a_day_with_too_few_ads_has_no_band(self):
        curve = cm.delivery_curve(cm.load_rows(str(FIXTURE)), ("ctr",), min_ads=99)
        self.assertTrue(all(d["median"] is None and d["note"].startswith("n/a (fewer than 99") for d in curve["ctr"]))


class ExtendedFixtureTest(unittest.TestCase):
    def test_extended_export_keeps_every_original_column_and_adds_four(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import make_fixture
        base = make_fixture.build(7)
        extended = make_fixture.extend(base, 7)
        self.assertEqual([row[:len(make_fixture.HEADERS)] for row in extended], base)
        self.assertTrue(all(len(row) == len(make_fixture.HEADERS) + len(make_fixture.EXTRA_HEADERS) for row in extended))

    def test_checked_in_files_match_the_generator(self):
        import csv
        sys.path.insert(0, str(ROOT / "tools"))
        import make_fixture
        with open(EXTENDED, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], make_fixture.HEADERS + make_fixture.EXTRA_HEADERS)
        expected = [[str(c) for c in r] for r in make_fixture.extend(make_fixture.build(7), 7)]
        self.assertEqual(rows[1:], expected)
        with open(FIXTURE, newline="", encoding="utf-8") as handle:
            self.assertEqual(list(csv.reader(handle))[1:], [[str(c) for c in r] for r in make_fixture.build(7)])


class EvidenceViewsTest(unittest.TestCase):
    def run_view(self, *args):
        done = subprocess.run([sys.executable, "-I", str(EVIDENCE)] + [str(a) for a in args],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_json_contract_carries_schema_and_every_section(self):
        data = json.loads(self.run_view(EXTENDED, "--json"))
        self.assertEqual(data["schema"], 1)
        for key in ("records", "segments", "angles", "hooks", "coverage", "top_quartile", "fatiguing", "never_worked", "gaps"):
            self.assertIn(key, data)
        self.assertEqual(data["segments"]["field"], "adset_name")
        self.assertEqual({r["value"] for r in data["segments"]["rows"]},
                         {"weekend-hikers", "family-campers", "gear-upgraders", "past-visitors", "broad-prospecting"})
        self.assertTrue(all(r["ad_ids"] for r in data["segments"]["rows"]))

    def test_persona_view_names_ads_and_new_customer_share(self):
        text = self.run_view(EXTENDED, "--for", "persona")
        self.assertIn("Results by adset_name", text)
        self.assertIn("new-customer share", text)
        self.assertIn("120000000002", text)

    def test_persona_view_without_a_tag_says_personas_are_unbacked(self):
        text = self.run_view(FIXTURE, "--for", "persona")
        self.assertIn("no persona or audience tag in the data", text)
        self.assertIn("unbacked", text)

    def test_new_customer_share_missing_is_named_not_zero(self):
        data = json.loads(self.run_view(FIXTURE, "--segment", "ad_type", "--json"))
        for row in data["segments"]["rows"]:
            self.assertIsNone(row["new_customer_purchase_share"])
            self.assertEqual(row["new_customer_note"], "n/a (missing new_customers)")

    def test_hooks_view_sets_faded_hooks_apart_and_names_missing_openings(self):
        data = json.loads(self.run_view(FIXTURE, "--json"))
        faded = [h["ad"] for h in data["hooks"]["faded"]]
        self.assertIn("120000000001", faded)
        self.assertNotIn("120000000001", [h["ad"] for h in data["hooks"]["top"]])
        text = self.run_view(FIXTURE, "--for", "hooks")
        self.assertIn("n/a (missing primary text", text)

    def test_hooks_view_reads_an_opening_line_when_the_export_has_text(self):
        rows = [dict(r, primary_text="Rain all week? This shell kept me dry on every trail. Here is how.")
                for r in cm.load_rows(str(FIXTURE))]
        sys.path.insert(0, str(ROOT / "shared"))
        import evidence
        result = evidence.build_evidence(rows)
        self.assertTrue(all(r["opening"].startswith("Rain all week?") for r in result["records"]))

    def test_verdicts_join_onto_records(self):
        verdicts = subprocess.run([sys.executable, "-I", str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"),
                                   str(FIXTURE), "--json"], capture_output=True, text=True).stdout
        path = Path(self.id().replace(".", "_") + ".json")
        try:
            path.write_text(verdicts, encoding="utf-8")
            data = json.loads(self.run_view(FIXTURE, "--verdicts", path, "--json"))
        finally:
            path.unlink()
        record = next(r for r in data["records"] if r["ad"] == "120000000001")
        self.assertEqual(record["verdict_id"], "iterate")
        self.assertEqual(data["verdicts_source"], "keep-or-kill")

    def test_ideation_view_lists_coverage_and_says_when_no_scan_was_given(self):
        text = self.run_view(FIXTURE, "--for", "ideation")
        self.assertIn("Concept x format coverage", text)
        self.assertIn("Competitor scan: not supplied", text)

    def test_no_usable_rows_is_none_available_and_unbacked(self):
        sys.path.insert(0, str(ROOT / "shared"))
        import evidence
        empty = evidence.build_evidence([])
        self.assertFalse(empty["available"])
        self.assertEqual(evidence.render(empty), evidence.NONE_AVAILABLE)
        for render in (evidence.render_persona, evidence.render_hooks, evidence.render_ideation):
            self.assertIn("unbacked", render(empty))

    def test_bad_verdicts_file_is_a_plain_error(self):
        path = Path(self.id().replace(".", "_") + ".json")
        try:
            path.write_text("[]", encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(EVIDENCE), str(FIXTURE), "--verdicts", str(path)],
                                  capture_output=True, text=True)
        finally:
            path.unlink()
        self.assertEqual(done.returncode, 2)
        self.assertIn("keep-or-kill --json output", done.stderr)


if __name__ == "__main__":
    unittest.main()
