#!/usr/bin/env python3
"""Can this account power a test of a copy change, and how long would it take?

Usage: python3 power.py ads.csv --metric ctr --mde 18 --daily-budget 300 --max-days 21
                        [--arms 2] [--alpha 0.05] [--power 0.8] [--currency USD] [--json]

Standard library only. The baseline rate is this account's own pooled rate for the metric (after --where, so
--where format=ugc-video sizes the test on one format's baseline). From it the script works out how many
denominator units (impressions for ctr, clicks for cvr) each arm needs for a two-sided two-proportion test to
see a relative change of --mde percent, how many days the daily budget takes to deliver them, and whether that
fits --max-days. If it does not, it says the smallest change that would fit, the budget that would fit, and
the other way out. More than two arms use a Bonferroni split of alpha across the variant-to-control
comparisons. --alpha (0.05) and --power (0.8) are a statistical convention, not a benchmark; --mde,
--daily-budget, --max-days and --arms are yours to set from your own account and appetite. Missing counts
are "n/a (missing <field>)", never 0.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

METRICS = ("hook_rate", "hold_rate", "video_completion_rate", "ctr", "cvr", "add_to_cart_rate",
           "landing_page_view_rate", "cart_to_checkout_rate")
EXPORT_COLUMNS = {
    "video_views_3s": "3-second video plays", "video_thruplay": "ThruPlays", "impressions": "Impressions",
    "link_clicks": "Link clicks", "clicks": "Clicks (all)", "conversions": "Purchases",
    "add_to_carts": "Adds to cart", "landing_page_views": "Landing page views",
    "checkouts": "Checkouts initiated", "spend": "Amount spent",
}
NO_CURRENCY = "currency not stated"
STOPPING_RULE = ("Fixed horizon: decide once, at the planned sample. Do not stop early when one arm looks ahead, "
                 "and do not extend a test that missed: both inflate false wins. Split budget evenly, change one "
                 "thing, and keep the other settings the same.")
HIGHER_FUNNEL = "or test on a higher-funnel metric with more volume (e.g. ctr instead of cvr)"


def sample_per_arm(p1: float, p2: float, alpha: float, power: float) -> int:
    """Denominator units each arm needs for a two-sided two-proportion test of p1 against p2."""
    z = NormalDist().inv_cdf
    pbar = (p1 + p2) / 2
    spread = z(1 - alpha / 2) * math.sqrt(2 * pbar * (1 - pbar)) + z(power) * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(spread ** 2 / (p2 - p1) ** 2)


def smallest_detectable_mde(p1: float, capacity: float, alpha: float, power: float) -> Optional[float]:
    """Smallest relative change (percent) whose sample fits `capacity` units per arm; None when none does."""
    low, high = p1, 1 - 1e-9
    if sample_per_arm(p1, high, alpha, power) > capacity:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if mid > p1 and sample_per_arm(p1, mid, alpha, power) <= capacity:
            high = mid
        else:
            low = mid
    return (high / p1 - 1) * 100


def _field(total: Dict[str, Any], fields: Sequence[str]) -> str:
    return next((f for f in fields if total.get(f) is not None), fields[0])


def pooled_baseline(rows: Sequence[Dict[str, Any]], metric: str, key_map: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Pooled counts for the metric over every ad that has both its operands and a spend; ValueError if none."""
    ads = cm.aggregate_by_ad(rows, key_map)
    usable = [a for a in ads if cm.describe_missing(a, metric) is None and a.get("spend") is not None]
    if not usable:
        total = {f: sum(a[f] for a in ads if a.get(f) is not None) if any(a.get(f) is not None for a in ads) else None
                 for f in cm.NUMERIC_FIELDS}
        reason = cm.describe_missing(total, metric) or "missing spend"
        fields = reason.replace("missing ", "").split(" or ")
        columns = " or ".join(EXPORT_COLUMNS.get(f, f) for f in fields)
        raise ValueError("n/a (%s): add the %s column to the export" % (reason, columns))
    total = {f: sum(a[f] for a in usable if a.get(f) is not None) if any(a.get(f) is not None for a in usable) else None
             for f in cm.NUMERIC_FIELDS}
    num, den = cm.rate_counts(total, metric)
    num_fields, den_fields, _ = cm.METRICS[metric]
    if not den or not total["spend"]:
        raise ValueError("n/a (zero %s or spend): nothing to size a test from" % _field(total, den_fields))
    return {"numerator": num, "denominator": den, "num_field": _field(total, num_fields),
            "den_field": _field(total, den_fields), "spend": total["spend"]}


def money(amount: float, currency: str) -> str:
    text = "{:,.0f}".format(amount)
    return "%s (%s)" % (text, currency) if currency == NO_CURRENCY else "%s %s" % (text, currency)


