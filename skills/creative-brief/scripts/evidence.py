#!/usr/bin/env python3
"""An "Evidence" block for a creative brief, from the account's own ads.

Usage: python3 evidence.py ads.csv [--include-types bau,promo] [--window 6] [--min-change 8] [--max-gaps 8] [--json]

Standard library only. Lists the account's top-quartile ads with the fields
parsed from their names, the ads that are fatiguing or never worked, and
concept x format cells with no ad beside a top-quartile ad. Every judgement is
relative to this account's own ads in the same format, never a benchmark.
--include-types picks which ad types seed coverage gaps (default: bau). --window,
--min-change and --max-gaps are arbitrary defaults: set them from
your own account. With no usable rows it prints "Evidence: none available".
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

import creative_metrics as cm

NONE_AVAILABLE = "Evidence: none available"
PAYBACK = ("cpa", "roas")
FIELDS = ("concept", "format", "creator", "ad_type", "product", "tone")


def _key(ad: Dict[str, Any]) -> Optional[str]:
    return ad.get("ad_id") or ad.get("ad_name")


def _summary(ad: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ad": _key(ad), "ad_name": ad.get("ad_name")}
    out.update({f: ad.get(f) for f in FIELDS})
    out.update(roas=ad.get("roas"), cpa=ad.get("cpa"), spend=ad.get("spend"), age_days=ad.get("age_days"))
    return out


def _bands(ad: Dict[str, Any], ads: Sequence[Dict[str, Any]], min_impressions: int) -> Dict[str, str]:
    return {m: cm.grade_against(ad, ads, m, ("format",), min_impressions)["band"] for m in PAYBACK}


def _bottom(bands: Dict[str, str]) -> bool:
    return cm.BAND_BOTTOM in bands.values()


def _fatiguing(rows: Sequence[Dict[str, Any]], key: str, window: int, min_change: float) -> Dict[str, Any]:
    ctr = cm.fatigue_trend(rows, key, "ctr", window)
    if ctr["status"] != "ok":
        return {"fatiguing": False, "readable": False}
    hook = cm.fatigue_trend(rows, key, "hook_rate", window)
    ctr_change, freq_change = ctr.get("pct_change"), ctr.get("frequency_pct_change")
    hook_change = hook.get("pct_change") if hook["status"] == "ok" else None
    ctr_down = ctr_change is not None and ctr_change <= -min_change
    freq_up = freq_change is not None and freq_change >= min_change
    hook_down = hook_change is not None and hook_change <= -min_change
    return {"fatiguing": bool(ctr_down and (freq_up or hook_down)), "readable": True,
            "ctr_change": ctr_change, "frequency_change": freq_change, "hook_change": hook_change}


def build_evidence(rows: Sequence[Dict[str, Any]], window: int = 6, min_change: float = 8.0,
                   min_impressions: int = 1000, max_gaps: int = 8,
                   include_types: Sequence[str] = ("bau",)) -> Dict[str, Any]:
    """Top-quartile ads, fatiguing and never-worked ads, and coverage gaps."""
    ads = [a for a in cm.aggregate_by_ad(rows) if a.get("concept") and a.get("format")]
    if not ads:
        return {"available": False}
    first_ads = cm.window_aggregate(rows, window, "first")
    first_by_key = {_key(a): a for a in first_ads}
    top, fatiguing, never, young = [], [], [], []
    for ad in ads:
        if (ad.get("impressions") or 0) < min_impressions:
            young.append(_key(ad))
            continue
        bands = _bands(ad, ads, min_impressions)
        trend = _fatiguing(rows, _key(ad), window, min_change)
        entry = dict(_summary(ad), bands=bands)
        if trend["fatiguing"]:
            fatiguing.append(dict(entry, trend=trend))
        elif _bottom(bands):
            first = first_by_key.get(_key(ad))
            if first and _bottom(_bands(first, first_ads, min_impressions)):
                never.append(entry)
        graded = [b for b in bands.values() if not b.startswith("not graded")]
        if graded and all(b == cm.BAND_TOP for b in graded):
            top.append(entry)

    # Promo and launch concepts are tied to a date, so by default only evergreen winners
    # seed gaps; the caller can include other ad types when briefing a sale or a launch.
    top_concepts = sorted({a["concept"] for a in top if a.get("ad_type") in include_types})
    top_formats = sorted({a["format"] for a in top})
    present = {(a["concept"], a["format"]) for a in ads}
    gaps = [{"concept": c, "format": f} for c in top_concepts for f in top_formats if (c, f) not in present]
    return {
        "available": True, "ads": len(ads), "window": cm.data_window(rows),
        "settings": {"window": window, "min_change": min_change, "min_impressions": min_impressions,
                     "include_types": list(include_types)},
        "top_quartile": top, "fatiguing": fatiguing, "never_worked": never,
        "top_concepts": top_concepts, "top_formats": top_formats,
        "gaps": gaps[:max_gaps], "gaps_total": len(gaps), "too_young": young,
    }


def _ad_line(ad: Dict[str, Any]) -> str:
    fields = " | ".join(str(ad.get(f) or "?") for f in FIELDS)
    return "  %s  %s  (roas %s, cpa %s)" % (ad["ad"], fields, _n(ad["roas"]), _n(ad["cpa"]))


def _n(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.2f" % value


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%+.0f%%" % value


def render(result: Dict[str, Any]) -> str:
    if not result.get("available"):
        return NONE_AVAILABLE
    start, end = result["window"]
    s = result["settings"]
    out = [
        "Evidence",
        "Basis: this account's own ads, %s to %s, each graded against ads of the same format. "
        "Never a benchmark." % (start or "n/a", end or "n/a"),
        "Settings (arbitrary defaults, set them from your own account): window=%d days, "
        "min-change=%g%%, min-impressions=%d. Ad types used to seed gaps: %s." % (
            s["window"], s["min_change"], s["min_impressions"], ", ".join(s["include_types"])),
        "Hook wording is not in an ad export: take the opening line from the ad itself.",
        "", "Top-quartile ads (top quartile when all available payback metrics (cpa, roas) are top quartile "
        "for the ad's format; fields from the ad name, confirm them before relying on them):"]
    out += [_ad_line(a) for a in result["top_quartile"]] or ["  none"]
    out += ["", "Fatiguing ads (ctr down and frequency or hook rate moving the wrong way, first vs last "
            "%d delivery days):" % s["window"]]
    for a in result["fatiguing"]:
        t = a["trend"]
        out.append(_ad_line(a) + "  ctr %s, frequency %s, hook rate %s" % (
            _pct(t["ctr_change"]), _pct(t["frequency_change"]), _pct(t["hook_change"])))
    if not result["fatiguing"]:
        out.append("  none")
    out += ["", "Never worked (payback bottom quartile from the first %d delivery days and still is; rule out "
            "tracking, site and audience first):" % s["window"]]
    out += [_ad_line(a) for a in result["never_worked"]] or ["  none"]
    out += ["", "Coverage gaps (concepts of ad types %s behind a top-quartile ad, in the formats of the "
            "top-quartile ads, with no ad; a hypothesis to test, not a result):" % ", ".join(s["include_types"])]
    out += ["  %s in %s" % (g["concept"], g["format"]) for g in result["gaps"]] or ["  none"]
    if result["gaps_total"] > len(result["gaps"]):
        out.append("  ... %d more (see --json)" % (result["gaps_total"] - len(result["gaps"])))
    if result["too_young"]:
        out += ["", "Too little delivery to judge: %s" % ", ".join(str(a) for a in result["too_young"])]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence block for a creative brief.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--include-types", default="bau",
                        help="comma-separated ad types whose top-quartile concepts seed coverage gaps "
                             "(default: bau; add promo or launch when briefing a sale or a drop)")
    parser.add_argument("--window", type=int, default=6,
                        help="days compared at the start and end of an ad's life (arbitrary default)")
    parser.add_argument("--min-change", type=float, default=8.0,
                        help="percent move that counts as real (arbitrary default)")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are not judged (arbitrary default)")
    parser.add_argument("--max-gaps", type=int, default=8, help="gaps shown (arbitrary default)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    result = build_evidence(cm.load_rows(args.path), args.window, args.min_change,
                            args.min_impressions, args.max_gaps,
                            tuple(t.strip().lower() for t in args.include_types.split(",") if t.strip()))
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
