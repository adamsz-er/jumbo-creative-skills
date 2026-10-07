#!/usr/bin/env python3
"""A pause / check / iterate / scale / keep verdict per ad, with confidence, a plain-English sentence and fatigue trend.

Usage: python3 verdicts.py ads.csv [--young-days 5] [--window 6] [--min-change 8] [--top-n 3] [--group-by format,ad_type] [--key-map PX=concept] [--json]

Standard library only. Needs daily rows (one row per ad per day) for fatigue.
--young-days, --window, --min-impressions, --min-change, --top-n, --protect-top
and the minimum group size are arbitrary defaults: set them from your own
account (how long ads take to stabilise, how much a week-to-week wobble moves
your numbers). --min-change is a materiality size, not a fatigue benchmark.
Every grade is relative to the account's own ads of the same campaign objective.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

CHECK = ("rule out tracking, site or audience problems first; "
         "only fatigue and never-worked are creative decisions")
# verdict id -> what the user reads. `verdict` in the JSON is the label; `verdict_id` is stable.
LABELS = {
    "scale": "Scale: raise budget in steps",
    "keep": "Keep",
    "check_mixed": "Check before cutting",
    "check_top_seller": "Check before cutting",
    "check_immature": "Check before cutting",
    "check_feeds": "Check before cutting",
    "iterate": "Iterate: refresh the hook or creator, keep the concept",
    "pause_fatigued": "Pause: fatigued",
    "pause_never_worked": "Pause: never worked",
    "cant_judge": "Can't judge",
    "too_early": "Too early (learning)",
}
# summary group -> name, in display order
GROUPS = (("scale", "Scale"), ("keep", "Keep"), ("check", "Check before cutting"), ("iterate", "Iterate"),
          ("pause", "Pause"), ("cant_judge", "Can't judge"), ("too_early", "Too early"))
GROUP_NAME = dict(GROUPS)
ACT_ON = ("pause", "check", "iterate", "scale")
ATTENTION = ("hook_rate", "ctr")
NOUN = {"sales": "purchase", "traffic": "click", "awareness": "impression", "leads": "lead", "engagement": "engagement"}
DO_FIRST = 5  # arbitrary default: how many actions lead the list, set from how many you can act on
PROTECT_TOP = 3  # arbitrary default: the biggest sellers are never paused unchecked
CONFIDENT, EARLY_READ, CANT_JUDGE_YET = "Confident", "Early read", "Can't judge yet"
BOTTOM, TOP = cm.BAND_BOTTOM, cm.BAND_TOP


def group_of(verdict_id: str) -> str:
    """The summary group of a verdict id: pause_fatigued -> pause, check_mixed -> check."""
    head = verdict_id.split("_")[0]
    return head if head in ("pause", "check") else verdict_id


def _key(ad: Dict[str, Any]) -> Optional[str]:
    return ad.get("ad_id") or ad.get("ad_name")


def _payback(ad: Dict[str, Any], pool: Sequence[Dict[str, Any]], metrics: Sequence[str],
             group_by: Sequence[str], min_impressions: int) -> Dict[str, Any]:
    """Grade an ad on the payback metrics of its objective, each against the narrowest big-enough group.

    A metric that cannot be graded is named in `missing`, never counted as weak or fine.
    """
    grades = {m: cm.grade_with_fallback(ad, pool, m, group_by, min_impressions) for m in metrics}
    graded = {m: g for m, g in grades.items() if not g["band"].startswith("not graded")}
    bands = [g["band"] for g in graded.values()]
    sizes = [g["group_size"] for g in graded.values() if g["group_size"] is not None]
    return {
        "graded": list(graded), "known": bool(bands),
        "all_bottom": bool(bands) and all(b == BOTTOM for b in bands),
        "all_top": bool(bands) and all(b == TOP for b in bands),
        "mixed": TOP in bands and BOTTOM in bands,
        "bands": {m: g["band"] for m, g in grades.items()},
        "group_size": min(sizes) if sizes else None,
        "thin": any(cm.is_thin(n) for n in sizes),
        "group": next((g["group_value"] for g in graded.values()), None),
        "group_by": next((g["group_by"] for g in graded.values()), None),
        "fallbacks": sorted({g["fallback"] for g in graded.values() if g["fallback"]}),
        "missing": {m: g["band"][len("not graded ("):-1] for m, g in grades.items() if m not in graded},
    }


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


def _money(value: Optional[float], currency: Optional[str]) -> str:
    return "n/a" if value is None else "%s%.2f" % (currency + " " if currency else "", value)


def _clause(metric: str, value: Optional[float], currency: Optional[str]) -> str:
    """What an ad's number says, as a predicate after "it": costs X per sale, has a click-through rate of Y."""
    if value is None:
        return "has no %s" % metric
    if metric == "cpa":
        return "costs %s per sale" % _money(value, currency)
    if metric == "cost_per_lead":
        return "costs %s per lead" % _money(value, currency)
    if metric == "cpc":
        return "costs %s per click" % _money(value, currency)
    if metric == "cpm":
        return "costs %s per 1,000 impressions" % _money(value, currency)
    if metric == "roas":
        return "returns %.2f for every %s spent" % (value, "%s1" % (currency + " " if currency else ""))
    if metric == "ctr":
        return "has a click-through rate of %.2f%%" % value
    if metric == "hook_rate":
        return "has a hook rate of %.1f%%" % value
    return "has an engagement rate of %.2f%%" % value