def plan(rows: Sequence[Dict[str, Any]], key_map: Optional[Dict[str, str]], metric: str, mde: float,
         daily_budget: float, max_days: int, arms: int, alpha: float, power: float) -> Dict[str, Any]:
    """The test size, duration and budget, with the options when it does not fit."""
    if metric not in METRICS:
        raise ValueError("--metric must be one of: %s" % ", ".join(METRICS))
    if mde <= 0 or daily_budget <= 0 or max_days < 1 or arms < 2 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("--mde, --daily-budget and --max-days must be positive, --arms at least 2, "
                         "--alpha and --power between 0 and 1")
    base = pooled_baseline(rows, metric, key_map)
    p1 = base["numerator"] / base["denominator"]
    if p1 <= 0 or p1 >= 1:
        raise ValueError("no variation to test against: the account's %s is %s" % (metric, "0" if p1 <= 0 else "1"))
    p2 = p1 * (1 + mde / 100)
    if p2 >= 1:
        raise ValueError("an increase of %s%% takes %s to 100%% or beyond: choose a smaller --mde" % (mde, metric))
    volume = base["denominator"] / base["spend"]
    adjusted = alpha / (arms - 1)
    n = sample_per_arm(p1, p2, adjusted, power)
    daily_per_arm = daily_budget / arms * volume
    days = math.ceil(n / daily_per_arm)
    capacity = max_days * daily_per_arm
    smallest = smallest_detectable_mde(p1, capacity, adjusted, power)
    return {
        "settings": {"metric": metric, "mde_percent": mde, "daily_budget": daily_budget, "max_days": max_days,
                     "arms": arms, "alpha": alpha, "alpha_per_comparison": adjusted, "power": power},
        "baseline": {"metric": metric, "rate": p1, "numerator": base["numerator"],
                     "denominator": base["denominator"], "num_field": base["num_field"],
                     "den_field": base["den_field"], "volume_per_spend": volume},
        "target_rate": p2, "n_per_arm": n, "daily_per_arm": daily_per_arm, "days_needed": days,
        "total_budget": days * daily_budget, "powered": days <= max_days,
        "smallest_detectable_mde": smallest,
        "budget_to_fit": n * arms / (volume * max_days),
        "stopping_rule": STOPPING_RULE,
    }


def render(result: Dict[str, Any], currency: str) -> str:
    s, b = result["settings"], result["baseline"]
    days, per_day = result["days_needed"], money(s["daily_budget"], currency)
    if result["powered"]:
        lines = ["This account can power the test: about %d %s at %s/day, %s in all."
                 % (days, "day" if days == 1 else "days", per_day, money(result["total_budget"], currency))]
    else:
        lines = ["This account cannot power this test within %d days: it needs about %d days." % (s["max_days"], days),
                 "Options:"]
        smallest = result["smallest_detectable_mde"]
        lines.append("- Accept a bigger change: the smallest relative change detectable in %d days is %s."
                     % (s["max_days"], "%.1f%%" % smallest if smallest is not None else "n/a (no change below 100% fits)"))
        lines.append("- Spend more: about %s/day would fit %d days." % (money(result["budget_to_fit"], currency), s["max_days"]))
        lines.append("- " + HIGHER_FUNNEL[0].upper() + HIGHER_FUNNEL[1:] + ".")
    lines += [
        "",
        "Inputs and working:",
        "- Baseline %s: %.4f (%s %s of %s %s, pooled over this account's rows)"
        % (b["metric"], b["rate"], "{:,.0f}".format(b["numerator"]), b["num_field"],
           "{:,.0f}".format(b["denominator"]), b["den_field"]),
        "- Volume: %.2f %s per unit of spend" % (b["volume_per_spend"], b["den_field"]),
        "- Smallest change to detect: %s%% relative, so %.4f becomes %.4f" % (s["mde_percent"], b["rate"], result["target_rate"]),
        "- Arms: %d; alpha %s two-sided%s; power %s (a statistical convention, not a benchmark)"
        % (s["arms"], s["alpha"], "" if s["arms"] == 2 else ", split to %.4g per comparison (Bonferroni)" % s["alpha_per_comparison"],
           s["power"]),
        "- Needed: %s %s per arm; each arm gets about %s a day" % ("{:,}".format(result["n_per_arm"]), b["den_field"],
                                                                  "{:,.0f}".format(result["daily_per_arm"])),
        "- Budget: %s/day, longest run %d days" % (per_day, s["max_days"]),
        "",
        result["stopping_rule"],
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Size a copy test from the account's own baseline.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--metric", required=True, help="rate to test: " + ", ".join(METRICS))
    parser.add_argument("--mde", type=float, required=True,
                        help="smallest relative change worth detecting, in percent of the baseline (18 means 18%% higher)")
    parser.add_argument("--daily-budget", type=float, required=True, help="money per day for the whole test")
    parser.add_argument("--max-days", type=int, required=True, help="the longest you will run the test")
    parser.add_argument("--arms", type=int, default=2, help="control plus variants, at least 2 (default 2)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="false-win rate, two-sided (default 0.05: a statistical convention, not a benchmark)")
    parser.add_argument("--power", type=float, default=0.8,
                        help="chance of seeing a real change of --mde (default 0.8: a statistical convention, not a benchmark)")
    parser.add_argument("--currency", help="currency code (default: read from the export, else 'currency not stated')")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        result = plan(rows, key_map, args.metric, args.mde, args.daily_budget, args.max_days, args.arms,
                      args.alpha, args.power)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    currency = args.currency or cm.detect_currency(args.path) or NO_CURRENCY
    result["settings"]["currency"] = currency
    result["run_notes"] = run_notes
    print(json.dumps(result, indent=2) if args.json else "\n".join(run_notes + [render(result, currency)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
