#!/usr/bin/env python3
"""Which ads are fading, which are on course to, and a dated refresh calendar.

Usage: python3 fatigue_plan.py ads.csv [--metric ctr] [--capacity 2] [--start 2026-03-31] [--weeks 6]
                               [--lead-days 7] [--window 6] [--min-change 8] [--fit-days 9] [--min-days 9]
                               [--min-impressions 1000] [--curve-min-ads 3] [--json]

Standard library only. For each ad it reads three things from the account's own data: the fatigue trend (the
metric falling while frequency rises or hook rate falls, the rule keep-or-kill uses), where the ad sits against
the account's band for its day of delivery (only ads launched inside the window build that band), and a straight
line fitted to the metric over the ad's last delivery days. The line, run forward to the floor (the lower quartile
of the metric among ads of the same format), gives an estimate of days left with a range from the line's own
standard error. It is a straight-line estimate: a real ad may not fade in a straight line.

With --capacity (refreshes the team can produce per week) it also builds a dated calendar: fading ads first
(largest spend first), then ads on course to fade (soonest first), each placed in the first week with a free slot.
Without it the calendar is left out. --weeks, --lead-days, --window, --min-change, --fit-days, --min-days,
--min-impressions and --curve-min-ads are arbitrary defaults: set them from your own account. Use a rate where
higher is better (ctr, hook_rate). A missing operand is shown as "n/a (missing <field>)", never 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

SCHEMA = 1
NOT_FALLING = "not falling"
NO_END = "no end in sight"
NO_CALENDAR = "Give --capacity (ads you can make per week) for a dated refresh calendar."
LINE_CAVEAT = "a real ad may not fade in a straight line"
BEFORE_NOTE = ("running before the window began: compared with its own start, not the account's "
               "delivery-day band")


def fit_line(points: Sequence[Tuple[float, float]]) -> Optional[Dict[str, Optional[float]]]:
    """Ordinary least squares of y on x: slope, intercept and the slope's standard error (n-2 dof).

    Needs two points with different x. With fewer than three points there is no standard error.
    """
    n = len(points)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / sxx
    intercept = mean_y - slope * mean_x
    se = None
    if n >= 3:
        residuals = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
        se = math.sqrt(max(residuals, 0.0) / (n - 2) / sxx)
    return {"slope": slope, "intercept": intercept, "se": se}


def days_to_floor(fitted_now: float, floor: float, slope: float) -> Optional[float]:
    """Days until a line falling at `slope` per day goes from `fitted_now` to `floor`; None if it is not falling."""
    if fitted_now <= floor:
        return 0.0
    if slope >= 0:
        return None
    return (fitted_now - floor) / -slope


def whole_days(exact: float) -> int:
    """Whole days to the floor: 0 only when the line is already at or below it, else at least 1."""
    return 0 if exact <= 0 else max(1, round(exact))


def days_left_range(fitted_now: float, floor: float, slope: float, se: Optional[float]) -> Tuple[Optional[int], Optional[int]]:
    """(low, high) whole days from the slope one standard error faster and slower; high None is no end in sight."""
    if se is None or slope >= 0 or fitted_now <= floor:
        return None, None
    low = days_to_floor(fitted_now, floor, slope - se)
    high = days_to_floor(fitted_now, floor, slope + se)
    return whole_days(low), (whole_days(high) if high is not None else None)


def floor_for(ad: Dict[str, Any], base: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """The lower quartile of the metric among ads of the same format, and which group it came from."""
    group = str(ad.get("format") or "unknown")
    stats = base["groups"].get(group, base["account"])
    return stats["p25"], "%s (%s)" % (group, stats.get("basis", "account-wide"))


def band_position(series: Sequence[Dict[str, Any]], curve: Sequence[Dict[str, Any]], metric: str,
                  window: int) -> Dict[str, int]:
    """Over the last `window` delivered days with a value: days below that delivery day's lower quartile."""
    recent = [e for e in series if e["delivery_day"] is not None and e[metric] is not None][-window:]
    below = checked = no_band = 0
    for entry in recent:
        day = entry["delivery_day"]
        p25 = curve[day - 1]["p25"] if day <= len(curve) else None
        if p25 is None:
            no_band += 1
            continue
        checked += 1
        below += entry[metric] < p25
    return {"below": below, "checked": checked, "no_band": no_band}


