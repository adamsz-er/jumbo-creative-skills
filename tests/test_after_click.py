import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "creative-grader" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "funnel-diagnosis" / "scripts"))

import creative_metrics as cm  # noqa: E402
import funnel  # noqa: E402
import grade  # noqa: E402

TARGET = "90003"


def rows(adds, purchases, days):
    return cm.load_rows(rows_raw(adds, purchases, days))


def rows_raw(adds, purchases, days):
    """Eight static ads with the same spend, impressions and link clicks every day, so only the after-click steps differ."""
    out = []
    for ad, (add, bought) in enumerate(zip(adds, purchases)):
        for day in range(days):
            out.append({"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad, "Ad ID": "9000%d" % ad,
                        "Amount spent (USD)": 100, "Impressions": 20000, "Link clicks": 300, "Adds to cart": add, "Purchases": bought})
    return out


def daily(per_ad, days=20, adds=100):
    """Eight static ads; `per_ad[i](day)` is ad i's purchases that day, with clicks and adds to cart flat."""
    out = []
    for ad, bought in enumerate(per_ad):
        for day in range(days):
            out.append({"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad, "Ad ID": "9000%d" % ad,
                        "Amount spent (USD)": 100, "Impressions": 20000, "Link clicks": 300, "Adds to cart": adds, "Purchases": bought(day)})
    return cm.load_rows(out)


def reads(data):
    graded = {str(e["ad"]): e for e in grade.grade_ads(data)}
    result = funnel.build_funnel(data, None, [], [], 6, 8.0, 1000, cm.FUNNEL_Z)
    return graded, {str(r["ad"]): r for r in result["ads"]}, funnel.render(result)


