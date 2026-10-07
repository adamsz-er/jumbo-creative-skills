#!/usr/bin/env python3
"""Grade each ad against the account's own baseline and diagnose the first broken funnel step.

Usage: python3 grade.py ads.csv [--group-by format] [--key-map PX=concept] [--min-impressions 1000] [--json]

Standard library only. Every band is relative to the same account: top quartile
(at or above p75), middle, bottom quartile (at or below p25), within the ad's
own group. Costs (cpm, cpa) are inverted. No benchmark is used anywhere. The
--min-impressions default is arbitrary: set it from your own spend per ad.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

GRADED = ("cpm", "hook_rate", "hold_rate", "ctr", "cvr", "add_to_cart_rate", "cpa", "roas")
LOW_VOLUME = "not graded (low volume)"

HOOK_ACTION = "Change the first 3 seconds: the opening is not stopping the scroll."
ACTIONS = {
    "reach cost": "Reach is expensive: likely auction or audience saturation, not necessarily the creative. "
                  "Rule that out before changing the ad.",
    "hook": HOOK_ACTION,
    "hold": "The hook works but the promise is not sustained: tighten the body of the ad.",
    "click": "People watch but few click: the call to action or the offer is weak.",
    "post-click": "Clicks arrive but do not convert: likely the landing page or the offer, not the creative. "
                  "Check the site and whether the page matches the message; also rule out an audience mismatch.",
    "pays back": "The funnel reads normally but payback is weak: check price, margin, offer and attribution "
                 "before blaming the creative.",
}

# funnel order, each step with the metrics that can break it
STEPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("reach cost", ("cpm",)),
    ("hook", ("hook_rate",)),
    ("hold", ("hold_rate",)),
    ("click", ("ctr",)),
    ("post-click", ("cvr", "add_to_cart_rate")),
    ("pays back", ("cpa", "roas")),
)


def _not_graded(band: Optional[str]) -> bool:
    return band is None or band.startswith("not graded")


def diagnose(bands: Dict[str, str], notes: Sequence[str] = ()) -> Dict[str, Any]:
    """Name the FIRST broken step reading the funnel in order, with its one-line action.

    `bands` maps metric id to its band. A step is broken when any of its metrics
    is in the bottom quartile; post-click is only read while CTR is not bottom,
    since a weak CTR is already the broken step. Steps whose metrics could not
    be graded are listed under `skipped`, never read as healthy.
    """
    skipped = list(notes)
    for step, metrics in STEPS:
        for metric in metrics:
            band = bands.get(metric)
            if metric in bands and _not_graded(band):
                skipped.append("%s %s" % (metric, band))
    broken = [(step, [m for m in metrics if bands.get(m) == cm.BAND_BOTTOM])
              for step, metrics in STEPS]
    broken = [(step, metrics) for step, metrics in broken if metrics]
    if not broken:
        return {"step": "none", "metrics": [], "summary": "no broken step",
                "action": "Nothing in the funnel reads weak against this account.",
                "also_weak": [], "skipped": skipped}
    step, metrics = broken[0]
    also_weak = [m for _, later in broken[1:] for m in later]
    return {"step": step, "metrics": metrics, "also_weak": also_weak,
            "summary": "%s (%s bottom quartile)" % (step, ", ".join(metrics)),
            "action": ACTIONS[step], "skipped": skipped}


def grade_ads(rows: Sequence[Dict[str, Any]], group_by: Sequence[str] = ("format",),
              min_impressions: int = 1000, key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """One entry per ad: grades per metric, then the diagnosis."""
    ads = cm.aggregate_by_ad(rows, key_map=key_map)
    group_by = cm.resolve_group_by(ads, group_by)
    results = []
    for ad in ads:
        graded = (ad.get("impressions") or 0) >= min_impressions
        grades = {}
        for metric in GRADED:
            grade = cm.grade_against(ad, ads, metric, group_by=group_by, min_impressions=min_impressions)
            if not graded:
                grade["band"] = LOW_VOLUME
            grade["display"] = cm.format_value(ad, metric)
            grades[metric] = grade
        if graded:
            diagnosis = diagnose({m: g["band"] for m, g in grades.items()})
        else:
            diagnosis = {"step": "not graded", "metrics": [], "summary": LOW_VOLUME,
                         "action": "Too few impressions to judge: let it deliver, or raise the threshold knowingly.",
                         "also_weak": [], "skipped": []}
        results.append({
            "ad": ad.get("ad_id") or ad.get("ad_name"), "name": ad.get("ad_name"),
            "format": ad.get("format"), "group": cm.group_key(ad, group_by), "group_by": list(group_by),
            "impressions": ad.get("impressions"), "graded": graded,
            "ctr_clicks": cm.metric_basis(ad, "ctr")["numerator"],
            "conversions_source": ad.get("conversions_source"),
            "hook_source": ad.get("video_views_3s_source"),
            "grades": grades, "diagnosis": diagnosis,
        })
    return results


def basis_header(rows: Sequence[Dict[str, Any]], results: Sequence[Dict[str, Any]],
                 group_by: Sequence[str] = ("format",), min_impressions: int = 1000) -> str:
    """The basis every number below rests on: window, grouping, group sizes, clicks, conversions."""
    start, end = cm.data_window(rows)
    sizes: Dict[str, int] = {}
    for entry in results:
        if entry["graded"]:
            sizes[entry["group"]] = sizes.get(entry["group"], 0) + 1
    clicks = sorted({r["ctr_clicks"] for r in results if r["ctr_clicks"]})
    sources = sorted({r["conversions_source"] for r in results if r["conversions_source"]})
    fallback = sorted({e["group"] for e in results if e["graded"]
                       and (e["grades"]["ctr"].get("basis") or "").startswith("account-wide")})
    lines = [
        "Basis: graded against this account's own ads, never a benchmark.",
        "Window: %s to %s" % (start or "n/a (no dates)", end or "n/a (no dates)"),
        "Grouped by: %s. Ads graded per group: %s" % (
            ", ".join(group_by), ", ".join("%s=%d" % kv for kv in sorted(sizes.items())) or "none"),
        "Bands: top quartile is at or above p75, bottom at or below p25 (costs inverted: a cheap CPM is top).",
        "Ads under %d impressions are not graded (arbitrary default: set it from your own spend per ad)." % min_impressions,
        "CTR uses: %s. Conversions column: %s." % (", ".join(clicks) or "n/a (no clicks)",
                                                    ", ".join(sources) or "n/a (no conversions column)"),
    ]
    derived = sorted({r["hook_source"] for r in results if (r.get("hook_source") or "").startswith("derived")})
    if derived:
        lines.append("Hook rate: 3-second plays are not reported per ad here, so they are %s. "
                     "Hold rate uses ThruPlays." % derived[0])
    if fallback:
        lines.append("Groups with fewer than 5 ads fall back to account-wide numbers: %s." % ", ".join(fallback))
    return "\n".join(lines)


_SHORT = {cm.BAND_TOP: "top", cm.BAND_MID: "mid", cm.BAND_BOTTOM: "LOW"}


def _cell(entry: Dict[str, Any], metric: str, digits: int = 1) -> str:
    grade = entry["grades"][metric]
    if grade["value"] is None:
        return "n/a"
    band = grade["band"]
    return "%.*f %s" % (digits, grade["value"], _SHORT.get(band, "-"))


def render(rows, results, group_by=("format",), min_impressions=1000) -> str:
    header = ["ad", "group", "hook%", "hold%", "ctr%", "cpm", "cpa", "roas", "diagnosis"]
    lines = []
    for entry in results:
        hook = _cell(entry, "hook_rate")
        if hook != "n/a" and (entry.get("hook_source") or "").startswith("derived"):
            hook += " (derived)"
        lines.append([str(entry["ad"]), entry["group"], hook,
                      _cell(entry, "hold_rate"), _cell(entry, "ctr", 2), _cell(entry, "cpm", 2),
                      _cell(entry, "cpa", 2), _cell(entry, "roas", 2), entry["diagnosis"]["summary"]])
    widths = [max(len(header[i]), *(len(r[i]) for r in lines)) for i in range(len(header))]
    out = [basis_header(rows, results, group_by, min_impressions), ""]
    out.append("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in lines]
    counts: Dict[str, int] = {}
    for entry in results:
        counts[entry["diagnosis"]["step"]] = counts.get(entry["diagnosis"]["step"], 0) + 1
    out += ["", "Diagnoses: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1]))]
    out += ["", "What to do, by first broken step (fix that step first, then re-read; 'also weak' lists later bottom-quartile metrics):"]
    for step, _ in STEPS:
        hits = [e for e in results if e["diagnosis"]["step"] == step]
        if not hits:
            continue
        out.append("  %s: %s" % (step, ACTIONS[step]))
        for e in hits:
            extra = " (also weak: %s)" % ", ".join(e["diagnosis"]["also_weak"]) if e["diagnosis"]["also_weak"] else ""
            out.append("    %s%s" % (e["ad"], extra))
    notes: Dict[Tuple[str, ...], List[str]] = {}
    for e in results:
        if e["diagnosis"]["skipped"]:
            notes.setdefault(tuple(e["diagnosis"]["skipped"]), []).append(str(e["ad"]))
    if notes:
        out += ["", "Steps skipped, never read as healthy:"]
        for skipped, ads in notes.items():
            out.append("  %s: %d ads (%s)" % ("; ".join(skipped), len(ads), ", ".join(ads)))
    out += ["", "LOW = bottom quartile, top = top quartile, mid = middle; n/a = missing or zero operand, never 0."]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Grade ads against the account's own baseline.")
    parser.add_argument("path", help="Ads Manager CSV, or a .json file of rows")
    parser.add_argument("--group-by", default="format",
                        help="comma-separated columns to compare within: a name field or any column in the "
                             "data, e.g. format,ad_type,market (default: format)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are not graded (arbitrary default; set from your own account)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    group_by = tuple(g.strip() for g in args.group_by.split(",") if g.strip())
    rows = cm.load_rows(args.path)
    try:
        key_map = cm.parse_key_map(args.key_map) if args.key_map else None
        results = grade_ads(rows, group_by=group_by, min_impressions=args.min_impressions, key_map=key_map)
    except (cm.GroupColumnError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    group_by = tuple(results[0]["group_by"]) if results else group_by
    if args.json:
        print(json.dumps({"basis": basis_header(rows, results, group_by, args.min_impressions),
                          "ads": results}, indent=2))
    else:
        print(render(rows, results, group_by, args.min_impressions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
