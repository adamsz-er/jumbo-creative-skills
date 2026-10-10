#!/usr/bin/env python3
"""Is a drop (or a weak result) the creative or the site? One call per ad, and one for the whole account.

Usage: python3 funnel.py ads.csv [--ad 123 --ad name] [--group-by format] [--window 6] [--min-change 8]
                         [--min-impressions 1000] [--z 1.96] [--json]

Standard library only. The decision rule lives in creative_metrics.funnel_read and this script only reports
it: each funnel step (hook rate, hold rate, ctr, then landing page view rate, add to cart rate, cart to
checkout rate, cvr) is weak when it fell since the ad's first delivery days or sits in the bottom quartile of
the ad's own group. A weak site step with healthy attention is "site"; the reverse is "creative". The
account-wide read pools every ad per calendar day and compares the account's first --window days with its
last, so a sitewide problem (checkout, payment, shipping, stock) shows here first. A step with no data is
named with the export column that adds it, never read as fine. --window, --min-change and --min-impressions
are arbitrary defaults: set them from your own account. --z is the common two-sided 95% convention from
statistics, not a benchmark.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

CALL_ORDER = ("site", "both", "creative", "neither", "unjudged", "unreadable")
EXPORT_COLUMNS = {
    "landing_page_view_rate": ["Landing page views"],
    "add_to_cart_rate": ["Adds to cart"],
    "cart_to_checkout_rate": ["Checkouts initiated", "Adds to cart"],
    "cvr": ["Purchases"],
}
ACCOUNT_LABEL = "account-wide: a sitewide problem (checkout, payment, shipping, stock) shows here first"
CHECKLIST = "For a site call, work through references/page-checklist.md before changing the ad."


def _key(ad: Dict[str, Any]) -> Optional[str]:
    return ad.get("ad_id") or ad.get("ad_name")


def _label(metric: str) -> str:
    return metric.replace("_", " ")


def _falling(step: Dict[str, Any], min_change: float, z: float) -> bool:
    """Whether a weak step is weak because it fell (as funnel_read judges it), not only because it is low."""
    return bool(step["weak"] and step["change_pct"] is not None and step["change_pct"] <= -min_change
                and step["trend_z"] is not None and step["trend_z"] <= -z)


def _columns(metrics: Sequence[str]) -> str:
    names: List[str] = []
    for metric in metrics:
        names += [c for c in EXPORT_COLUMNS.get(metric, []) if c not in names]
    return " and ".join('"%s"' % n for n in names)


def select_ads(ads: Sequence[Dict[str, Any]], wanted: Sequence[str]) -> List[Dict[str, Any]]:
    """The ads asked for by id or name (every ad when none are named); ValueError on one that is not in the data."""
    if not wanted:
        return list(ads)
    chosen = []
    for item in wanted:
        match = [a for a in ads if item in (a.get("ad_id"), a.get("ad_name"))]
        if not match:
            raise ValueError("--ad %s is not in the data" % item)
        chosen += [a for a in match if a not in chosen]
    return chosen


def _window_sums(rows: Sequence[Dict[str, Any]], window: int) -> Optional[Dict[str, Dict[str, Any]]]:
    """The account's first and last `window` calendar days, every ad's rows pooled per day."""
    days: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        day = cm._parse_date(row.get("date"))
        if day and (row.get("impressions") or 0) > 0:
            days.setdefault(day, []).append(row)
    ordered = [days[d] for d in sorted(days)]
    if len(ordered) < 2 * window:
        return None
    out = {}
    for name, chosen in (("first", ordered[:window]), ("last", ordered[-window:])):
        total: Dict[str, Any] = {}
        for field in cm.NUMERIC_FIELDS:
            values = [r[field] for day in chosen for r in day if r.get(field) is not None]
            total[field] = sum(values) if values else None
        out[name] = total
    return out


def account_read(rows: Sequence[Dict[str, Any]], window: int, min_change: float, z: float) -> Dict[str, Any]:
    """The funnel read for the whole account, by the same rule funnel_read applies to one ad."""
    windows = _window_sums(rows, window)
    whole = cm.compute_metrics(cm._sum_rows(rows))
    steps = []
    for metric in cm.ATTENTION_STEPS + cm.SITE_STEPS:
        first = cm.compute_metrics(windows["first"])[metric] if windows else None
        last = cm.compute_metrics(windows["last"])[metric] if windows else None
        change = trend_z = None
        if first and last is not None:
            change = (last - first) / first * 100
            trend_z = cm.proportion_z(*cm.rate_counts(windows["first"], metric), *cm.rate_counts(windows["last"], metric))
        falling = change is not None and change <= -min_change and trend_z is not None and trend_z <= -z
        steps.append({"metric": metric, "side": "attention" if metric in cm.ATTENTION_STEPS else "site",
                      "first": first, "last": last, "change_pct": change, "trend_z": trend_z,
                      "readable": whole[metric] is not None, "judged": trend_z is not None, "weak": falling,
                      "why": "down %.0f%% from the account's first %d days to its last" % (-change, window) if falling else None})
    attention = [s for s in steps if s["side"] == "attention" and s["weak"]]
    site = [s for s in steps if s["side"] == "site" and s["weak"]]
    judged = {side: any(s["judged"] for s in steps if s["side"] == side) for side in ("attention", "site")}
    if not any(s["readable"] for s in steps if s["side"] == "site"):
        call = "unreadable"
    elif site and attention:
        call = "both"
    elif site and judged["attention"]:
        call = "site"
    elif attention and judged["site"]:
        call = "creative"
    elif not site and not attention and judged["attention"] and judged["site"]:
        call = "neither"
    else:
        call = "unjudged"
    return {"label": ACCOUNT_LABEL, "call": call, "reason": cm.FUNNEL_CALLS[call],
            "weak_steps": [s["metric"] for s in attention + site], "steps": steps,
            "trend_readable": windows is not None}


def build_funnel(rows: Sequence[Dict[str, Any]], key_map: Optional[Dict[str, str]], wanted: Sequence[str],
                 group_by: Sequence[str], window: int, min_change: float, min_impressions: int,
                 z: float) -> Dict[str, Any]:
    ads = cm.aggregate_by_ad(rows, key_map)
    group = cm.resolve_group_by(ads, group_by)
    chosen = select_ads(ads, wanted)
    judged = [a for a in chosen if (a.get("impressions") or 0) >= min_impressions]
    too_little = [{"ad": _key(a), "ad_name": a.get("ad_name"), "impressions": a.get("impressions"),
                   "note": "too little delivery to judge (under %d impressions)" % min_impressions}
                  for a in chosen if a not in judged]
    reads = []
    for ad in judged:
        read = cm.funnel_read(rows, ad, ads, group, window, min_change, min_impressions, z)
        read.update(ad_name=ad.get("ad_name"), spend=ad.get("spend"), concept=ad.get("concept"), format=ad.get("format"))
        reads.append(read)
    reads.sort(key=lambda r: (CALL_ORDER.index(r["call"]),
                              not any(_falling(s, min_change, z) for s in r["steps"]), -(r["spend"] or 0)))
    missing: Dict[str, List[str]] = {}
    for read in reads:
        for metric in read["missing_site_steps"]:
            missing[metric] = EXPORT_COLUMNS.get(metric, [])
    return {"settings": {"window": window, "min_change": min_change, "min_impressions": min_impressions,
                         "group_by": list(group), "z": z},
            "window": cm.data_window(rows), "account": account_read(rows, window, min_change, z),
            "ads": reads, "too_little_delivery": too_little,
            "counts": {c: sum(1 for r in reads if r["call"] == c) for c in CALL_ORDER},
            "missing_columns": missing}


def _lead_sentence(read: Dict[str, Any], settings: Dict[str, Any]) -> str:
    site = [s for s in read["steps"] if s["side"] == "site" and s["weak"]]
    ctr = next(s for s in read["steps"] if s["metric"] == "ctr")
    earns = "the ad still earns clicks (ctr holds)" if ctr["readable"] else "the ad's attention steps hold"
    parts = []
    for step in site:
        if _falling(step, settings["min_change"], settings["z"]):
            parts.append("%s fell %.0f%% since its first %d delivery days" % (_label(step["metric"]), -step["change_pct"], settings["window"]))
        else:
            parts.append("%s is in the bottom quartile of its group" % _label(step["metric"]))
    return "%s: %s while %s: check the page before touching the creative." % (
        read.get("ad_name") or read["ad"], earns, " and ".join(parts))


def render(result: Dict[str, Any]) -> str:
    counts, window = result["counts"], result["settings"]["window"]
    judged = sum(counts.values())
    if not judged and not result["too_little_delivery"]:
        return "Funnel diagnosis: no ads to judge."
    out = ["Funnel diagnosis: %d ads judged: %s." % (judged, ", ".join("%d %s" % (counts[c], c) for c in CALL_ORDER))]
    first_site = next((r for r in result["ads"] if r["call"] == "site"), None)
    out.append(_lead_sentence(first_site, result["settings"]) if first_site else "No ad points at the site on its own.")
    account = result["account"]
    out += ["", "%s: %s" % (ACCOUNT_LABEL, account["call"]), "  " + account["reason"]]
    if not account["trend_readable"]:
        out.append("  n/a (fewer than twice the window (2 x %d delivery days): the account's start and end cannot be compared)" % window)
    for step in account["steps"]:
        if step["weak"]:
            out.append("  %s: %s" % (_label(step["metric"]), step["why"]))
    unread = [s["metric"] for s in account["steps"] if s["side"] == "site" and not s["readable"]]
    if unread:
        out.append("  could not be read: %s; add the export column %s" % (", ".join(_label(m) for m in unread), _columns(unread)))
    out += ["", "Per ad (site, both, creative, neither, unjudged, unreadable; within a call, ads with a step that fell first, then by spend):"]
    for read in result["ads"]:
        out.append("%s (%s): %s" % (read.get("ad_name") or read["ad"], read["ad"], read["call"]))
        out.append("  " + read["reason"])
        for step in read["steps"]:
            if step["weak"]:
                out.append("  weak: %s, %s" % (_label(step["metric"]), step["why"]))
        for step in read["steps"]:
            if not step["readable"]:
                out.append("  %s: %s%s" % (_label(step["metric"]), step["note"],
                                           "; add the export column %s" % _columns([step["metric"]])
                                           if step["metric"] in EXPORT_COLUMNS else ""))
        if not read["trend_readable"]:
            out.append("  n/a (fewer than twice the window (2 x %d delivery days): the ad's start and end cannot be compared)" % window)
    if result["too_little_delivery"]:
        out += ["", "Too little delivery to judge:"]
        out += ["  %s (%s): %s" % (t["ad_name"] or t["ad"], t["ad"], t["note"]) for t in result["too_little_delivery"]]
    if counts["site"] or counts["both"]:
        out += ["", CHECKLIST]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Decide whether a drop is the creative or the site.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--ad", action="append", default=[],
                        help="ad id or name to judge (repeatable; default: every ad with enough delivery)")
    parser.add_argument("--group-by", default="format",
                        help="comma-separated columns that define 'the same kind of ad' (default: format)")
    parser.add_argument("--window", type=int, default=6,
                        help="delivery days compared at the start and end of an ad's life (arbitrary default)")
    parser.add_argument("--min-change", type=float, default=8.0,
                        help="percent a step must fall to count as falling (arbitrary default)")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are listed as too little delivery to judge (arbitrary default)")
    parser.add_argument("--z", type=float, default=cm.FUNNEL_Z,
                        help="standard errors a move must clear (default %(default)s: the common two-sided 95%% "
                             "convention from statistics, not a benchmark)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        result = build_funnel(rows, key_map, args.ad, [g.strip() for g in args.group_by.split(",") if g.strip()],
                              args.window, args.min_change, args.min_impressions, args.z)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["run_notes"] = run_notes
    print(json.dumps(result, indent=2) if args.json else "\n".join(run_notes + [render(result)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
