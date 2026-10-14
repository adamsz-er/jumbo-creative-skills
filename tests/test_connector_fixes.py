import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import creative_metrics as cm  # noqa: E402
import from_mcp  # noqa: E402


def wrapped(rows, info=None):
    """A response shaped like the hosted connector's: rows as a JSON string under ad_entities."""
    response = {"ad_entities": json.dumps(rows)}
    if info:
        response["additional_info"] = info
    return response


def day(ad_id, name, date, spend, impressions, **extra):
    row = {"id": ad_id, "name": name, "date_start": date, "date_stop": date,
           "amount_spent": {"value": str(spend), "unit": "USD"}, "impressions": str(impressions)}
    row.update(extra)
    return row


ROWS = [
    day("1", "TH:BAU | CN:Trail | SN:SS26 | Polished | Ana | FT:Video | US | 2026/03/01", "2026-03-01", 10, 1000),
    day("1", "TH:BAU | CN:Trail | SN:SS26 | Polished | Ana | FT:Video | US | 2026/03/01", "2026-03-02", 20, 2000),
    # one segment short: the market sits one place earlier, but still second from the end
    day("2", "TH:BAU | CN:Camp | SN:SS26 | Polished | FT:Image | CA | 2026/03/01", "2026-03-01", 5, 500),
    # a second, older convention with another separator
    day("3", "Trail_BAU_Ecom_SS26_V1_Catalogue__US", "2026-03-01", 7, 700),
    day("4", "Camp_BAU_Ecom_SS26_V2_Catalogue__CA", "2026-03-01", 3, 300),
]


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = from_mcp.main(argv)
    return code, out.getvalue()


class ResponseShapeTest(unittest.TestCase):
    def test_rows_under_an_ad_entities_string_are_read(self):
        self.assertEqual(len(cm.rows_from_response(wrapped(ROWS))), len(ROWS))

    def test_a_plain_list_and_a_data_list_still_read(self):
        self.assertEqual(len(cm.rows_from_response(ROWS)), len(ROWS))
        self.assertEqual(len(cm.rows_from_response({"data": ROWS})), len(ROWS))

    def test_any_other_shape_is_refused(self):
        with self.assertRaises(ValueError):
            cm.rows_from_response({"ad_entities": "not json"})
        with self.assertRaises(ValueError):
            cm.rows_from_response("rows")

    def test_load_rows_reads_a_wrapped_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "page.json")
            path.write_text(json.dumps(wrapped(ROWS)))
            self.assertEqual(len(cm.load_rows(str(path), level="ad")), len(ROWS))


class AdapterOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, response, *flags):
        page = self.dir / "page.json"
        page.write_text(json.dumps(response))
        out = self.dir / "ads.csv"
        code, text = run_main([str(page), "-o", str(out)] + list(flags))
        with open(out, newline="") as handle:
            return code, text, list(csv.DictReader(handle))

    def test_wrapped_response_reconciles(self):
        code, text, rows = self._run(wrapped(ROWS), "--expect-spend", "45")
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), len(ROWS))
        self.assertIn("reconciled against the expected totals", text)

    def test_connector_notes_are_printed_and_refused_fields_warned(self):
        info = "Unsupported fields: cost_per_action_type:video_view. Supported fields at this level are: id, name."
        code, text, _ = self._run(wrapped(ROWS, info))
        self.assertEqual(code, 0)
        self.assertIn("CONNECTOR NOTE page.json: Unsupported fields: cost_per_action_type:video_view", text)
        self.assertIn("WARNING: the connector refused some requested fields", text)

    def test_reconcile_warning_still_comes_first(self):
        code, text, _ = self._run(wrapped(ROWS, "Unsupported fields: x."), "--expect-spend", "1000")
        self.assertEqual(code, 3)
        self.assertTrue(text.startswith("WARNING: the pull does not reconcile"))

    def test_fields_no_row_carries_are_named(self):
        _, text, _ = self._run(wrapped(ROWS))
        line = next(l for l in text.splitlines() if l.startswith("fields no row carries"))
        for words in ("link clicks", "purchases", "ThruPlays", "3-second plays", "objective"):
            self.assertIn(words, line)

    def test_market_is_filled_from_names_of_every_shape(self):
        _, _, rows = self._run(wrapped(ROWS))
        self.assertEqual({r["Ad ID"]: r["market"] for r in rows}, {"1": "US", "2": "CA", "3": "US", "4": "CA"})

    def test_aggregates_carry_the_market_that_where_reads(self):
        rows = cm.load_rows(ROWS, level="ad")
        ads = {a["ad_id"]: a["market"] for a in cm.aggregate_by_ad(rows)}
        kept = {r["ad_id"] for r in cm.filter_rows(rows, cm.parse_where(["market=US"]))}
        self.assertEqual(ads, {"1": "US", "2": "CA", "3": "US", "4": "CA"})
        self.assertEqual(kept, {a for a, m in ads.items() if m == "US"})

    def test_leads_are_carried_from_the_grouped_lead_field(self):
        _, _, rows = self._run(wrapped([day("9", "a", "2026-03-01", 4, 400, onsite_conversion_lead_grouped="3")]))
        self.assertEqual(rows[0]["Leads"], "3")


class RoundedCostPerViewTest(unittest.TestCase):
    def test_rounding_error_comes_from_the_decimals_shown(self):
        self.assertAlmostEqual(cm.rounding_error("0.02"), 25.0)
        self.assertAlmostEqual(cm.rounding_error({"value": "1.25", "unit": "USD"}), 0.4)
        self.assertIsNone(cm.rounding_error("0"))

    def test_a_coarse_cost_is_not_derived_and_says_why(self):
        row = cm.load_rows([{"ad_name": "a", "spend": 10, "cost_per_video_view": {"value": "0.02"}}])[0]
        self.assertIsNone(row.get("video_views_3s"))
        self.assertTrue(row["video_views_3s_source"].startswith(cm.NOT_DERIVED_3S))
        self.assertIn("25%", row["video_views_3s_source"])

    def test_a_precise_cost_under_the_new_name_is_derived(self):
        row = cm.load_rows([{"ad_name": "a", "spend": 10, "cost_per_video_view": "0.0412"}])[0]
        self.assertAlmostEqual(row["video_views_3s"], 10 / 0.0412)
        self.assertEqual(row["video_views_3s_source"], cm.DERIVED_3S)

    def test_one_refused_day_leaves_the_ad_without_plays(self):
        rows = cm.load_rows([
            {"ad_name": "a", "date": "2026-03-01", "spend": 10, "impressions": 900, "cost_per_video_view": "1.25"},
            {"ad_name": "a", "date": "2026-03-02", "spend": 10, "impressions": 900, "cost_per_video_view": "0.02"}])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertIsNone(ad["video_views_3s"])
        self.assertIsNone(ad["hook_rate"])
        self.assertTrue(ad["video_views_3s_source"].startswith(cm.NOT_DERIVED_3S))

    def test_refused_plays_are_named_with_their_reason_in_absent_fields(self):
        rows = from_mcp.merge([day("1", "a", "2026-03-01", 10, 900, cost_per_video_view={"value": "0.02"})])
        self.assertIn("3-second plays (not derived", " ".join(from_mcp.absent_fields(rows)))


if __name__ == "__main__":
    unittest.main()
