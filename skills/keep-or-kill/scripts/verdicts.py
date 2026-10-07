#!/usr/bin/env python3
"""A keep / kill / iterate / scale verdict per ad, with age, a learning flag and fatigue trend.

Usage: python3 verdicts.py ads.csv [--young-days 5] [--window 6] [--min-change 8] [--top-n 3] [--key-map PX=concept] [--json]

Standard library only. Needs daily rows (one row per ad per day) for fatigue.
--young-days, --window, --min-impressions and --min-change are arbitrary
defaults: set them from your own account (how long ads take to stabilise, how
much a week-to-week wobble moves your numbers). --min-change is a materiality
size, not a fatigue benchmark. Every grade is relative to the account's own ads.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

CHECK = ("rule out tracking, site or audience problems first; "
         "only fatigue and never-worked are creative decisions")
V_EARLY = "too early (learning)"
V_NEVER = "kill: never worked"
V_ITERATE = "iterate: refresh the hook or creator, keep the concept"
V_FATIGUED = "kill: fatigued"
V_SCALE = "scale: raise budget in steps"
V_ATTENTION = "keep: check whether it feeds other ads before cutting"
V_KEEP = "keep"
ORDER = (V_SCALE, V_KEEP, V_ATTENTION, V_ITERATE, V_FATIGUED, V_NEVER, V_EARLY)
PAYBACK = ("cpa", "roas")
ATTENTION = ("hook_rate", "ctr")


def _key(ad: Dict[str, Any]) -> Optional[str]:
    return ad.get("ad_id") or ad.get("ad_name")


def _payback(grades: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Collapse cpa and roas bands: bottom if either is bottom, top only if every graded one is top."""
    bands = [g["band"] for g in grades.values() if not g["band"].startswith("not graded")]
    return {"known": bool(bands),
            "bottom": cm.BAND_BOTTOM in bands,
            "top": bool(bands) and all(b == cm.BAND_TOP for b in bands),
            "bands": {m: g["band"] for m, g in grades.items()}}


def _change(trend: Dict[str, Any], field: str = "pct_change") -> Optional[float]:
    return trend.get(field) if trend.get("status") == "ok" else None


def _fatigue(rows, key, window, min_change) -> Dict[str, Any]:
    ctr = cm.fatigue_trend(rows, key, "ctr", window)
    if ctr["status"] != "ok":
        return {"status": "insufficient data", "fatiguing": False, "ctr_change": None,
                "frequency_change": None, "hook_change": None,
                "note": "needs %d delivery days, has %d" % (ctr["needed"], ctr["delivery_days"])}
    hook = cm.fatigue_trend(rows, key, "hook_rate", window)
    ctr_change, freq_change = _change(ctr), _change(ctr, "frequency_pct_change")
    hook_change = _change(hook)
    ctr_down = ctr_change is not None and ctr_change <= -min_change
    freq_up = freq_change is not None and freq_change >= min_change
    hook_down = hook_change is not None and hook_change <= -min_change
    return {"status": "ok", "fatiguing": bool(ctr_down and (freq_up or hook_down)),
            "ctr_change": ctr_change, "frequency_change": freq_change, "hook_change": hook_change,
            "note": None}


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%+.0f%%" % value


