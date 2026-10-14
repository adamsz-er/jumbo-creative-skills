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
    """Eight static ads with the same spend, impressions and link clicks every day, so only the after-click steps differ."""
    out = []
    for ad, (add, bought) in enumerate(zip(adds, purchases)):
        for day in range(days):
            out.append({"Day": "2026-04-%02d" % (day + 1), "Ad name": "ad-%d | static | house | bau" % ad, "Ad ID": "9000%d" % ad,
                        "Amount spent (USD)": 100, "Impressions": 20000, "Link clicks": 300, "Adds to cart": add, "Purchases": bought})
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


if __name__ == "__main__":
    unittest.main()