def _versus(metric: str, band: str, pool_word: str) -> str:
    """A plain comparison with the ad's own comparison group, never a benchmark."""
    worse = band == BOTTOM
    if metric in cm.LOWER_IS_BETTER:
        word = "more" if worse else "less"
    else:
        word = "lower" if worse else "higher"
    return "%s than most of your %s ads" % (word, pool_word)


def _first_with(pb: Dict[str, Any], band: str) -> Optional[str]:
    return next((m for m, b in pb["bands"].items() if b == band), None)


def _mixed_reason(pb: Dict[str, Any]) -> str:
    top, bottom = _first_with(pb, TOP), _first_with(pb, BOTTOM)
    if (top, bottom) == ("cpa", "roas"):
        return "it costs little per sale but sales are small: check order value before cutting"
    if (top, bottom) == ("roas", "cpa"):
        return "each sale costs more to win but brings back more: check margin before cutting"
    return "%s is among your best but %s is among your weakest: find out why before cutting" % (top, bottom)


def _compare(metric: str, value: Optional[float], band: str, pool_word: str, cur: Optional[str]) -> str:
    """"costs X per sale, more than most of your similar ads", or the no-sales case on its own."""
    if metric == "roas" and value == 0:
        return "has not brought back any sales"
    return "%s, %s" % (_clause(metric, value, cur), _versus(metric, band, pool_word))


