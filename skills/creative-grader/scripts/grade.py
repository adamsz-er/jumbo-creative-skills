#!/usr/bin/env python3
"""Grade each ad against the account's own baseline and diagnose the first broken funnel step.

Usage: python3 grade.py ads.csv [--group-by format,ad_type] [--key-map PX=concept] [--min-impressions 1000] [--json]

Standard library only. Every band is relative to the same account: top quartile
(at or above p75), middle, bottom quartile (at or below p25), within the ad's
own group and campaign objective. A group with too few comparable ads widens
(format and ad type, then format, then the whole account) and the basis says so.
Costs (cpm, cpa) are inverted. No benchmark is used anywhere. The
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

GRADED = ("cpm", "hook_rate", "hold_rate", "ctr", "cvr", "add_to_cart_rate", "cart_to_purchase_rate", "cpa", "roas",
          "cpc", "cost_per_lead", "engagement_rate")
LOW_VOLUME = "not graded (low volume)"
# An after-click step in the bottom quartile but not significantly below its group (creative_metrics.below_group):
# shown as graded, never a broken step, the same call funnel-diagnosis makes.
NOT_SIGNIFICANT = "bottom quartile, not significantly below its group"
# An after-click step in the bottom quartile whose gap to its group could not be tested: unknown, so no summary reads it as fine.
UNTESTED = "not graded (bottom quartile of its group, but the gap can't be tested: %s)"
# What the text output counts and lists an ad under when nothing reads weak but a step could not be tested: never plain "none".
NONE_UNTESTED = "none (with an untested step)"

HOOK_ACTION = "Change the first 3 seconds: the opening is not stopping the scroll."
ACTIONS = {
    "reach cost": "Reach is expensive: likely auction or audience saturation, not necessarily the creative. "
                  "Rule that out before changing the ad.",
    "hook": HOOK_ACTION,
    "hold": "The hook works but the promise is not sustained: tighten the body of the ad.",
    "click": "People watch but few click: the call to action or the offer is weak.",
    "post-click": "Clicks arrive but do not convert: likely the landing page or the offer, not the creative. "
                  "Check the site and whether the page matches the message; also rule out an audience mismatch.",
    "post-click cart": "People add to cart but do not buy: check checkout, price and shipping costs first, not the landing "
                       "page or the creative.",
    "pays back": "The funnel reads normally but payback is weak: check price, margin, offer and attribution "
                 "before blaming the creative.",
}

# funnel order, each step with the metrics that can break it
STEPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("reach cost", ("cpm",)),
    ("hook", ("hook_rate",)),
    ("hold", ("hold_rate",)),
    ("click", ("ctr",)),
    ("post-click", cm.AFTER_CLICK_STEPS),
    ("pays back", ("cpa", "roas")),
)


def _not_graded(band: Optional[str]) -> bool:
    return band is None or band.startswith("not graded")


def diagnose(bands: Dict[str, str], notes: Sequence[str] = (),
             payback: Sequence[str] = ("cpa", "roas")) -> Dict[str, Any]:
    """Name the FIRST broken step reading the funnel in order, with its one-line action.

    `bands` maps metric id to its band. A step is broken when any of its metrics
    is in the bottom quartile (an after-click metric only when it is also significantly
    below its group, see grade_ads); post-click is only read while CTR is not bottom,
    since a weak CTR is already the broken step. Steps whose metrics could not
    be graded are listed under `skipped`, never read as healthy. `payback` names
    the metrics that decide the last step for the ad's campaign objective.
    """
    skipped = list(notes)
    steps = tuple((step, tuple(payback) if step == "pays back" else metrics) for step, metrics in STEPS)
    for step, metrics in steps:
        for metric in metrics:
            band = bands.get(metric)
            if metric in bands and _not_graded(band):
                skipped.append("%s %s" % (metric, band))
    broken = [(step, [m for m in metrics if bands.get(m) == cm.BAND_BOTTOM])
              for step, metrics in steps]
    broken = [(step, metrics) for step, metrics in broken if metrics]
    prefix = UNTESTED.split("%s")[0]
    unknown = [m for m in cm.AFTER_CLICK_STEPS if str(bands.get(m) or "").startswith(prefix)]
    untested = ["%s could not be tested (%s)" % (m.replace("_", " "), bands[m][len(prefix):-1]) for m in unknown]
    if not broken:
        if unknown:
            return {"step": "none", "metrics": [], "untested": unknown, "also_weak": [], "skipped": skipped,
                    "summary": "no broken step found; %s could not be tested" % ", ".join(unknown),
                    "action": "Nothing graded reads weak, but %s, so the funnel is not known to read normally." % "; ".join(untested)}
        return {"step": "none", "metrics": [], "untested": [], "summary": "no broken step",
                "action": "Nothing in the funnel reads weak against this account.", "also_weak": [], "skipped": skipped}
    step, metrics = broken[0]
    also_weak = [m for _, later in broken[1:] for m in later]
    cart_only = step == "post-click" and all(m in cm.CART_STEPS for m in metrics)
    action = ACTIONS["post-click cart" if cart_only else step]
    if step == "pays back" and untested:
        action = ("Payback is weak, and %s, so the funnel is not known to read normally: check that step, then price, margin, "
                  "offer and attribution before blaming the creative." % "; ".join(untested))
    return {"step": step, "metrics": metrics, "also_weak": also_weak, "untested": unknown,
            "summary": "%s (%s bottom quartile)" % (step, ", ".join(metrics)),
            "action": action, "skipped": skipped}


def grade_ads(rows: Sequence[Dict[str, Any]], group_by: Optional[Sequence[str]] = None,
              min_impressions: int = 1000, key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """One entry per ad: grades per metric, then the diagnosis.

    Each ad is graded against ads of its own campaign objective, in the
    narrowest group (default format then ad type) with enough comparable ads.
    """
    ads = cm.aggregate_by_ad(rows, key_map=key_map)
    group_by, _ = cm.default_group_by(ads, group_by)
    results = []
    for ad in ads:
        graded = (ad.get("impressions") or 0) >= min_impressions
        info = cm.payback_metrics(ad.get("objective"))
        grades = {}
        for metric in GRADED:
            grade = cm.grade_in_objective(ad, ads, metric, group_by, min_impressions)
            if not graded:
                grade["band"] = LOW_VOLUME
            grade["display"] = cm.format_value(ad, metric)
            grades[metric] = grade
        for metric in cm.AFTER_CLICK_STEPS:
            gap, low, untested = cm.below_group(ad, ads, metric, grades[metric], min_impressions=min_impressions)
            grades[metric]["gap_z"], grades[metric]["significant"] = gap, None if untested else low
            if untested and graded:
                grades[metric]["band"] = UNTESTED % untested
        if graded:
            bands = {m: NOT_SIGNIFICANT if g["band"] == cm.BAND_BOTTOM and g.get("significant") is False else g["band"]
                     for m, g in grades.items()}
            diagnosis = diagnose(bands, payback=info["metrics"])
        else:
            diagnosis = {"step": "not graded", "metrics": [], "summary": LOW_VOLUME,
                         "action": "Too few impressions to judge: let it deliver, or raise the threshold knowingly.",
                         "also_weak": [], "skipped": []}
        results.append({
            "ad": ad.get("ad_id") or ad.get("ad_name"), "name": ad.get("ad_name"),
            "format": ad.get("format"), "group": cm.group_key(ad, group_by), "group_by": list(group_by),
            "graded_in": grades["ctr"].get("group_value"), "graded_in_size": grades["ctr"].get("group_size"),
            "objective": info["objective"], "objective_assumed": info["assumed"],
            "payback_basis": info["what"], "payback_metrics": list(info["metrics"]),
            "impressions": ad.get("impressions"), "graded": graded,
            "ctr_clicks": cm.metric_basis(ad, "ctr")["numerator"],
            "conversions_source": ad.get("conversions_source"),
            "hook_source": ad.get("video_views_3s_source"),
            "grades": grades, "diagnosis": diagnosis,
        })
    return results


def _shown_step(entry: Dict[str, Any]) -> str:
    """The step the text output counts an ad under: plain "none" only when no step was left untested."""
    diagnosis = entry["diagnosis"]
    return NONE_UNTESTED if diagnosis["step"] == "none" and diagnosis.get("untested") else diagnosis["step"]


def _used_group(entry: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    """The group an ad's ctr was actually graded in (after any widening) and its size."""
    grade = entry["grades"]["ctr"]
    if grade.get("group_size") is None:
        return "not graded", None
    return "%s (%s)" % (grade["group_value"], entry["objective"]), grade["group_size"]


