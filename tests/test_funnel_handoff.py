"""keep-or-kill hands a would-be pause to the site when the ad's own funnel says the page is the problem."""
import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "keep-or-kill" / "scripts"))

import creative_metrics as cm  # noqa: E402
import verdicts  # noqa: E402

DAYS = 18
WEAK = "120000000099"


def _rows(weak_ad):
    """Seven static ads; the weak one sells little. `weak_ad` sets what is wrong with it: its page or its click."""
    rows = []
    start = dt.date(2026, 3, 1)
    for index in range(7):
        ad_id = WEAK if index == 0 else "1200000000%02d" % (index + 1)
        for day in range(DAYS):
            purchases = 1 if ad_id == WEAK else 5 + index % 3
            mid = 3 if ad_id == WEAK else index  # the weak ad's click rate sits mid-pack, so only its page differs
            link_clicks = 150 + mid * 3
            landing = int(link_clicks * 0.86)
            if ad_id == WEAK and weak_ad == "page":
                landing = int(link_clicks * 0.27)
            if ad_id == WEAK and weak_ad == "click":
                link_clicks = 61
                landing = int(link_clicks * 0.86)
            rows.append({
                "date": (start + dt.timedelta(days=day)).isoformat(), "ad_id": ad_id,
                "ad_name": "offer-%d | static | house | bau | tent | polished | 2026-03-01" % index,
                "spend": 150.0 + index, "impressions": 10000 + mid * 40, "link_clicks": link_clicks,
                "clicks": link_clicks + 40, "landing_page_views": landing, "add_to_carts": 21 + mid,
                "checkouts": 11 + index % 2, "conversions": purchases, "conversion_value": purchases * 96.0,
            })
    return cm.load_rows(rows)


def _verdict(weak_ad, targets=None):
    results = verdicts.judge_ads(_rows(weak_ad), targets=targets if targets is not None else {"cpa": 40})
    return next(r for r in results if r["ad"] == WEAK)


class FunnelHandoffTest(unittest.TestCase):
    def test_a_weak_page_turns_pause_into_check_with_the_reason(self):
        entry = _verdict("page")
        self.assertEqual(entry["verdict_id"], "check_site")
        self.assertEqual(entry["verdict"], "Check before cutting")
        self.assertEqual(entry["funnel"]["call"], "site")
        self.assertIn("landing_page_view_rate", entry["funnel"]["weak_steps"])
        self.assertIn("landing page view rate is bottom quartile of its group", entry["sentence"])
        self.assertNotIn("cvr", entry["sentence"])
        self.assertIn("check the landing page", entry["sentence"].lower())
        self.assertTrue(any("funnel points at the site" in r for r in entry["reasons"]))
        self.assertIsNone(entry["check"])

    def test_a_weak_purchase_rate_alone_never_reads_as_the_site(self):
        read = cm.funnel_read(_rows("none"), next(a for a in cm.aggregate_by_ad(_rows("none")) if a["ad_id"] == WEAK),
                              cm.aggregate_by_ad(_rows("none")))
        cvr = next(s for s in read["steps"] if s["metric"] == "cvr")
        self.assertTrue(cvr["weak"])
        self.assertEqual(cvr["side"], "context")
        self.assertEqual(read["call"], "neither")

    def test_a_weak_click_stays_a_pause(self):
        entry = _verdict("click")
        self.assertEqual(entry["verdict_id"], "pause_never_worked")
        self.assertIn(entry["funnel"]["call"], ("creative", "both"))
        self.assertIsNotNone(entry["check"])

    def test_without_site_fields_the_funnel_is_unreadable_and_the_pause_stands(self):
        rows = [{k: v for k, v in r.items() if k not in ("landing_page_views", "checkouts", "add_to_carts")}
                for r in _rows("page")]
        entry = next(r for r in verdicts.judge_ads(rows, targets={"cpa": 40}) if r["ad"] == WEAK)
        self.assertEqual(entry["verdict_id"], "pause_never_worked")
        self.assertEqual(entry["funnel"]["call"], "unreadable")
        self.assertIn("landing_page_view_rate", entry["funnel"]["missing_site_steps"])

    def test_no_target_still_reads_check_before_cutting_for_another_reason(self):
        entry = _verdict("page", targets={})
        self.assertEqual(entry["verdict_id"], "check_no_target")
        self.assertNotIn("funnel", entry)

    def test_check_site_is_summarised_with_the_checks(self):
        self.assertEqual(verdicts.group_of("check_site"), "check")