def _sentence(vid: str, ad: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """One plain sentence leading with the action, with numbers from the data and no statistics jargon."""
    cur, pb = ctx["currency"], ctx["payback"]
    if vid == "too_early":
        return "Too early to judge: %s." % ctx["why"]
    if vid == "cant_judge":
        return "Can't judge yet: %s." % ctx["why"]
    metric = next((m for m, b in pb["bands"].items() if not b.startswith("not graded")), None)
    value = ad.get(metric)
    pool_word = "similar" if pb["group_by"] else ctx["objective"]
    days = ctx.get("delivery_days")
    span = ("%d days" % days) if days else "this long"
    if vid == "pause_never_worked":
        text = "Pause it: after %s it %s, and it was weak from the start." % (
            span, _compare(metric, value, BOTTOM, pool_word, cur))
    elif vid == "pause_fatigued":
        text = "Pause it: it is wearing out (more repeat views, fewer people reacting) and it %s." % (
            _compare(metric, value, BOTTOM, pool_word, cur))
    elif vid == "iterate":
        text = ("Refresh it, keep the idea: people are tiring of it (more repeat views, fewer clicks), "
                "but its payback is not weak. Change the opening or the creator.")
    elif vid == "scale":
        text = "Scale it gradually: it %s, and it is not showing signs of wearing out." % (
            _compare(metric, value, TOP, pool_word, cur))
    elif vid == "check_mixed":
        text = "Check before cutting: %s." % _mixed_reason(pb)
    elif vid == "check_immature":
        text = ("Check before cutting: it looks weak, but it has only delivered %d days, too few to be sure "
                "against so small a comparison group." % ctx["delivery_days"])
    elif vid == "check_top_seller":
        text = ("Check before cutting: it looks weak, but it is one of your account's biggest sellers. "
                "Find out why before touching it.")
    elif vid == "check_feeds":
        text = ("Check before cutting: it catches attention (%s) but pays back weakly. "
                "See whether it feeds your other ads first." % " and ".join(ctx["strong"]))
    else:
        text = "Keep it running: %s." % ctx["why"]
    if pb["thin"]:
        text += " Early read: small comparison group (%d similar ads)." % pb["group_size"]
    return text


def _confidence(vid: str, entry: Dict[str, Any], pb: Optional[Dict[str, Any]], window: int) -> Tuple[str, str]:
    if vid == "too_early":
        return CANT_JUDGE_YET, "still learning"
    if vid == "cant_judge":
        return CANT_JUDGE_YET, "payback cannot be graded"
    problems = []
    if pb["thin"]:
        problems.append("small comparison group: only %d similar ads" % pb["group_size"])
    days = entry.get("active_days")
    if days is None or days < 2 * window:
        problems.append("%s delivery days, under two %d-day windows" % ("unknown" if days is None else days, window))
    if len(pb["graded"]) < 2:
        problems.append("one payback measure only (%s)" % ", ".join(pb["graded"]))
    elif pb["mixed"]:
        problems.append("payback measures disagree")
    if problems:
        return EARLY_READ, "; ".join(problems)
    return CONFIDENT, "enough comparable ads and delivery days, and the payback measures agree"


def _objective_of(ad: Dict[str, Any]) -> str:
    return cm.payback_metrics(ad.get("objective"))["objective"]


def judge_ads(rows: Sequence[Dict[str, Any]], young_days: int = 5, window: int = 6,
              min_impressions: int = 1000, min_change: float = 8.0,
              group_by: Optional[Sequence[str]] = None,
              key_map: Optional[Dict[str, str]] = None, protect_top: int = PROTECT_TOP,
              currency: Optional[str] = None) -> List[Dict[str, Any]]:
    """One verdict per ad, first matching rule wins, every verdict lists its reasons.

    Each ad is judged on the payback measures of its campaign objective, against
    ads of the same objective, in the narrowest group (default format then ad
    type) with enough comparable ads.
    """
    ads = cm.aggregate_by_ad(rows, key_map=key_map)
    group_by, _ = cm.default_group_by(ads, group_by)
    first_ads = cm.window_aggregate(rows, window, "first", key_map=key_map)
    first_by_key = {_key(a): a for a in first_ads}
    seller_keys = set()
    for field in ("conversions", "conversion_value"):
        values = sorted((a[field] for a in ads if (a.get(field) or 0) > 0), reverse=True)
        if protect_top > 0 and values:
            cutoff = values[min(protect_top, len(values)) - 1]
            seller_keys.update(_key(a) for a in ads if (a.get(field) or 0) >= cutoff and (a.get(field) or 0) > 0)
    results = []
    for ad in ads:
        key = _key(ad)
        age = ad["age_days"]
        info = cm.payback_metrics(ad.get("objective"))
        objective, metrics = info["objective"], info["metrics"]
        low_volume = (ad.get("impressions") or 0) < min_impressions
        learning = low_volume or (age is not None and age < young_days)
        entry: Dict[str, Any] = {
            "ad": key, "ad_id": ad.get("ad_id"), "ad_name": ad.get("ad_name"),
            "format": ad.get("format"), "spend": ad.get("spend"), "spend_at_stake": ad.get("spend"),
            "age_days": age, "age_basis": ad.get("age_basis"),
            "active_days": ad.get("active_days"), "learning": learning, "check": None,
            "objective": objective, "objective_assumed": info["assumed"],
            "payback_basis": info["what"] + (" (%s)" % info["note"] if info["note"] else ""),
        }
        ctx: Dict[str, Any] = {"currency": currency, "objective": objective, "payback": None}
        if learning:
            why = ("under %d impressions" % min_impressions) if low_volume else \
                  "%d days old, under the %d-day learning window" % (age, young_days)
            vid = "too_early"
            ctx["why"] = ("it has " if low_volume else "it is ") + why
            entry.update(verdict_id=vid, verdict=LABELS[vid], fatiguing=False, fatigue=None, payback=None,
                         group=None, group_size=None, thin=False,
                         reasons=["learning: " + why, "no other verdict until it has delivered longer"])
            entry["confidence"], entry["confidence_reason"] = _confidence(vid, entry, None, window)
            entry["sentence"] = _sentence(vid, ad, ctx)
            results.append(entry)
            continue

        pool = [a for a in ads if _objective_of(a) == objective]
        first_pool = [a for a in first_ads if _objective_of(a) == objective]
        fatigue = _fatigue(rows, key, window, min_change)
        pb = _payback(ad, pool, metrics, group_by, min_impressions)
        account = _payback(ad, pool, metrics, (), min_impressions)
        first = first_by_key.get(key)
        first_bottom = bool(first) and _payback(first, first_pool, metrics, group_by, min_impressions)["all_bottom"]
        attention = {m: cm.grade_with_fallback(ad, pool, m, group_by, min_impressions)["band"] for m in ATTENTION}
        strong = [m for m, band in attention.items() if band == TOP]
        ctx.update(payback=pb, strong=strong, delivery_days=ad.get("active_days"))

        reasons = []
        if age is None:
            reasons.append("age unknown (no dates in the data)")
        if info["note"]:
            reasons.append(info["note"])
        reasons.append("payback measured by %s" % info["what"])
        if "cpc" in metrics:
            basis = cm.metric_basis(ad, "cpc")["denominator"]
            if basis:
                reasons.append("cost per click counts %s, the click type ctr uses" % basis)
        reasons.append("payback: " + ", ".join("%s %s" % (m, b) for m, b in pb["bands"].items()))
        if pb["known"]:
            reasons.append("compared with %s: %s (%d comparable ads)%s" % (
                " / ".join(pb["group_by"]) or "all ads", pb["group"], pb["group_size"],
                "; " + "; ".join(pb["fallbacks"]) if pb["fallbacks"] else ""))
        if fatigue["status"] == "ok":
            reasons.append("trend over first vs last %d delivery days: ctr %s, frequency %s, hook rate %s "
                           "(fatigue needs ctr down %g%%+ and frequency up %g%%+ or hook down %g%%+)" % (
                               window, _pct(fatigue["ctr_change"]), _pct(fatigue["frequency_change"]),
                               _pct(fatigue["hook_change"]), min_change, min_change, min_change))
        else:
            reasons.append("fatigue not readable: " + fatigue["note"])
        fatiguing = fatigue["fatiguing"]
        suffix = ""

        pause = None
        if pb["all_bottom"] and fatiguing:
            pause = "pause_fatigued"
        elif pb["all_bottom"] and first_bottom:
            pause = "pause_never_worked"

        if not pb["known"]:
            vid = "cant_judge"
            gaps = sorted(set(pb["missing"].values()))
            if any(g.startswith("too little comparison") for g in gaps):
                size = next((cm.grade_with_fallback(ad, pool, m, group_by, min_impressions).get("n_comparable")
                             for m in metrics), None)
                ctx["why"] = "only %s comparable %s ads, too few to compare it against" % (size or 0, objective)
                suffix = ": too few comparable ads"
            elif any(g.startswith("no spread") for g in gaps):
                ctx["why"] = "its comparison group has no spread (the ads look the same), so there is nothing to judge it against"
                suffix = ": no spread in group"
            elif "missing spend" in gaps:
                ctx["why"] = "the data has no spend for this ad"
                suffix = ": missing spend"
            else:
                ctx["why"] = "the data has no %s numbers for this ad" % NOUN[objective]
                suffix = ": " + ", ".join(gaps)
            reasons.append("payback not gradable: " + "; ".join("%s %s" % kv for kv in pb["missing"].items()))
            if fatigue["status"] == "ok":
                reasons.append("fatigue is shown as context only: it does not make a decision without payback")
        elif fatiguing and not pb["all_bottom"]:
            vid = "iterate"
            reasons.append("fatiguing, but payback is not weak on every measure: the concept still earns")
        elif pb["mixed"]:
            vid = "check_mixed"
            reasons.append("payback measures disagree: " + _mixed_reason(pb))
        elif pause and pb["thin"] and (entry["active_days"] or 0) < 2 * window:
            vid = "check_immature"
            reasons.append("would be paused, but the comparison group is small and it has delivered %s days, under two "
                           "%d-day windows" % (entry["active_days"], window))
        elif pause:
            if not account["all_bottom"]:
                vid = "keep"
                ctx["why"] = "weak against similar ads but not against all your %s ads: watch it" % objective
                reasons.append("bottom quartile in its group but not on every measure account-wide within "
                               "objective %s: watch it" % objective)
            elif key in seller_keys:
                vid = "check_top_seller"
                reasons.append("would be paused, but it is one of the account's top %d by purchases or purchase "
                               "value (one of the account's biggest sellers)" % protect_top)
            else:
                vid = pause
                reasons.append("payback is bottom quartile on every measure, in its group and account-wide within "
                               "its objective" + (", and was bottom in the first %d delivery days too" % window
                                                  if pause == "pause_never_worked" else ", and it is fatiguing"))
        elif pb["all_top"] and fatigue["status"] == "ok" and not fatiguing:
            vid = "scale"
            reasons.append("payback is top quartile and the ad is not fatiguing; "
                           "set the step size from your own account's history")
        elif strong and pb["all_bottom"]:
            vid = "check_feeds"
            reasons.append("%s top quartile but payback is bottom quartile" % " and ".join(strong))
        else:
            vid = "keep"
            if pb["all_top"]:
                ctx["why"] = "payback is strong but there are too few days to rule out wearing out, so hold off scaling"
                reasons.append("payback is top quartile but fatigue is not readable yet: hold before scaling")
            elif pb["all_bottom"]:
                ctx["why"] = "payback is weak now but was not from the start and it is not wearing out: watch it"
                reasons.append("payback is bottom quartile but not from the start and not fatiguing: watch it")
            else:
                ctx["why"] = "nothing here says to change it yet"
        ctx.setdefault("why", "nothing here says to change it yet")
        if vid == "scale" and ad.get("ad_type") == "promo":
            reasons.append("promo: strong payback can be existing demand being harvested; check "
                           "new-customer share and the sale end date before raising budget")
        entry.update(verdict_id=vid, verdict=LABELS[vid] + suffix, fatiguing=fatiguing, fatigue=fatigue,
                     payback=pb, attention=attention, reasons=reasons, group=pb["group"],
                     group_size=pb["group_size"], thin=pb["thin"],
                     check=CHECK if vid.startswith("pause") else None)
        entry["confidence"], entry["confidence_reason"] = _confidence(vid, entry, pb, window)
        entry["sentence"] = _sentence(vid, ad, ctx)
        results.append(entry)
    return results


def _stake(entry: Dict[str, Any]) -> float:
    return entry.get("spend_at_stake") or 0.0


def do_first(results: Sequence[Dict[str, Any]], limit: int = DO_FIRST) -> List[Dict[str, Any]]:
    """The ads to act on first: largest spend at stake across pause, check, iterate and scale. Never can't-judge."""
    pool = [e for e in results if group_of(e["verdict_id"]) in ACT_ON]
    return [{k: e[k] for k in ("ad", "ad_name", "verdict", "verdict_id", "spend_at_stake", "confidence", "sentence")}
            for e in sorted(pool, key=lambda e: -_stake(e))[:limit]]


def summarise(results: Sequence[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    """Verdict counts, ads that are too young, thin groups, spend concentration and the do-these-first list.

    top_n=3 is an arbitrary default: set your own from how many ads you run.
    """
    counts: Dict[str, int] = {}
    for entry in results:
        name = GROUP_NAME[group_of(entry["verdict_id"])]
        counts[name] = counts.get(name, 0) + 1
    share = cm.concentration(results, top_n=top_n)
    if share is None:
        line = "top %d ads (N=%d, an arbitrary default: set your own) hold n/a of spend (no spend in the data)" % (top_n, top_n)
    else:
        line = ("top %d ads (N=%d, an arbitrary default: set your own) hold %.0f%% of spend. Heavy "
                "concentration means one fatigue event hurts the whole account; judge it against "
                "your own history." % (top_n, top_n, share))
    thin: Dict[str, int] = {}
    for entry in results:
        if entry.get("thin") and entry.get("group"):
            thin["%s, %s objective" % (entry["group"], entry["objective"])] = entry["group_size"]
    return {"counts": counts, "too_young": [e["ad"] for e in results if e["learning"]],
            "concentration_line": line, "do_first": do_first(results),
            "thin_groups": [{"group": k, "ads": v} for k, v in sorted(thin.items())]}


def render(results: Sequence[Dict[str, Any]], args: argparse.Namespace, rows: Sequence[Dict[str, Any]],
           group_by: Sequence[str] = ("format",), group_note: Optional[str] = None,
           currency: Optional[str] = None) -> str:
    summary = summarise(results, args.top_n)
    start, end = cm.data_window(rows)
    out = [
        "Basis: each ad graded against this account's own ads of the same campaign objective (same %s group, "
        "widening when a group has under %d comparable ads), never a benchmark." % (", ".join(group_by), cm.MIN_GROUP),
        "Window: %s to %s. Fatigue compares each ad's first and last %d delivery days." % (
            start or "n/a", end or "n/a", args.window),
        "Settings used (arbitrary defaults, set them from your own account): young-days=%d, window=%d, "
        "min-impressions=%d, top-n=%d, protect-top=%d, min-change=%g%% (a materiality size for ctr, frequency and hook movement, "
        "not a fatigue benchmark: set it from your own week-to-week noise)." % (
            args.young_days, args.window, args.min_impressions, args.top_n, args.protect_top, args.min_change),
        "Money is shown in %s." % (currency or "the account's own currency (the export did not name one)"),
    ]
    if group_note:
        out.append("Grouping: " + group_note + ".")
    assumed = [e["ad"] for e in results if e.get("objective_assumed")]
    if assumed:
        out.append("Objective: not in the data (or not a known objective) for %d ads, so they are judged as sales: "
                   "add an objective column to judge each ad on its own goal." % len(assumed))
    if summary["thin_groups"]:
        out.append("WARNING small comparison groups (fewer than twice the %d-ad minimum; their verdicts are an early read at most): %s." % (
            cm.MIN_GROUP, ", ".join("%s n=%d" % (t["group"], t["ads"]) for t in summary["thin_groups"])))
    bases = sorted({e["age_basis"] for e in results if e.get("age_basis")})
    out.append("Age basis: %s." % ("; ".join(bases) or "n/a (no dates in the data)"))
    derived = sorted({r["video_views_3s_source"] for r in rows
                      if (r.get("video_views_3s_source") or "").startswith("derived")})
    if derived:
        out.append("Hook rate (used in the fatigue trend): 3-second plays are %s." % derived[0])
    out += ["", "Summary:"]
    for _, name in GROUPS:
        if name in summary["counts"]:
            out.append("  %-24s %d" % (name, summary["counts"][name]))
    out.append("  too young to judge: %s" % (", ".join(summary["too_young"]) or "none"))
    out.append("  " + summary["concentration_line"])
    if summary["do_first"]:
        out += ["", "Do these first (largest spend at stake; an ad that cannot be judged never leads):"]
        for item in summary["do_first"]:
            out.append("  %s  %s  spend %s  [%s]" % (item["ad"], item["verdict"],
                                                   _money(item["spend_at_stake"], currency), item["confidence"]))
    out += ["", "Verdicts (largest spend at stake first within each):"]
    for gid, _ in GROUPS:
        for entry in sorted((e for e in results if group_of(e["verdict_id"]) == gid), key=lambda e: -_stake(e)):
            out.append("%s  [%s]  age %s d, %s  (spend %s)" % (
                entry["ad"], entry["format"] or "-", "n/a" if entry["age_days"] is None else entry["age_days"],
                entry["verdict"], _money(entry["spend_at_stake"], currency)))
            out.append("    " + entry["sentence"])
            out.append("    confidence: %s (%s)" % (entry["confidence"], entry["confidence_reason"]))
            out += ["    - " + r for r in entry["reasons"]]
            if entry["check"]:
                out.append("    ! check first: " + entry["check"])
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pause, check, iterate, scale or keep: a verdict per ad.")
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
    parser.add_argument("--group-by", default=None,
                        help="comma-separated columns to compare within, widest fallback last: a name field or any "
                             "column in the data (default: format,ad_type)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    parser.add_argument("--top-n", type=int, default=3,
                        help="how many top-spend ads the concentration line counts (arbitrary default)")
    parser.add_argument("--protect-top", type=int, default=PROTECT_TOP,
                        help="the account's top N ads by purchases or purchase value are never paused "
                             "unchecked (arbitrary default)")
    parser.add_argument("--currency", help="three-letter currency code for money; default: read from the export's spend header")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    rows = cm.load_rows(args.path)
    explicit = tuple(g.strip() for g in args.group_by.split(",") if g.strip()) if args.group_by else None
    currency = args.currency or cm.detect_currency(args.path)
    try:
        key_map = cm.parse_key_map(args.key_map) if args.key_map else None
        group_by, group_note = cm.default_group_by(cm.aggregate_by_ad(rows, key_map=key_map), explicit)
        results = judge_ads(rows, args.young_days, args.window, args.min_impressions, args.min_change,
                            group_by, key_map, args.protect_top, currency)
    except (cm.GroupColumnError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"summary": summarise(results, args.top_n),
                          "settings": dict(vars(args), group_by=",".join(group_by), currency=currency),
                          "group_note": group_note, "ads": results}, indent=2))
    else:
        print(render(results, args, rows, group_by, group_note, currency))
    return 0


if __name__ == "__main__":
    sys.exit(main())
