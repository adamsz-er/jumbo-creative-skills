import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "tools"))

import creative_metrics as cm  # noqa: E402
import make_fixture  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"


class ComputeMetricsTest(unittest.TestCase):
    ROW = {
        "spend": 200.0, "impressions": 10000.0, "reach": 8000.0, "video_views_3s": 3000.0,
        "video_thruplay": 900.0, "link_clicks": 150.0, "clicks": 250.0, "conversions": 10.0,
        "conversion_value": 800.0, "add_to_carts": 25.0, "revenue": 1000.0,
    }

    def test_every_metric_matches_hand_computation(self):
        m = cm.compute_metrics(self.ROW)
        self.assertAlmostEqual(m["hook_rate"], 30.0)
        self.assertAlmostEqual(m["hold_rate"], 30.0)
        self.assertAlmostEqual(m["video_completion_rate"], 9.0)
        self.assertAlmostEqual(m["ctr"], 1.5)
        self.assertAlmostEqual(m["cpm"], 20.0)
        self.assertAlmostEqual(m["cpc"], 200.0 / 150.0)  # same click type as ctr: link clicks
        self.assertAlmostEqual(m["cpa"], 20.0)
        self.assertAlmostEqual(m["roas"], 4.0)
        self.assertAlmostEqual(m["cvr"], 4.0)
        self.assertAlmostEqual(m["add_to_cart_rate"], 10.0)
        self.assertAlmostEqual(m["cost_per_add_to_cart"], 8.0)
        self.assertAlmostEqual(m["frequency"], 1.25)
        self.assertAlmostEqual(m["mer"], 5.0)

    def test_ctr_uses_link_clicks_and_falls_back_to_all_clicks(self):
        self.assertAlmostEqual(cm.compute_metrics(self.ROW)["ctr"], 1.5)
        no_link = dict(self.ROW, link_clicks=None)
        self.assertAlmostEqual(cm.compute_metrics(no_link)["ctr"], 2.5)
        self.assertEqual(cm.metric_basis(no_link, "ctr")["numerator"], "clicks")
        self.assertEqual(cm.metric_basis(self.ROW, "ctr")["numerator"], "link_clicks")

    def test_thumb_stop_rate_is_an_alias_not_a_second_metric(self):
        self.assertNotIn("thumb_stop_rate", cm.compute_metrics(self.ROW))
        self.assertEqual(cm.resolve_metric("thumb_stop_rate"), "hook_rate")

    def test_zero_denominators_return_none_not_zero(self):
        row = dict(self.ROW, impressions=0.0, spend=0.0, link_clicks=0.0, clicks=0.0, add_to_carts=0.0,
                   video_views_3s=0.0, conversions=0.0, reach=0.0)
        for name, value in cm.compute_metrics(row).items():
            self.assertIsNone(value, name)

    def test_missing_operand_returns_none_and_renders_reason(self):
        row = dict(self.ROW, video_thruplay=None)
        self.assertIsNone(cm.compute_metrics(row)["hold_rate"])
        self.assertEqual(cm.format_value(row, "hold_rate"), "n/a (missing video_thruplay)")
        self.assertIsNone(cm.compute_metrics({})["ctr"])

    def test_p75_is_never_substituted_for_thruplay(self):
        row = dict(self.ROW, video_thruplay=None, video_p75=500.0)
        self.assertIsNone(cm.compute_metrics(row)["hold_rate"])

    def test_true_zero_numerator_is_zero_not_none(self):
        row = dict(self.ROW, conversion_value=0.0)
        self.assertEqual(cm.compute_metrics(row)["roas"], 0.0)

    def test_zero_denominator_reason_names_the_field(self):
        self.assertEqual(cm.format_value({"spend": 5.0, "impressions": 0.0}, "cpm"), "n/a (zero impressions)")