def basis_header(rows: Sequence[Dict[str, Any]], results: Sequence[Dict[str, Any]],
                 group_by: Sequence[str] = ("format",), min_impressions: int = 1000,
                 group_note: Optional[str] = None) -> str:
    """The basis every number below rests on: window, grouping, group sizes, clicks, conversions."""
    ads = cm.aggregate_by_ad(rows)
    start, end = cm.data_window(rows)
    sizes: Dict[str, int] = {}
    for entry in results:
        if entry["graded"]:
            name, size = _used_group(entry)
            if size is not None:
                sizes[name] = size
    sources = sorted({r["conversions_source"] for r in results if r["conversions_source"]})
    widened = [e for e in results if e["graded"] and e["grades"]["ctr"].get("fallback")]
    thin = sorted(name for name, size in sizes.items() if cm.is_thin(size))
    lines = [
        "Basis: graded against this account's own ads of the same campaign objective, never a benchmark.",
        "Window: %s to %s" % (start or "n/a (no dates)", end or "n/a (no dates)"),
        "Grouped by: %s, widening when a group has under %d comparable ads. Comparable ads per group used: %s" % (
            ", ".join(group_by), cm.MIN_GROUP, ", ".join("%s n=%d" % kv for kv in sorted(sizes.items())) or "none"),
        "Bands: top quartile is at or above p75, bottom at or below p25 (costs inverted: a cheap CPM is top).",
        "Ads under %d impressions are not graded (arbitrary default: set it from your own spend per ad)." % min_impressions,
        cm.click_basis_line(ads),
        "Conversions column: %s." % (", ".join(sources) or "n/a (no conversions column)"),
    ]
    if group_note:
        lines.append("Grouping: " + group_note + ".")
    assumed = [e["ad"] for e in results if e.get("objective_assumed")]
    if assumed:
        lines.append("Objective: not in the data (or not a known objective) for %d ads, so they are graded as sales. "
                     "Add an objective column to grade each ad on its own goal." % len(assumed))
    by_objective = sorted({(e["objective"], e["payback_basis"]) for e in results})
    lines.append("Payback is read by objective: " + "; ".join("%s: %s" % kv for kv in by_objective) + ".")
    derived = sorted({r["hook_source"] for r in results if (r.get("hook_source") or "").startswith("derived")})
    if derived:
        lines.append("Hook rate: 3-second plays are not reported per ad here, so they are %s. "
                     "Hold rate uses ThruPlays." % derived[0])
    if widened:
        lines.append("%d of %d ads were graded in a wider group than %s because the narrower one had under %d "
                     "comparable ads (each ad's own reason is in --json); the group column shows where each was graded."
                     % (len(widened), sum(1 for e in results if e["graded"]), " / ".join(group_by), cm.MIN_GROUP))
    if thin:
        lines.append("WARNING small comparison groups (fewer than twice the %d-ad minimum, so a grade there is an early read): %s." % (
            cm.MIN_GROUP, ", ".join(thin)))
    return "\n".join(lines)