def trend_summary(rows: Sequence[Dict[str, Any]], key: str, metric: str, window: int) -> Dict[str, Optional[float]]:
    main = cm.fatigue_trend(rows, key, metric, window)
    hook = cm.fatigue_trend(rows, key, "hook_rate", window)
    return {"pct_change": main.get("pct_change"), "frequency_pct_change": main.get("frequency_pct_change"),
            "hook_change": hook.get("pct_change")}


def is_fading_trend(trend: Dict[str, Optional[float]], min_change: float) -> bool:
    """The keep-or-kill rule: the metric down by min_change percent and frequency up or hook rate down by as much."""
    down = trend["pct_change"] is not None and trend["pct_change"] <= -min_change
    freq_up = trend["frequency_pct_change"] is not None and trend["frequency_pct_change"] >= min_change
    hook_down = trend["hook_change"] is not None and trend["hook_change"] <= -min_change
    return bool(down and (freq_up or hook_down))


def describe_days_left(entry: Dict[str, Any]) -> str:
    left, low, high = entry["days_left"], entry["days_left_low"], entry["days_left_high"]
    if left is None:
        return NOT_FALLING
    if left == 0:
        return "already at or below the floor"
    span = ""
    if low is not None:
        span = "range %d to %s, " % (low, NO_END if high is None else high)
    return "about %d day%s (%sfrom a straight line through its last %d delivery days; %s)" % (
        left, "" if left == 1 else "s", span, entry["fit_days_used"], LINE_CAVEAT)