class LoadRowsTest(unittest.TestCase):
    def test_csv_headers_map_to_canonical_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Day", "Ad name", "Ad ID", "Amount spent (AUD)", "Impressions", "Reach",
                                 "3-second video plays", "ThruPlays", "Link clicks", "Clicks (all)", "Purchases",
                                 "Purchases conversion value", "Adds to cart", "Custom col"])
                writer.writerow(["2026-03-01", "a", "9", "1,234.50", "1,000", "800", "300", "", "10", "20", "2",
                                 "99.5", "4", "keep me"])
            row = cm.load_rows(path)[0]
        self.assertEqual(row["spend"], 1234.5)
        self.assertEqual(row["impressions"], 1000.0)
        self.assertEqual(row["video_views_3s"], 300.0)
        self.assertIsNone(row["video_thruplay"] if "video_thruplay" in row else None)
        self.assertNotIn("video_thruplay", row)
        self.assertEqual((row["link_clicks"], row["clicks"], row["conversions"]), (10.0, 20.0, 2.0))
        self.assertEqual((row["conversion_value"], row["add_to_carts"]), (99.5, 4.0))
        self.assertEqual((row["date"], row["ad_name"], row["ad_id"]), ("2026-03-01", "a", "9"))
        self.assertEqual(row["Custom col"], "keep me")

    def test_header_matching_ignores_case_and_punctuation(self):
        row = cm.load_rows([{"AMOUNT SPENT (usd)": "5", "thru-plays": "2", "reporting starts": "2026-01-02"}])[0]
        self.assertEqual((row["spend"], row["video_thruplay"], row["date"]), (5.0, 2.0, "2026-01-02"))

    def test_api_rows_actions_and_video_lists(self):
        api = {
            "ad_id": "55", "ad_name": "n", "date_start": "2026-03-02", "spend": "10.5", "impressions": "1000",
            "reach": "900", "inline_link_clicks": "12", "clicks": "30",
            "actions": [{"action_type": "video_view", "value": "400"}, {"action_type": "purchase", "value": "3"},
                        {"action_type": "add_to_cart", "value": "7"}, {"action_type": "link_click", "value": "12"}],
            "action_values": [{"action_type": "purchase", "value": "180.25"}],
            "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "120"}],
            "ctr": "1.2",
        }
        row = cm.load_rows([api])[0]
        self.assertEqual(row["video_views_3s"], 400.0)
        self.assertEqual(row["video_thruplay"], 120.0)
        self.assertEqual((row["conversions"], row["conversion_value"], row["add_to_carts"]), (3.0, 180.25, 7.0))
        self.assertEqual((row["link_clicks"], row["clicks"], row["date"]), (12.0, 30.0, "2026-03-02"))
        self.assertEqual(row["reported_ctr"], "1.2")
        self.assertEqual(row["conversions_source"], "actions:purchase")

    def test_purchases_wins_over_results_and_source_is_recorded(self):
        both = cm.load_rows([{"Ad name": "a", "Results": "9", "Purchases": "3"}])[0]
        self.assertEqual(both["conversions"], 3.0)
        self.assertEqual(both["conversions_source"], "Purchases")
        results_first = cm.load_rows([{"Results": "9", "Ad name": "a", "Purchases": "3"}])[0]
        self.assertEqual(results_first["conversions"], 3.0)
        self.assertEqual(results_first["conversions_source"], "Purchases")

    def test_results_alone_is_used_but_labelled(self):
        row = cm.load_rows([{"Ad name": "a", "Results": "9"}])[0]
        self.assertEqual((row["conversions"], row["conversions_source"]), (9.0, "Results"))

    def test_blank_purchases_falls_back_to_results(self):
        row = cm.load_rows([{"Ad name": "a", "Purchases": "", "Results": "9"}])[0]
        self.assertEqual((row["conversions"], row["conversions_source"]), (9.0, "Results"))

    def test_conversions_source_survives_aggregation(self):
        ad = cm.aggregate_by_ad(cm.load_rows([{"Ad name": "a", "Purchases": "1", "Results": "5", "Day": "2026-01-01"}]))[0]
        self.assertEqual(ad["conversions_source"], "Purchases")

    def test_meta_computed_columns_are_kept_but_not_used(self):
        row = cm.load_rows([{"Ad name": "a", "CTR (all)": "9.9", "Impressions": "100", "Clicks (all)": "1"}])[0]
        self.assertEqual(cm.compute_metrics(row)["ctr"], 1.0)