class AfterClickAgreementTest(unittest.TestCase):
    """creative-grader and funnel-diagnosis judge an ad's after-click steps (add to cart rate, cart to purchase rate) by one rule."""

    def test_a_significantly_low_cart_to_purchase_rate_is_a_checkout_read_in_both(self):
        graded, funnels, text = reads(rows([88, 89, 90, 91, 92, 93, 94, 95], [30, 30, 31, 18, 31, 30, 31, 30], 20))
        diagnosis = graded[TARGET]["diagnosis"]
        self.assertEqual(graded[TARGET]["grades"]["add_to_cart_rate"]["band"], cm.BAND_MID)
        self.assertEqual((diagnosis["step"], diagnosis["metrics"]), ("post-click", ["cart_to_purchase_rate"]))
        self.assertIn("checkout, price and shipping", diagnosis["action"])
        self.assertEqual(funnels[TARGET]["call"], "site")
        self.assertIn("cart_to_purchase_rate", funnels[TARGET]["weak_steps"])
        self.assertIn("checkout, price and shipping", funnels[TARGET]["reason"])
        self.assertNotIn("No ad points at the site", text)

    def test_a_bottom_quartile_add_to_cart_rate_within_noise_is_flagged_by_neither(self):
        graded, funnels, _ = reads(rows([90, 91, 92, 89, 93, 94, 95, 96], [30] * 8, 4))
        self.assertEqual(graded[TARGET]["grades"]["add_to_cart_rate"]["band"], cm.BAND_BOTTOM)
        self.assertNotEqual(graded[TARGET]["diagnosis"]["step"], "post-click")
        self.assertNotIn("add_to_cart_rate", graded[TARGET]["diagnosis"]["also_weak"])
        self.assertNotIn("add_to_cart_rate", funnels[TARGET]["weak_steps"])
        self.assertFalse(graded[TARGET]["grades"]["add_to_cart_rate"]["significant"])


    def test_a_falling_cart_to_purchase_rate_reads_as_falling_not_as_low(self):
        steady = [lambda d, n=n: 28 + n for n in range(7)]
        data = daily(steady[:3] + [lambda d: 42 if d < 10 else 20] + steady[3:])
        graded, funnels, _ = reads(data)
        step = next(s for s in funnels[TARGET]["steps"] if s["metric"] == "cart_to_purchase_rate")
        self.assertTrue(step["weak"])
        self.assertRegex(step["why"], r"^down \d+% since its first 6 delivery days$")
        self.assertNotIn("cart_to_purchase_rate", graded[TARGET]["diagnosis"]["metrics"] + graded[TARGET]["diagnosis"]["also_weak"])

    def test_the_funnels_low_after_click_steps_are_the_graders_on_every_acme_ad(self):
        data = cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv"))
        graded, funnels, _ = reads(data)
        for ad, entry in graded.items():
            mine = {m for m in entry["diagnosis"]["metrics"] + entry["diagnosis"]["also_weak"] if m in cm.AFTER_CLICK_STEPS}
            theirs = {s["metric"] for s in funnels[ad]["steps"] if s["metric"] in cm.AFTER_CLICK_STEPS and "bottom quartile" in (s["why"] or "")}
            self.assertEqual(mine, theirs, ad)

    def test_a_gap_that_cannot_be_tested_is_unknown_in_both_never_weak_or_healthy(self):
        data = daily([lambda d, n=n: 30 + n for n in range(3)] + [lambda d: 8] + [lambda d, n=n: 33 + n for n in range(4)], adds=20)
        graded, funnels, text = reads(data)
        grade_band = graded[TARGET]["grades"]["cart_to_purchase_rate"]["band"]
        self.assertEqual(grade_band, "not graded (bottom quartile of its group, but the gap can't be tested: its group has more purchases than "
                                     "adds to cart)")
        self.assertNotEqual(graded[TARGET]["diagnosis"]["step"], "post-click")
        self.assertTrue(any("cart_to_purchase_rate" in s for s in graded[TARGET]["diagnosis"]["skipped"]))
        step = next(s for s in funnels[TARGET]["steps"] if s["metric"] == "cart_to_purchase_rate")
        self.assertFalse(step["weak"])
        self.assertIn("more purchases than adds to cart", step["untested"])
        self.assertIn("could not test: cart to purchase rate is bottom quartile of its group, but the gap can't be tested: its group has "
                      "more purchases than adds to cart", text)
        self.assertEqual(funnels[TARGET]["call"], "untested")
        self.assertEqual(funnels[TARGET]["reason"], "no step is weak or falling, but cart to purchase rate could not be tested (its group "
                                                    "has more purchases than adds to cart), so the funnel is not known to be fine")
        self.assertNotIn("reads normally", graded[TARGET]["diagnosis"]["action"])
        self.assertIn("cart to purchase rate could not be tested (its group has more purchases than adds to cart), so the funnel is "
                      "not known to read normally", graded[TARGET]["diagnosis"]["action"])

    def test_the_significance_test_pools_only_the_peers_the_band_was_read_against(self):
        rows = [dict(r) for r in rows_raw([88, 89, 90, 91, 92, 93, 94, 95], [30, 30, 31, 27, 31, 30, 31, 30], 20)]
        rows += [{"Day": "2026-04-01", "Ad name": "tiny | static | house | bau", "Ad ID": "90009", "Amount spent (USD)": 5,
                  "Impressions": 500, "Link clicks": 300, "Adds to cart": 900, "Purchases": 30}]
        data = cm.load_rows(rows)
        ads = cm.aggregate_by_ad(data)
        target = next(a for a in ads if str(a["ad_id"]) == TARGET)
        grade_ = cm.grade_in_objective(target, ads, "cart_to_purchase_rate", ("format",), 1000)
        self.assertEqual(grade_["band"], cm.BAND_BOTTOM)
        peers = [a for a in ads if a is not target and (a.get("impressions") or 0) >= 1000]
        pooled = {f: sum(a[f] for a in peers if a.get(f) is not None) for f in ("conversions", "add_to_carts")}
        expected = cm.proportion_z(pooled["conversions"], pooled["add_to_carts"], target["conversions"], target["add_to_carts"])
        self.assertAlmostEqual(cm.below_group(target, ads, "cart_to_purchase_rate", grade_)[0], expected)


if __name__ == "__main__":
    unittest.main()