def base_entry(ad: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
    return {"ad": ad.get("ad_id") or ad.get("ad_name"), "ad_name": ad.get("ad_name"),
            "concept": ad.get("concept"), "format": ad.get("format"), "spend": ad.get("spend"),
            "age_days": ad.get("age_days"), "age_basis": ad.get("age_basis"), "delivery_days": None, "fit_days_used": None,
            "status": status, "days_left": None, "days_left_low": None, "days_left_high": None,
            "fade_date": None, "days_left_note": None, "floor": None, "floor_basis": None, "slope": None, "slope_se": None,
            "below_band_days": None, "band_days_checked": None,
            "trend": {"pct_change": None, "frequency_pct_change": None, "hook_change": None},
            "reason": reason}


def judge_ad(rows: Sequence[Dict[str, Any]], ad: Dict[str, Any], metric: str,
             base: Dict[str, Any], curve: Sequence[Dict[str, Any]], last_date: Optional[dt.date],
             settings: Dict[str, Any]) -> Dict[str, Any]:
    if (ad.get("impressions") or 0) < settings["min_impressions"]:
        return base_entry(ad, "too little delivery", "too little delivery to judge (under %d impressions)"
                          % settings["min_impressions"])
    if ad.get(metric) is None:
        return base_entry(ad, "unreadable", "n/a (%s)" % (cm.describe_missing(ad, metric) or "no value"))
    key = str(ad.get("ad_id") or ad.get("ad_name"))
    series = cm.delivery_series(rows, key, [metric])
    delivered = [e for e in series if e["delivery_day"] is not None]
    if len(delivered) < settings["min_days"]:
        entry = base_entry(ad, "too little history", "%d delivery days, needs %d" % (len(delivered), settings["min_days"]))
        entry["delivery_days"] = len(delivered)
        return entry
    entry = base_entry(ad, "steady", "")
    entry["delivery_days"] = len(delivered)
    entry["trend"] = trend_summary(rows, key, metric, settings["window"])
    launched = cm.launched_in_window(rows, key, series)[0] is not None
    notes = []
    if launched:
        position = band_position(series, curve, metric, settings["window"])
        entry["below_band_days"], entry["band_days_checked"] = position["below"], position["checked"]
        if position["checked"] and position["below"] * 2 > position["checked"]:
            notes.append("below the account's band for its age for most of its last days (%d of %d)"
                         % (position["below"], position["checked"]))
    else:
        notes.append(BEFORE_NOTE)
    floor, floor_basis = floor_for(ad, base)
    entry["floor"], entry["floor_basis"] = floor, floor_basis
    points = [(float(e["delivery_day"]), e[metric]) for e in delivered if e[metric] is not None][-settings["fit_days"]:]
    fit = fit_line(points)
    if fit is None or floor is None:
        entry["status"] = "too little history" if fit is None else "unreadable"
        entry["reason"] = ("too few days with a value to fit a line" if fit is None
                           else "n/a (no floor: no ad of this format has the metric)")
        return entry
    entry["slope"], entry["slope_se"], entry["fit_days_used"] = fit["slope"], fit["se"], len(points)
    fitted_now = fit["intercept"] + fit["slope"] * points[-1][0]
    exact = days_to_floor(fitted_now, floor, fit["slope"])
    if exact is not None:
        entry["days_left"] = whole_days(exact)
        entry["days_left_low"], entry["days_left_high"] = days_left_range(fitted_now, floor, fit["slope"], fit["se"])
        if last_date:
            entry["fade_date"] = (last_date + dt.timedelta(days=entry["days_left"])).isoformat()
    if exact is None:
        entry["days_left_note"] = NOT_FALLING
    # A fall counts only when the line is still falling at the slow end of its range (slope plus one standard
    # error below zero), so noise around a flat line is never read as a fade. Sitting below the floor is a level,
    # not a fade: keep-or-kill and the grader judge levels.
    falling = fit["slope"] < 0 and fit["se"] is not None and fit["slope"] + fit["se"] < 0
    horizon = settings["weeks"] * 7
    if is_fading_trend(entry["trend"], settings["min_change"]):
        entry["status"] = "fading"
    elif falling and entry["days_left"] is not None and entry["days_left"] <= horizon:
        entry["status"] = "on course to fade"
    elif fit["slope"] < 0 and exact is not None:
        notes.append("not clearly falling: the line's range includes no fall")
    notes.append(describe_days_left(entry))
    entry["reason"] = "; ".join(notes)
    return entry


def build_calendar(entries: Sequence[Dict[str, Any]], start: dt.date, capacity: int, weeks: int,
                   lead_days: int) -> Dict[str, Any]:
    """Fading ads (largest spend first), then ads on course (soonest fade first), one per slot, earliest week first."""
    fading = sorted((e for e in entries if e["status"] == "fading"), key=lambda e: -(e["spend"] or 0))
    coming = sorted((e for e in entries if e["status"] == "on course to fade"), key=lambda e: e["fade_date"])
    placed, beyond = [], []
    for position, entry in enumerate(fading + coming):
        week = position // capacity
        due = start if entry["status"] == "fading" else dt.date.fromisoformat(entry["fade_date"]) - dt.timedelta(days=lead_days)
        item = {"ad": entry["ad"], "ad_name": entry["ad_name"], "concept": entry["concept"], "format": entry["format"], "status": entry["status"],
                "refresh_due": due.isoformat()}
        if week >= weeks:
            beyond.append(item)
            continue
        slot = start + dt.timedelta(days=7 * week)
        item["slot_week_start"] = slot.isoformat()
        item["late"] = slot > due
        placed.append(item)
    clears = (dt.date.fromisoformat(placed[-1]["slot_week_start"]) + dt.timedelta(days=6)).isoformat() if placed else None
    return {"weeks": [{"week_start": (start + dt.timedelta(days=7 * i)).isoformat(),
                       "refreshes": [p for p in placed if p["slot_week_start"] == (start + dt.timedelta(days=7 * i)).isoformat()]}
                      for i in range(weeks)],
            "beyond_horizon": beyond, "clears_by": clears, "late": sum(p["late"] for p in placed)}


def build_plan(rows: Sequence[Dict[str, Any]], metric: str = "ctr", capacity: Optional[int] = None,
               start: Optional[str] = None, weeks: int = 6, lead_days: int = 7, window: int = 6,
               min_change: float = 8.0, fit_days: int = 9, min_days: int = 9, min_impressions: int = 1000,
               curve_min_ads: int = cm.CURVE_MIN_ADS,
               key_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    metric = cm.resolve_metric(metric)
    if metric not in cm.HIGHER_IS_BETTER:
        raise ValueError("%s cannot show fading, which is read as an ad-level, higher-is-better metric falling; "
                         "use one of: %s" % (metric, ", ".join(cm.HIGHER_IS_BETTER)))
    settings = {"metric": metric, "capacity": capacity, "start": start, "weeks": weeks, "lead_days": lead_days,
                "window": window, "min_change": min_change, "fit_days": fit_days, "min_days": min_days,
                "min_impressions": min_impressions, "curve_min_ads": curve_min_ads}
    first, last = cm.data_window(rows)
    last_date = dt.date.fromisoformat(last) if last else None
    if start:
        start_date: Optional[dt.date] = dt.date.fromisoformat(start)
    else:
        start_date = last_date + dt.timedelta(days=1) if last_date else None
    settings["start"] = start_date.isoformat() if start_date else None
    ads = cm.aggregate_by_ad(rows, key_map)
    base = cm.baseline(ads, metric, ("format",), min_impressions)
    curve = cm.delivery_curve(rows, [metric], curve_min_ads)[metric]
    entries = [judge_ad(rows, ad, metric, base, curve, last_date, settings) for ad in ads]
    counts = {status: sum(e["status"] == status for e in entries) for status in
              ("fading", "on course to fade", "steady", "too little history", "too little delivery", "unreadable")}
    plan: Dict[str, Any] = {"schema": SCHEMA, "settings": settings, "data_window": {"first": first, "last": last},
                            "counts": counts, "ads": entries, "calendar": None}
    if capacity is not None and start_date is not None:
        plan["calendar"] = build_calendar(entries, start_date, capacity, weeks, lead_days)
    return plan


def label(item: Dict[str, Any]) -> str:
    return str(item.get("concept") or item["ad_name"] or item["ad"])


def due_text(item: Dict[str, Any], start: str) -> str:
    if item["status"] == "fading" or item["refresh_due"] <= start:
        return "due now"
    return "due %s" % item["refresh_due"]


def render_calendar(plan: Dict[str, Any]) -> List[str]:
    calendar, start = plan["calendar"], plan["settings"]["start"]
    lines = ["Refresh calendar:"]
    for week in calendar["weeks"]:
        if not week["refreshes"]:
            lines.append("Week of %s: nothing queued" % week["week_start"])
            continue
        parts = ["refresh %s (%s, %s, %s%s)" % (label(i), i["format"] or "unknown format",
                                                 "fading" if i["status"] == "fading" else "on course",
                                                 due_text(i, start), ", late" if i["late"] else "")
                 for i in week["refreshes"]]
        lines.append("Week of %s: %s" % (week["week_start"], "; ".join(parts)))
    if calendar["beyond_horizon"]:
        lines.append("Beyond the horizon: add capacity or extend --weeks: "
                     + ", ".join(label(i) for i in calendar["beyond_horizon"]))
    return lines


def answer_lines(plan: Dict[str, Any]) -> List[str]:
    counts, settings, calendar = plan["counts"], plan["settings"], plan["calendar"]
    fading, coming = counts["fading"], counts["on course to fade"]
    first = "%d %s fading, %d %s on course to fade within %d weeks" % (
        fading, "ad is" if fading == 1 else "ads are", coming, "is" if coming == 1 else "are", settings["weeks"])
    if calendar is None:
        return [first + ".", NO_CALENDAR]
    if calendar["clears_by"] is None:
        return [first + ".", "Nothing is queued for a refresh."]
    second = "at %d refreshes a week the queue clears by %s (%d late)" % (
        settings["capacity"], calendar["clears_by"], calendar["late"])
    if calendar["beyond_horizon"]:
        second += "; %d more do not fit in %d weeks" % (len(calendar["beyond_horizon"]), settings["weeks"])
    return [first + ";", second + "."]


def render(plan: Dict[str, Any]) -> str:
    if not plan["ads"]:
        return "No ads with delivery in this data."
    lines = answer_lines(plan)
    sections = (("fading", "Fading"), ("on course to fade", "On course to fade"), ("steady", "Steady"),
                ("too little history", "Too little history"), ("too little delivery", "Too little delivery"),
                ("unreadable", "Unreadable"))
    for status, title in sections:
        chosen = [e for e in plan["ads"] if e["status"] == status]
        if not chosen:
            continue
        lines.append("%s (%d):" % (title, len(chosen)))
        for e in chosen:
            lines.append("  %s (%s): %s" % (label(e), e["format"] or "unknown format", e["reason"]))
    if plan["calendar"] is not None:
        lines += [""] + render_calendar(plan)
    return "\n".join(lines)


def check_settings(args: argparse.Namespace) -> None:
    checks = (("--capacity", args.capacity, 1), ("--weeks", args.weeks, 1), ("--lead-days", args.lead_days, 0),
              ("--window", args.window, 1), ("--fit-days", args.fit_days, 2), ("--min-days", args.min_days, 1))
    for flag, value, least in checks:
        if value is not None and value < least:
            raise ValueError("%s must be a whole number of at least %d" % (flag, least))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Which ads are fading, which are on course to, and a refresh calendar.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--metric", default="ctr",
                        help="rate metric to follow, higher is better (default: ctr); hook_rate is read too for video ads")
    parser.add_argument("--capacity", type=int,
                        help="refreshes the team can produce per week (a whole number of 1 or more); "
                             "required for the calendar")
    parser.add_argument("--start", help="first calendar day, YYYY-MM-DD (default: the day after the data's last date)")
    parser.add_argument("--weeks", type=int, default=6, help="calendar horizon in weeks (arbitrary default)")
    parser.add_argument("--lead-days", type=int, default=7,
                        help="days a refresh needs from brief to live (arbitrary default)")
    parser.add_argument("--window", type=int, default=6,
                        help="days compared at the start and end of an ad's life, and days checked against the "
                             "band (arbitrary default)")
    parser.add_argument("--min-change", type=float, default=8.0,
                        help="percent move that counts as real (arbitrary default)")
    parser.add_argument("--fit-days", type=int, default=9,
                        help="delivery days the straight-line fit uses (arbitrary default)")
    parser.add_argument("--min-days", type=int, default=9,
                        help="fewest delivery days before an ad gets a trajectory (arbitrary default)")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are not judged (arbitrary default)")
    parser.add_argument("--curve-min-ads", type=int, default=cm.CURVE_MIN_ADS,
                        help="ads needed for a delivery-day band (arbitrary default)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        check_settings(args)
        if args.start:
            dt.date.fromisoformat(args.start)
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        plan = build_plan(rows, args.metric, args.capacity, args.start, args.weeks, args.lead_days, args.window,
                          args.min_change, args.fit_days, args.min_days, args.min_impressions,
                          args.curve_min_ads, key_map)
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    plan["run_notes"] = run_notes
    print(json.dumps(plan, indent=2) if args.json else "\n".join(run_notes + [render(plan)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