class AggregateTest(unittest.TestCase):
    def rows(self):
        return cm.load_rows([
            {"Ad ID": "1", "Ad name": "x", "Day": "2026-03-01", "Impressions": "1000", "Amount spent": "10",
             "3-second video plays": "300", "ThruPlays": "90", "Link clicks": "10"},
            {"Ad ID": "1", "Ad name": "x", "Day": "2026-03-02", "Impressions": "0", "Amount spent": "0",
             "3-second video plays": "0", "ThruPlays": "0", "Link clicks": "0"},
            {"Ad ID": "1", "Ad name": "x", "Day": "2026-03-04", "Impressions": "1000", "Amount spent": "10",
             "3-second video plays": "300", "ThruPlays": "90", "Link clicks": "20"},
            {"Ad ID": "2", "Ad name": "y", "Day": "2026-03-10", "Impressions": "500", "Amount spent": "5",
             "Link clicks": "5"},
        ])

    def test_sums_metrics_and_dates_per_ad(self):
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(self.rows())}
        one = ads["1"]
        self.assertEqual((one["impressions"], one["spend"], one["link_clicks"]), (2000.0, 20.0, 30.0))
        self.assertAlmostEqual(one["hook_rate"], 30.0)
        self.assertAlmostEqual(one["hold_rate"], 30.0)
        self.assertAlmostEqual(one["ctr"], 1.5)
        self.assertEqual((one["first_date"], one["last_date"]), ("2026-03-01", "2026-03-04"))
        self.assertEqual(one["active_days"], 2)

    def test_age_is_measured_to_latest_date_in_data(self):
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(self.rows())}
        self.assertEqual(ads["1"]["age_days"], 9)
        self.assertEqual(ads["2"]["age_days"], 0)

    def test_field_with_no_values_stays_none(self):
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(self.rows())}
        self.assertIsNone(ads["2"]["video_views_3s"])
        self.assertIsNone(ads["2"]["hook_rate"])

    def test_groups_by_name_when_there_is_no_id(self):
        rows = cm.load_rows([{"Ad name": "a", "Impressions": "10"}, {"Ad name": "a", "Impressions": "5"}])
        self.assertEqual(cm.aggregate_by_ad(rows)[0]["impressions"], 15.0)

    def test_row_with_no_identity_is_an_error(self):
        with self.assertRaises(ValueError):
            cm.aggregate_by_ad([{"impressions": 1.0}])


class BaselineTest(unittest.TestCase):
    def ads(self):
        ads = []
        for i, value in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
            ads.append({"format": "static", "ctr": value, "impressions": 5000})
        for value in (9.0, 10.0):
            ads.append({"format": "carousel", "ctr": value, "impressions": 5000})
        ads.append({"format": "static", "ctr": 99.0, "impressions": 10})
        ads.append({"format": "static", "ctr": None, "impressions": 5000})
        return ads

    def test_group_with_five_ads_uses_its_own_quartiles(self):
        base = cm.baseline(self.ads(), "ctr")
        static = base["groups"]["static"]
        self.assertEqual((static["n"], static["median"], static["p25"], static["p75"]), (5, 3.0, 2.0, 4.0))
        self.assertEqual(static["basis"], "group")

    def test_small_group_falls_back_to_account_wide_and_says_so(self):
        base = cm.baseline(self.ads(), "ctr")
        carousel = base["groups"]["carousel"]
        self.assertTrue(carousel["basis"].startswith("account-wide"))
        self.assertEqual(carousel["n_group"], 2)
        self.assertEqual(carousel["median"], base["account"]["median"])
        self.assertEqual(base["account"]["n"], 7)

    def test_low_volume_and_missing_values_are_excluded(self):
        base = cm.baseline(self.ads(), "ctr")
        self.assertNotEqual(base["groups"]["static"]["p75"], 99.0)

    def test_unknown_metric_raises(self):
        with self.assertRaises(KeyError):
            cm.baseline([], "nonsense")

    def test_empty_input_has_no_numbers(self):
        self.assertIsNone(cm.baseline([], "ctr")["account"]["median"])


class FatigueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(FIXTURE)

    def test_fatiguing_fixture_ad_has_falling_ctr_and_rising_frequency(self):
        trend = cm.fatigue_trend(self.rows, make_fixture.SPECIAL["fatiguing"])
        self.assertEqual(trend["status"], "ok")
        self.assertLess(trend["pct_change"], -30)
        self.assertGreater(trend["frequency_pct_change"], 30)

    def test_healthy_fixture_ad_is_not_flagged_as_falling(self):
        trend = cm.fatigue_trend(self.rows, make_fixture.ad_id(1))
        self.assertGreater(trend["pct_change"], -20)

    def test_young_ad_is_insufficient_data(self):
        self.assertEqual(cm.fatigue_trend(self.rows, make_fixture.SPECIAL["young"])["status"], "insufficient_data")

    def test_exactly_two_windows_is_enough(self):
        rows = [{"ad_id": "z", "date": "2026-01-%02d" % d, "impressions": 100.0, "link_clicks": 2.0 if d <= 6 else 1.0}
                for d in range(1, 13)]
        trend = cm.fatigue_trend(rows, "z")
        self.assertEqual(trend["status"], "ok")
        self.assertAlmostEqual(trend["pct_change"], -50.0)
        self.assertEqual(cm.fatigue_trend(rows[:11], "z")["status"], "insufficient_data")

    def test_other_ads_rows_are_ignored(self):
        self.assertEqual(cm.fatigue_trend(self.rows, "no-such-ad")["status"], "insufficient_data")