class FunnelReadTest(unittest.TestCase):
    def setUp(self):
        self.rows = _rows("page")
        self.ads = cm.aggregate_by_ad(self.rows)
        self.weak = next(a for a in self.ads if a["ad_id"] == WEAK)

    def test_site_call_names_the_weak_step_and_holds_attention(self):
        read = cm.funnel_read(self.rows, self.weak, self.ads)
        self.assertEqual(read["call"], "site")
        self.assertEqual(read["weak_steps"], ["landing_page_view_rate"])
        ctr = next(s for s in read["steps"] if s["metric"] == "ctr")
        self.assertFalse(ctr["weak"])

    def test_missing_steps_are_never_read_as_fine(self):
        read = cm.funnel_read(self.rows, self.weak, self.ads)
        hook = next(s for s in read["steps"] if s["metric"] == "hook_rate")
        self.assertFalse(hook["readable"])
        self.assertFalse(hook["weak"])
        self.assertTrue(hook["note"].startswith("n/a (missing video_views_3s"))

    def test_a_raised_z_calls_fewer_steps_weak(self):
        strict = cm.funnel_read(self.rows, self.weak, self.ads, z=1000.0)
        self.assertEqual(strict["call"], "neither")

    def test_a_falling_page_is_read_from_the_ads_own_start(self):
        rows = _rows("none")
        for row in rows:
            if row["ad_id"] == "120000000004" and row["date"] >= "2026-03-12":
                row["landing_page_views"] = int(row["link_clicks"] * 0.41)
        ads = cm.aggregate_by_ad(rows)
        ad = next(a for a in ads if a["ad_id"] == "120000000004")
        read = cm.funnel_read(rows, ad, ads)
        step = next(s for s in read["steps"] if s["metric"] == "landing_page_view_rate")
        self.assertTrue(step["weak"])
        self.assertIn("since its first 6 delivery days", step["why"])
        self.assertEqual(read["call"], "site")

    def test_proportion_z_refuses_what_is_not_a_proportion(self):
        self.assertIsNone(cm.proportion_z(5, 4, 1, 4))
        self.assertIsNone(cm.proportion_z(None, 4, 1, 4))
        self.assertIsNone(cm.proportion_z(0, 4, 0, 4))
        self.assertLess(cm.proportion_z(50, 100, 20, 100), -1.96)



def _fading_rows(early=32, late=29):
    """As _rows("page"), but the weak ad runs on little delivery while its click rate fades and frequency climbs."""
    rows = []
    start = dt.date(2026, 3, 1)
    for index in range(7):
        ad_id = WEAK if index == 0 else "1200000000%02d" % (index + 1)
        for day in range(DAYS):
            purchases = 1 if ad_id == WEAK else 5 + index % 3
            impressions, link_clicks = 10000 + index * 40, 150 + index * 3
            reach = impressions
            if ad_id == WEAK:
                impressions, link_clicks, reach = 2000, (early if day < 9 else late), 2000 - day * 60
            landing = int(link_clicks * (0.27 if ad_id == WEAK else 0.86))
            rows.append({
                "date": (start + dt.timedelta(days=day)).isoformat(), "ad_id": ad_id,
                "ad_name": "offer-%d | static | house | bau | tent | polished | 2026-03-01" % index,
                "spend": 150.0 + index, "impressions": impressions, "reach": reach, "link_clicks": link_clicks,
                "clicks": link_clicks + 8, "landing_page_views": landing, "add_to_carts": 21 + index,
                "checkouts": 11 + index % 2, "conversions": purchases, "conversion_value": purchases * 96.0,
            })
    return cm.load_rows(rows)


class FatiguedPauseTest(unittest.TestCase):
    def test_a_fatigued_pause_stands_and_names_the_weak_page(self):
        entry = next(r for r in verdicts.judge_ads(_fading_rows(), targets={"cpa": 40}) if r["ad"] == WEAK)
        self.assertEqual(entry["funnel"]["call"], "site")
        self.assertEqual(entry["verdict_id"], "pause_fatigued")
        self.assertTrue(any("fix the page before its replacement goes live" in r for r in entry["reasons"]))
        self.assertFalse(any("no step the ad controls" in r for r in entry["reasons"]))

    def test_a_fatigued_pause_names_the_weak_page_when_the_click_drop_is_clear_too(self):
        entry = next(r for r in verdicts.judge_ads(_fading_rows(40, 20), targets={"cpa": 40}) if r["ad"] == WEAK)
        self.assertEqual(entry["funnel"]["call"], "both")
        self.assertEqual(entry["verdict_id"], "pause_fatigued")
        self.assertTrue(any("fix the page before its replacement goes live" in r for r in entry["reasons"]))

    def test_an_unjudged_funnel_with_a_weak_page_keeps_the_pause_and_says_so(self):
        real = cm.funnel_read

        def unjudged(*args, **kwargs):
            read = real(*args, **kwargs)
            read["call"] = "unjudged"
            return read
        verdicts.cm.funnel_read = unjudged
        try:
            entry = _verdict("page")
        finally:
            verdicts.cm.funnel_read = real
        self.assertEqual(entry["verdict_id"], "pause_never_worked")
        self.assertTrue(any("the ad's own steps could not be judged" in r for r in entry["reasons"]))

    def test_a_never_worked_pause_with_both_sides_weak_does_not_say_the_ad_could_not_be_judged(self):
        real = cm.funnel_read

        def both(*args, **kwargs):
            read = real(*args, **kwargs)
            read["call"] = "both"
            return read
        verdicts.cm.funnel_read = both
        try:
            entry = _verdict("page")
        finally:
            verdicts.cm.funnel_read = real
        self.assertEqual(entry["verdict_id"], "pause_never_worked")
        joined = " ".join(entry["reasons"])
        self.assertIn("both the ad's own steps and a site step are weak", joined)
        self.assertIn("landing page view rate", joined)
        self.assertIn("fix the page before its replacement goes live", joined)
        self.assertNotIn("could not be judged", joined)


if __name__ == "__main__":
    unittest.main()