_SHORT = {cm.BAND_TOP: "top", cm.BAND_MID: "mid", cm.BAND_BOTTOM: "LOW"}


def _cell(entry: Dict[str, Any], metric: str, digits: int = 1) -> str:
    grade = entry["grades"][metric]
    if grade["value"] is None:
        return "n/a"
    band = grade["band"]
    return "%.*f %s" % (digits, grade["value"], _SHORT.get(band, "-"))


def render(rows, results, group_by=("format",), min_impressions=1000, group_note=None) -> str:
    header = ["ad", "group", "hook%", "hold%", "ctr%", "cpm", "cpa", "roas", "diagnosis"]
    lines = []
    for entry in results:
        hook = _cell(entry, "hook_rate")
        if hook != "n/a" and (entry.get("hook_source") or "").startswith("derived"):
            hook += " (derived)"
        lines.append([str(entry["ad"]), str(entry.get("graded_in") or "not graded"), hook,
                      _cell(entry, "hold_rate"), _cell(entry, "ctr", 2), _cell(entry, "cpm", 2),
                      _cell(entry, "cpa", 2), _cell(entry, "roas", 2), entry["diagnosis"]["summary"]])
    widths = [max(len(header[i]), *(len(r[i]) for r in lines)) for i in range(len(header))]
    out = [basis_header(rows, results, group_by, min_impressions, group_note), ""]
    out.append("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in lines]
    counts: Dict[str, int] = {}
    for entry in results:
        counts[_shown_step(entry)] = counts.get(_shown_step(entry), 0) + 1
    out += ["", "Diagnoses: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1]))]
    out += ["", "What to do, by first broken step (fix that step first, then re-read; 'also weak' lists later bottom-quartile metrics):"]
    for step in [s for s, _ in STEPS] + [NONE_UNTESTED]:
        hits = [e for e in results if _shown_step(e) == step]
        for action in dict.fromkeys(e["diagnosis"]["action"] for e in hits):
            out.append("  %s: %s" % (step, action))
            for e in (e for e in hits if e["diagnosis"]["action"] == action):
                extra = " (also weak: %s)" % ", ".join(e["diagnosis"]["also_weak"]) if e["diagnosis"]["also_weak"] else ""
                out.append("    %s%s" % (e["ad"], extra))
    skipped: Dict[str, Dict[str, List[str]]] = {}
    for e in results:
        for item in e["diagnosis"]["skipped"]:
            metric, _, band = item.partition(" ")
            reason = band[len("not graded ("):-1] if band.startswith("not graded (") and band.endswith(")") else band
            skipped.setdefault(metric, {}).setdefault(reason, []).append(str(e["ad"]))
    if skipped:
        out += ["", "Steps skipped, never read as healthy (one line per step: quote its count, never recount):"]
        for metric, reasons in skipped.items():
            ads = [a for found in reasons.values() for a in found]
            why = " (%s)" % next(iter(reasons)) if len(reasons) == 1 else ""
            counted = "" if len(reasons) == 1 else ", ".join("%d %s" % (len(found), reason) for reason, found in reasons.items()) + ": "
            out.append("  %s not graded%s on %d ad%s: %s%s" % (metric, why, len(ads), "" if len(ads) == 1 else "s", counted, ", ".join(ads)))
    out += ["", "LOW = bottom quartile, top = top quartile, mid = middle; n/a = missing or zero operand, never 0."]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Grade ads against the account's own baseline.")
    parser.add_argument("path", help="Ads Manager CSV, or a .json file of rows")
    parser.add_argument("--group-by", default=None,
                        help="comma-separated columns to compare within, widest fallback last: a name field or any "
                             "column in the data, e.g. format,ad_type,market (default: format,ad_type)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are not graded (arbitrary default; set from your own account)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        explicit = tuple(g.strip() for g in args.group_by.split(",") if g.strip()) if args.group_by else None
        group_by, group_note = cm.default_group_by(cm.aggregate_by_ad(rows, key_map=key_map), explicit)
        results = grade_ads(rows, group_by=group_by, min_impressions=args.min_impressions, key_map=key_map)
    except (cm.GroupColumnError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"basis": basis_header(rows, results, group_by, args.min_impressions, group_note),
                          "run_notes": run_notes, "ads": results}, indent=2))
    else:
        print("\n".join(run_notes + [render(rows, results, group_by, args.min_impressions, group_note)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