class ParseNameTest(unittest.TestCase):
    def test_pipe_separated(self):
        parsed = cm.parse_name("durability-test | UGC-Video | creator-01 | BAU | trail-boot | lofi | 2026-03-01")
        self.assertEqual(parsed["concept"], "durability-test")
        self.assertEqual((parsed["format"], parsed["ad_type"]), ("ugc-video", "bau"))
        self.assertEqual(parsed["launch_date"], "2026-03-01")

    def test_underscore_separated(self):
        parsed = cm.parse_name("a_static_house_promo_tent-2p_polished_2026-03-01")
        self.assertEqual(parsed["product"], "tent-2p")

    def test_custom_pattern(self):
        self.assertEqual(cm.parse_name("a | b", pattern=["concept", "format"]), {"concept": "a", "format": "b"})

    def test_non_matching_names_give_empty_dict(self):
        for name in (None, "", "plain name", "a | b | c"):
            self.assertEqual(cm.parse_name(name), {}, name)


class FixtureAndCliTest(unittest.TestCase):
    def test_fixture_shape(self):
        rows = cm.load_rows(FIXTURE)
        ads = cm.aggregate_by_ad(rows)
        self.assertEqual(len(ads), 30)
        self.assertEqual(len({r["date"] for r in rows}), 30)
        self.assertEqual({a["format"] for a in ads}, {"static", "carousel", "ugc-video", "founder-video", "partnership"})
        self.assertEqual({a["ad_type"] for a in ads}, {"bau", "promo", "launch"})

    def test_fixture_special_ads(self):
        ads = {a["ad_id"]: a for a in cm.aggregate_by_ad(cm.load_rows(FIXTURE))}
        self.assertLess(ads[make_fixture.SPECIAL["young"]]["age_days"], 5)
        self.assertIsNone(ads[make_fixture.SPECIAL["no_thruplay"]]["video_thruplay"])
        self.assertIsNotNone(ads[make_fixture.SPECIAL["no_thruplay"]]["hook_rate"])
        self.assertIsNone(ads[make_fixture.SPECIAL["no_thruplay"]]["hold_rate"])
        never = ads[make_fixture.SPECIAL["never_worked"]]
        median_ctr = sorted(a["ctr"] for a in ads.values())[15]
        self.assertLess(never["ctr"], median_ctr / 3)

    def test_fixture_is_deterministic_and_checked_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "f.csv"
            make_fixture.write(out, 7)
            self.assertEqual(out.read_text(), FIXTURE.read_text())

    def test_cli_prints_table_with_the_three_special_ads(self):
        script = ROOT / "skills" / "creative-context" / "scripts" / "creative_metrics.py"
        done = subprocess.run([sys.executable, str(script), str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = done.stdout
        self.assertIn("n/a (missing video_thruplay)", out)
        self.assertIn("young(3d)", out)
        fatigue_line = next(l for l in out.splitlines() if l.startswith(make_fixture.SPECIAL["fatiguing"]))
        self.assertIn("-5", fatigue_line)

    def test_cli_json(self):
        script = ROOT / "shared" / "creative_metrics.py"
        done = subprocess.run([sys.executable, str(script), str(FIXTURE), "--json"], capture_output=True, text=True)
        import json
        self.assertEqual(len(json.loads(done.stdout)), 30)


class ConnectorFieldsTest(unittest.TestCase):
    def test_derivation_needs_a_positive_cost_per_view(self):
        zero = cm.load_rows([{"ad_name": "a", "spend": 10, "cost_per_action_type:video_view": 0}])[0]
        self.assertIsNone(zero.get("video_views_3s"))
        self.assertIsNone(cm.compute_metrics(zero)["hook_rate"])

    def test_aggregation_sums_derived_plays_across_days(self):
        rows = cm.load_rows([
            {"ad_name": "a", "date_start": "2026-03-01", "spend": 10, "impressions": 1000,
             "cost_per_action_type:video_view": {"value": "0.05", "unit": "USD"}},
            {"ad_name": "a", "date_start": "2026-03-02", "spend": 20, "impressions": 1000,
             "cost_per_action_type:video_view": {"value": "0.04", "unit": "USD"}}])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertAlmostEqual(ad["video_views_3s"], 10 / 0.05 + 20 / 0.04)
        self.assertTrue(ad["video_views_3s_source"].startswith("derived"))

    def test_csv_columns_still_read_as_before(self):
        row = cm.load_rows([{"Ad name": "a", "Amount spent (USD)": "1,200.50", "Purchases": "3", "Results": "9"}])[0]
        self.assertEqual((row["spend"], row["conversions"], row["conversions_source"]), (1200.5, 3.0, "Purchases"))

    def test_rows_key_is_read_from_a_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text('{"rows": [{"ad_name": "a", "spend": 4}]}')
            self.assertEqual(cm.load_rows(str(path))[0]["spend"], 4.0)


if __name__ == "__main__":
    unittest.main()