def judge_ads(rows: Sequence[Dict[str, Any]], young_days: int = 5, window: int = 6,
              min_impressions: int = 1000, min_change: float = 8.0,
              group_by: Sequence[str] = ("format",),
              key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """One verdict per ad, first matching rule wins, every verdict lists its reasons."""
    ads = cm.aggregate_by_ad(rows, key_map=key_map)
    group_by = cm.resolve_group_by(ads, group_by)
    first_ads = cm.window_aggregate(rows, window, "first", key_map=key_map)
    first_by_key = {_key(a): a for a in first_ads}
    results = []
    for ad in ads:
        key = _key(ad)
        age = ad["age_days"]
        low_volume = (ad.get("impressions") or 0) < min_impressions
        learning = low_volume or (age is not None and age < young_days)
        entry: Dict[str, Any] = {
            "ad": key, "ad_id": ad.get("ad_id"), "ad_name": ad.get("ad_name"),
            "format": ad.get("format"), "spend": ad.get("spend"), "age_days": age,
            "age_basis": ad.get("age_basis"),
            "active_days": ad.get("active_days"), "learning": learning, "check": None,
        }
        if learning:
            why = ("under %d impressions" % min_impressions) if low_volume else \
                  "%d days old, under the %d-day learning window" % (age, young_days)
            entry.update(verdict=V_EARLY, fatiguing=False, fatigue=None, payback=None,
                         reasons=["learning: " + why, "no other verdict until it has delivered longer"])
            results.append(entry)
            continue

        fatigue = _fatigue(rows, key, window, min_change)
        grades = {m: cm.grade_against(ad, ads, m, group_by, min_impressions) for m in PAYBACK}
        payback = _payback(grades)
        first = first_by_key.get(key)
        first_payback = _payback({m: cm.grade_against(first, first_ads, m, group_by, min_impressions)
                                  for m in PAYBACK}) if first else {"known": False, "bottom": False}
        attention = {m: cm.grade_against(ad, ads, m, group_by, min_impressions)["band"] for m in ATTENTION}
        strong = [m for m, band in attention.items() if band == cm.BAND_TOP]

        reasons = []
        if age is None:
            reasons.append("age unknown (no dates in the data)")
        reasons.append("payback: " + ", ".join("%s %s" % (m, b) for m, b in payback["bands"].items()))
        if fatigue["status"] == "ok":
            reasons.append("trend over first vs last %d delivery days: ctr %s, frequency %s, hook rate %s "
                           "(fatigue needs ctr down %g%%+ and frequency up %g%%+ or hook down %g%%+)" % (
                               window, _pct(fatigue["ctr_change"]), _pct(fatigue["frequency_change"]),
                               _pct(fatigue["hook_change"]), min_change, min_change, min_change))
        else:
            reasons.append("fatigue not readable: " + fatigue["note"])
        fatiguing = fatigue["fatiguing"]

        if payback["bottom"] and first_payback["bottom"] and not fatiguing:
            verdict = V_NEVER
            reasons.append("payback was bottom quartile in the first %d delivery days and still is" % window)
        elif fatiguing and not payback["bottom"]:
            verdict = V_ITERATE
            reasons.append("fatiguing, but payback is %s: the concept still earns" %
                           ("not bottom quartile" if payback["known"] else "not gradable (cannot show it is weak)"))
        elif fatiguing:
            verdict = V_FATIGUED
            reasons.append("fatiguing and payback is bottom quartile")
        elif payback["top"] and fatigue["status"] == "ok":
            verdict = V_SCALE
            reasons.append("payback is top quartile and the ad is not fatiguing; "
                           "set the step size from your own account's history")
        elif strong and payback["bottom"]:
            verdict = V_ATTENTION
            reasons.append("%s top quartile but payback is bottom quartile" % " and ".join(strong))
        else:
            verdict = V_KEEP
            if payback["top"]:
                reasons.append("payback is top quartile but fatigue is not readable yet: hold before scaling")
            elif payback["bottom"]:
                reasons.append("payback is bottom quartile but not from the start and not fatiguing: watch it")
        if verdict == V_SCALE and ad.get("ad_type") == "promo":
            reasons.append("promo: strong payback can be existing demand being harvested; check "
                           "new-customer share and the sale end date before raising budget")
        entry.update(verdict=verdict, fatiguing=fatiguing, fatigue=fatigue, payback=payback,
                     attention=attention, reasons=reasons,
                     check=CHECK if verdict.startswith("kill") else None)
        results.append(entry)
    return results


def summarise(results: Sequence[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    """Verdict counts, ads that are too young, and spend concentration.

    top_n=3 is an arbitrary default: set your own from how many ads you run.
    """
    counts: Dict[str, int] = {}
    for entry in results:
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
    share = cm.concentration(results, top_n=top_n)
    if share is None:
        line = "top %d ads (N=%d, an arbitrary default: set your own) hold n/a of spend (no spend in the data)" % (top_n, top_n)
    else:
        line = ("top %d ads (N=%d, an arbitrary default: set your own) hold %.0f%% of spend. Heavy "
                "concentration means one fatigue event hurts the whole account; judge it against "
                "your own history." % (top_n, top_n, share))
    return {"counts": counts, "too_young": [e["ad"] for e in results if e["learning"]],
            "concentration_line": line}


def render(results: Sequence[Dict[str, Any]], args: argparse.Namespace, rows: Sequence[Dict[str, Any]]) -> str:
    summary = summarise(results, args.top_n)
    start, end = cm.data_window(rows)
    out = [
        "Basis: each ad graded against this account's own ads (same %s group), never a benchmark." % ", ".join(args.group_by.split(",")),
        "Window: %s to %s. Fatigue compares each ad's first and last %d delivery days." % (
            start or "n/a", end or "n/a", args.window),
        "Settings used (arbitrary defaults, set them from your own account): young-days=%d, window=%d, "
        "min-impressions=%d, top-n=%d, min-change=%g%% (a materiality size for ctr, frequency and hook movement, "
        "not a fatigue benchmark: set it from your own week-to-week noise)." % (
            args.young_days, args.window, args.min_impressions, args.top_n, args.min_change),
    ]
    bases = sorted({e["age_basis"] for e in results if e.get("age_basis")})
    out.append("Age basis: %s." % ("; ".join(bases) or "n/a (no dates in the data)"))
    derived = sorted({r["video_views_3s_source"] for r in rows
                      if (r.get("video_views_3s_source") or "").startswith("derived")})
    if derived:
        out.append("Hook rate (used in the fatigue trend): 3-second plays are %s." % derived[0])
    out += ["", "Summary:"]
    for verdict in ORDER:
        if verdict in summary["counts"]:
            out.append("  %-56s %d" % (verdict, summary["counts"][verdict]))
    out.append("  too young to judge: %s" % (", ".join(summary["too_young"]) or "none"))
    out.append("  " + summary["concentration_line"])
    out += ["", "Verdicts:"]
    for verdict in ORDER:
        for entry in results:
            if entry["verdict"] != verdict:
                continue
            out.append("%s  [%s]  age %s d, %s" % (entry["ad"], entry["format"] or "-",
                                                  "n/a" if entry["age_days"] is None else entry["age_days"],
                                                  entry["verdict"]))
            out += ["    - " + r for r in entry["reasons"]]
            if entry["check"]:
                out.append("    ! check first: " + entry["check"])
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Keep, kill, iterate or scale: a verdict per ad.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--young-days", type=int, default=5,
                        help="ads younger than this are still learning (arbitrary default)")
    parser.add_argument("--window", type=int, default=6,
                        help="days compared at the start and end of an ad's life (arbitrary default)")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are still learning (arbitrary default)")
    parser.add_argument("--min-change", type=float, default=8.0,
                        help="percent move that counts as real for ctr, frequency, hook rate "
                             "(arbitrary default: set from your own week-to-week noise)")
    parser.add_argument("--group-by", default="format",
                        help="comma-separated columns to compare within: a name field or any column in the "
                             "data, e.g. format,ad_type,market (default: format)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    parser.add_argument("--top-n", type=int, default=3,
                        help="how many top-spend ads the concentration line counts (arbitrary default)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    rows = cm.load_rows(args.path)
    group_by = tuple(g.strip() for g in args.group_by.split(",") if g.strip())
    try:
        key_map = cm.parse_key_map(args.key_map) if args.key_map else None
        results = judge_ads(rows, args.young_days, args.window, args.min_impressions, args.min_change,
                            group_by, key_map)
    except (cm.GroupColumnError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"summary": summarise(results, args.top_n), "settings": vars(args), "ads": results}, indent=2))
    else:
        print(render(results, args, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
