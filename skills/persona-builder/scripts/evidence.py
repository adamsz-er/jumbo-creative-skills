#!/usr/bin/env python3
"""Account evidence for the make skills, from the account's own ads.

Usage: python3 evidence.py ads.csv [--for brief|persona|hooks|ideation] [--segment adset_name]
                           [--verdicts verdicts.json] [--competitor scan.json]
                           [--include-types bau,promo] [--window 6] [--min-change 8] [--max-gaps 8] [--json]

Standard library only. One evidence set (schema 1) feeds creative-brief, persona-builder, hook-writer and
creative-ideation, so every idea, hook or persona can name the ads it came from. The brief view lists the
account's top-quartile ads with the fields parsed from their names, the ads that are fatiguing or never
worked, and concept x format cells with no ad beside a top-quartile ad. The persona view shows results by
persona or audience; the hooks view, the openings that stop people and the ones that do not; the ideation
view, concept and format coverage with spend share and age. Every judgement is relative to this account's
own ads in the same format, never a benchmark. --window, --min-change, --max-gaps and --top are arbitrary
defaults: set them from your own account. With no usable rows it prints "Evidence: none available".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

SCHEMA = 1
NONE_AVAILABLE = "Evidence: none available"
UNBACKED = ("No account data: everything below is unbacked, from the brand profile and craft, not results. "
            "Say so beside every idea, hook or persona.")
PAYBACK = ("cpa", "roas")
ATTENTION = ("hook_rate", "hold_rate", "ctr")
FIELDS = ("concept", "format", "creator", "ad_type", "product", "tone")
SEGMENT_FIELDS = ("persona", "audience", "adset_name")  # read in this order when --segment is not given
OPENING_COLUMNS = ("primary_text", "body", "ad_body", "body_text", "headline", "title", "ad_title")
OPENING_CHARS = 90  # arbitrary: where an opening line is cut, at a word boundary
TOP_N = 6  # arbitrary default: openings listed at each end of the hooks view
VIEWS = ("brief", "persona", "hooks", "ideation")


def _key(ad: Dict[str, Any]) -> Optional[str]:
    return ad.get("ad_id") or ad.get("ad_name")


def _summary(ad: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ad": _key(ad), "ad_name": ad.get("ad_name")}
    out.update({f: ad.get(f) for f in FIELDS})
    out.update(roas=ad.get("roas"), cpa=ad.get("cpa"), spend=ad.get("spend"), age_days=ad.get("age_days"))
    return out


def _bands(ad: Dict[str, Any], ads: Sequence[Dict[str, Any]], min_impressions: int,
           metrics: Sequence[str] = PAYBACK) -> Dict[str, str]:
    return {m: cm.grade_against(ad, ads, m, ("format",), min_impressions)["band"] for m in metrics}


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
            "ctr_change": ctr_change, "frequency_change": freq_change, "hook_change": hook_change,
            "hook_faded": hook_down}


def _opening(ad: Dict[str, Any]) -> Optional[str]:
    text = next((ad[c] for c in OPENING_COLUMNS if isinstance(ad.get(c), str) and ad[c].strip()), None)
    if text is None:
        return None
    line = text.strip().splitlines()[0].strip()
    if len(line) <= OPENING_CHARS:
        return line
    return line[:OPENING_CHARS].rsplit(" ", 1)[0] + "..."


def _verdicts(path_or_data: Any) -> Dict[str, Dict[str, Any]]:
    """{ad: {verdict_id, verdict, confidence}} from keep-or-kill --json output (a path or the loaded dict)."""
    data = path_or_data
    if isinstance(path_or_data, (str, Path)):
        data = json.loads(Path(path_or_data).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("ads"), list):
        raise ValueError("--verdicts must be keep-or-kill --json output (an object with an \"ads\" list)")
    return {str(a.get("ad")): {"verdict_id": a.get("verdict_id"), "verdict": str(a.get("verdict") or "").split(":")[0] or None,
                               "confidence": a.get("confidence")} for a in data["ads"] if a.get("ad")}


def _competitor(path_or_data: Any) -> Dict[str, Any]:
    """The parts of a competitor-scan --json result the make skills read."""
    data = path_or_data
    if isinstance(path_or_data, (str, Path)):
        data = json.loads(Path(path_or_data).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "clusters" not in data:
        raise ValueError("--competitor must be competitor-scan --json output (an object with \"clusters\")")
    return {k: data.get(k) for k in ("source", "advertisers", "ads", "clusters", "open_ground", "crowded", "worth_testing",
                                     "not_to_chase")}


SEGMENT_RATES = ("roas", "cpa", "ctr", "hook_rate", "new_customer_purchase_share")


def _segment_field(ads: Sequence[Dict[str, Any]], segment: Optional[str]) -> Optional[str]:
    if segment:
        return cm.resolve_group_by(ads, [segment])[0]
    return next((f for f in SEGMENT_FIELDS if any(isinstance(a.get(f), str) and a[f] for a in ads)), None)


def _pooled(ads: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    total: Dict[str, Optional[float]] = {}
    for field in cm.NUMERIC_FIELDS:
        values = [a[field] for a in ads if a.get(field) is not None]
        total[field] = sum(values) if values else None
    total["reach"] = None
    return dict(total, **cm.compute_metrics(total))


def _spend_of(items: Sequence[Dict[str, Any]]) -> Tuple[Optional[float], int]:
    """Spend summed over only the items that report it, and how many do: a missing spend is never a zero."""
    values = [i["spend"] for i in items if i.get("spend") is not None]
    return (sum(values) if values else None), len(values)


def _spend_share(spend: Optional[float], total_spend: Optional[float]) -> Optional[float]:
    return spend / total_spend * 100 if spend is not None and total_spend else None


def _rate_over_reporting(ads: Sequence[Dict[str, Any]], metric: str) -> Tuple[Optional[float], int]:
    """A rate pooled over only the ads that report both fields it needs, and how many of them there are: an ad
    without a field never counts as a zero, while a reported zero (an ad with no sales) still counts."""
    reporting = [a for a in ads if None not in cm.rate_counts(a, metric)]
    return (_pooled(reporting)[metric] if reporting else None), len(reporting)


def _relative(value: Optional[float], account: Optional[float]) -> Optional[float]:
    """The segment's rate as a percent of the account's own pooled rate (100 = the same)."""
    return None if value is None or not account else value / account * 100


def _segments(ads: Sequence[Dict[str, Any]], records: Dict[str, Dict[str, Any]], field: Optional[str],
              total_spend: float) -> Dict[str, Any]:
    if field is None:
        return {"field": None, "rows": [],
                "note": "no persona or audience tag in the data (no persona name field, audience or ad set column): "
                        "personas cannot be read from results; build them from the profile and say they are unbacked"}
    account = {m: _rate_over_reporting(ads, m)[0] for m in SEGMENT_RATES}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ad in ads:
        groups.setdefault(str(ad.get(field) or "untagged"), []).append(ad)
    out = []
    for value, members in groups.items():
        pooled = _pooled(members)
        rates = {m: _rate_over_reporting(members, m) for m in SEGMENT_RATES}
        nc_share, nc_ads = rates["new_customer_purchase_share"]
        recs = [records[str(_key(a))] for a in members]
        out.append({
            "value": value, "ads": len(members), "ad_ids": [str(_key(a)) for a in members],
            "spend": pooled["spend"], "spend_share": _spend_share(pooled["spend"], total_spend),
            "spend_reported": _spend_of(members)[1],
            "conversions": pooled["conversions"], **{m: rates[m][0] for m in ("roas", "cpa", "ctr", "hook_rate")},
            "roas_vs_account": _relative(rates["roas"][0], account["roas"]),
            "cpa_vs_account": _relative(rates["cpa"][0], account["cpa"]),
            "new_customer_purchase_share": nc_share,
            "new_customer_note": ("n/a (%s)" % (cm.describe_missing(pooled, "new_customer_purchase_share") if not nc_ads
                                                    else "missing purchases: the ads that report new customers have none")
                                  if nc_share is None else None if nc_ads == len(members) else
                                  "over the %d of %d ads that report new customers" % (nc_ads, len(members))),
            "top_quartile_ads": [r["ad"] for r in recs if r["payback_top"]],
            "bottom_quartile_ads": [r["ad"] for r in recs if r["payback_bottom"]],
            "concepts": sorted({str(a.get("concept")) for a in members if a.get("concept")}),
        })
    out.sort(key=lambda r: -(r["spend"] or 0))
    return {"field": field, "rows": out, "note": None,
            "account": {"roas": account["roas"], "cpa": account["cpa"],
                        "new_customer_purchase_share": account["new_customer_purchase_share"]}}


def _angles(records: Sequence[Dict[str, Any]], total_spend: float) -> List[Dict[str, Any]]:
    by_concept: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        if rec.get("concept"):
            by_concept.setdefault(str(rec["concept"]), []).append(rec)
    out = []
    for concept, recs in by_concept.items():
        judged = [r for r in recs if r["judged"]]
        top = [r["ad"] for r in judged if r["payback_top"]]
        bottom = [r["ad"] for r in judged if r["payback_bottom"]]
        never = [r["ad"] for r in judged if r["never_worked"]]
        spend, spend_reported = _spend_of(recs)
        if not judged:
            label = "unjudged"
        elif top and not never and not bottom:
            label = "winning"
        elif (never or bottom) and not top:
            label = "losing"
        elif top:
            label = "mixed"
        elif any(not b.startswith("not graded") for r in judged for b in r["bands"].values()):
            label = "middle"
        else:
            label = "ungraded"
        out.append({"concept": concept, "label": label, "ads": [r["ad"] for r in recs],
                    "formats": sorted({str(r["format"]) for r in recs if r.get("format")}),
                    "spend_share": _spend_share(spend, total_spend), "spend_reported": spend_reported,
                    "top_quartile_ads": top, "bottom_quartile_ads": bottom, "never_worked_ads": never,
                    "fatiguing_ads": [r["ad"] for r in recs if r["fatigue"].get("fatiguing")],
                    "youngest_age_days": min((r["age_days"] for r in recs if r["age_days"] is not None), default=None)})
    order = {"winning": 0, "mixed": 1, "middle": 2, "losing": 3, "ungraded": 4, "unjudged": 5}
    out.sort(key=lambda a: (order[a["label"]], -(a["spend_share"] or 0), a["concept"]))
    return out


def _hooks(records: Sequence[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
    graded = [r for r in records if r["judged"] and r["hook_band"] in (cm.BAND_TOP, cm.BAND_MID, cm.BAND_BOTTOM)]
    if not graded:
        reason = ("no ad has a hook rate (3-second plays are missing, or there are no video ads)"
                  if not any(r["hook_rate"] is not None for r in records) else
                  "too few comparable video ads to grade a hook rate")
        return {"top": [], "bottom": [], "faded": [], "note": "n/a (%s)" % reason}

    def entry(r: Dict[str, Any]) -> Dict[str, Any]:
        return {k: r[k] for k in ("ad", "ad_name", "concept", "format", "hook_rate", "hook_band", "hold_rate", "hold_band",
                                  "age_days", "opening", "opening_note", "verdict")} | {"faded": r["hook_faded"]}

    ranked = sorted(graded, key=lambda r: -(r["hook_percentile"] or 0))
    top = [entry(r) for r in ranked if r["hook_band"] == cm.BAND_TOP and not r["hook_faded"]][:top_n]
    bottom = [entry(r) for r in reversed(ranked) if r["hook_band"] == cm.BAND_BOTTOM][:top_n]
    faded = [entry(r) for r in ranked if r["hook_faded"]]
    return {"top": top, "bottom": bottom, "faded": faded, "note": None}


def _coverage(records: Sequence[Dict[str, Any]], total_spend: float) -> List[Dict[str, Any]]:
    cells: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in records:
        if rec.get("concept") and rec.get("format"):
            cells.setdefault((str(rec["concept"]), str(rec["format"])), []).append(rec)
    rank = {cm.BAND_TOP: 0, cm.BAND_MID: 1, cm.BAND_BOTTOM: 2}
    out = []
    for (concept, fmt), recs in sorted(cells.items()):
        bands = [b for r in recs for b in r["bands"].values() if b in rank]
        spend, spend_reported = _spend_of(recs)
        out.append({"concept": concept, "format": fmt, "ads": [r["ad"] for r in recs],
                    "spend_share": _spend_share(spend, total_spend), "spend_reported": spend_reported,
                    "best_band": min(bands, key=rank.__getitem__) if bands else "not graded",
                    "youngest_age_days": min((r["age_days"] for r in recs if r["age_days"] is not None), default=None)})
    return out


def build_evidence(rows: Sequence[Dict[str, Any]], window: int = 6, min_change: float = 8.0,
                   min_impressions: int = 1000, max_gaps: int = 8,
                   include_types: Sequence[str] = ("bau",),
                   key_map: Optional[Dict[str, str]] = None, segment: Optional[str] = None,
                   verdicts: Any = None, competitor: Any = None, top_n: int = TOP_N) -> Dict[str, Any]:
    """The evidence set (schema 1): the brief sections (top-quartile, fatiguing and never-worked ads, coverage
    gaps) plus per-ad records, results by segment, angle clusters, hooks and concept x format coverage."""
    all_ads = cm.aggregate_by_ad(rows, key_map=key_map)
    ads = [a for a in all_ads if a.get("concept") and a.get("format")]
    if not ads:
        return {"schema": SCHEMA, "available": False, "unbacked": UNBACKED,
                "competitor": _competitor(competitor) if competitor is not None else None}
    verdict_of = _verdicts(verdicts) if verdicts is not None else {}
    first_ads = cm.window_aggregate(rows, window, "first", key_map=key_map)
    first_by_key = {_key(a): a for a in first_ads}
    total_spend = _spend_of(ads)[0]
    top, fatiguing, never, young, records = [], [], [], [], []
    for ad in ads:
        key = _key(ad)
        judged = (ad.get("impressions") or 0) >= min_impressions
        bands = _bands(ad, ads, min_impressions) if judged else {}
        trend = _fatiguing(rows, key, window, min_change) if judged else {"fatiguing": False, "readable": False}
        never_worked = False
        if not judged:
            young.append(key)
        else:
            entry = dict(_summary(ad), bands=bands)
            if trend["fatiguing"]:
                fatiguing.append(dict(entry, trend=trend))
            elif _bottom(bands):
                first = first_by_key.get(key)
                if first and _bottom(_bands(first, first_ads, min_impressions)):
                    never.append(entry)
                    never_worked = True
            graded = [b for b in bands.values() if not b.startswith("not graded")]
            if graded and all(b == cm.BAND_TOP for b in graded):
                top.append(entry)
        hook = cm.grade_against(ad, ads, "hook_rate", ("format",), min_impressions)
        hold = cm.grade_against(ad, ads, "hold_rate", ("format",), min_impressions)
        graded = [b for b in bands.values() if not b.startswith("not graded")]
        opening = _opening(ad)
        records.append(dict(
            _summary(ad), **{f: ad.get(f) for f in ("persona", "audience", "adset_name", "funnel_stage", "offer", "hook")},
            spend_share=_spend_share(ad.get("spend"), total_spend),
            spend_share_note="n/a (missing spend)" if ad.get("spend") is None else None,
            impressions=ad.get("impressions"), age_basis=ad.get("age_basis"),
            **{m: ad.get(m) for m in ATTENTION},
            hook_band=hook["band"], hook_percentile=hook.get("percentile"), hold_band=hold["band"],
            judged=judged, bands=bands, payback_top=bool(graded) and all(b == cm.BAND_TOP for b in graded),
            payback_bottom=_bottom(bands), never_worked=never_worked, fatigue=trend,
            hook_faded=bool(trend.get("hook_faded")),
            verdict=(verdict_of.get(str(key)) or {}).get("verdict"),
            verdict_id=(verdict_of.get(str(key)) or {}).get("verdict_id"),
            verdict_source="keep-or-kill" if verdicts is not None else None,
            opening=opening, opening_note=None if opening else "n/a (missing primary text: the export has no ad text column)"))

    # Promo and launch concepts are tied to a date, so by default only evergreen winners
    # seed gaps; the caller can include other ad types when briefing a sale or a launch.
    top_concepts = sorted({a["concept"] for a in top if a.get("ad_type") in include_types})
    top_formats = sorted({a["format"] for a in top})
    present = {(a["concept"], a["format"]) for a in ads}
    gaps = [{"concept": c, "format": f} for c in top_concepts for f in top_formats if (c, f) not in present]
    by_key = {str(r["ad"]): r for r in records}
    field = _segment_field(all_ads, segment)
    return {
        "schema": SCHEMA, "available": True, "ads": len(ads), "window": cm.data_window(rows),
        "settings": {"window": window, "min_change": min_change, "min_impressions": min_impressions,
                     "include_types": list(include_types), "top_n": top_n},
        "top_quartile": top, "fatiguing": fatiguing, "never_worked": never,
        "top_concepts": top_concepts, "top_formats": top_formats,
        "gaps": gaps[:max_gaps], "gaps_total": len(gaps), "too_young": young,
        "hook_derived": any((r.get("video_views_3s_source") or "").startswith("derived") for r in rows),
        "records": records,
        "segments": _segments(ads, by_key, field, total_spend),
        "angles": _angles(records, total_spend),
        "hooks": _hooks(records, top_n),
        "coverage": _coverage(records, total_spend),
        "verdicts_source": "keep-or-kill" if verdicts is not None else
        "not supplied: bands below are quartiles, not verdicts (pass --verdicts from keep-or-kill)",
        "competitor": _competitor(competitor) if competitor is not None else None,
    }


def _ad_line(ad: Dict[str, Any]) -> str:
    fields = " | ".join(str(ad.get(f) or "?") for f in FIELDS)
    return "  %s  %s  (roas %s, cpa %s)" % (ad["ad"], fields, _n(ad["roas"]), _n(ad["cpa"]))


def _n(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.2f" % value


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%+.0f%%" % value


def _share(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.0f%%" % value


def _spend_text(share: Optional[float], reported: int, ads: int) -> str:
    if not reported:
        text = "spend share n/a (missing spend)"
    elif share is None:
        text = "0 spend reported"
    else:
        text = "%s of spend" % _share(share)
    return text + (" (%d of %d ads report spend)" % (reported, ads) if reported and reported < ads else "")


def _ids(ids: Sequence[Any]) -> str:
    return ", ".join(str(i) for i in ids) or "none"


def _basis(result: Dict[str, Any]) -> List[str]:
    start, end = result["window"]
    s = result["settings"]
    return [
        "Basis: this account's own ads, %s to %s, each graded against ads of the same format. "
        "Never a benchmark." % (start or "n/a", end or "n/a"),
        "Settings (arbitrary defaults, set them from your own account): window=%d days, "
        "min-change=%g%%, min-impressions=%d. Ad types used to seed gaps: %s." % (
            s["window"], s["min_change"], s["min_impressions"], ", ".join(s["include_types"])),
    ]


def render(result: Dict[str, Any]) -> str:
    """The brief view: the Evidence block a production brief carries."""
    if not result.get("available"):
        return NONE_AVAILABLE
    s = result["settings"]
    out = ["Evidence"] + _basis(result) + [
        "Hook wording is not in an ad export: take the opening line from the ad itself.",
    ] + (["Hook rate (derived): 3-second plays are derived as spend / cost per 3-second view, not reported."]
         if result.get("hook_derived") else []) + [
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


def render_persona(result: Dict[str, Any]) -> str:
    """Who responded: results by persona or audience, and the angles that won and lost."""
    if not result.get("available"):
        return "\n".join([NONE_AVAILABLE, UNBACKED])
    seg = result["segments"]
    out = ["Persona evidence"] + _basis(result) + [""]
    if seg["field"] is None:
        out.append(seg["note"] + ".")
    else:
        account = seg["account"]
        out.append("Results by %s (pooled over each group's ads; vs account = the group's rate as a percent of the "
                   "account's own pooled rate, 100 = the same; account roas %s, cpa %s):" % (
                       seg["field"], _n(account["roas"]), _n(account["cpa"])))
        for row in seg["rows"]:
            nc = row["new_customer_note"] if row["new_customer_purchase_share"] is None else _share(
                row["new_customer_purchase_share"]) + (" (%s)" % row["new_customer_note"] if row["new_customer_note"] else "")
            out.append("  %s: %d ads, %s, roas %s (%s of account), cpa %s, new-customer share %s" % (
                row["value"], row["ads"], _spend_text(row["spend_share"], row["spend_reported"], row["ads"]), _n(row["roas"]), _share(row["roas_vs_account"]),
                _n(row["cpa"]), nc))
            out.append("    top-quartile ads: %s; bottom-quartile ads: %s; concepts: %s" % (
                _ids(row["top_quartile_ads"]), _ids(row["bottom_quartile_ads"]), ", ".join(row["concepts"]) or "none read"))
    out += [""] + _angle_lines(result)
    return "\n".join(out)


def _angle_lines(result: Dict[str, Any]) -> List[str]:
    out = ["Angles (concepts) by how their ads did: winning = a top-quartile ad and no weak one; losing = weak or "
           "never-worked ads and no top-quartile one; mixed = both; middle = graded, none top or weak; "
           "ungraded = too few comparable ads to grade; unjudged = too little delivery:"]
    for a in result["angles"]:
        out.append("  %s [%s]: ads %s; %s; formats %s%s" % (
            a["concept"], a["label"], _ids(a["ads"]),
            _spend_text(a["spend_share"], a["spend_reported"], len(a["ads"])), ", ".join(a["formats"]) or "unknown",
            "; fatiguing: %s" % _ids(a["fatiguing_ads"]) if a["fatiguing_ads"] else ""))
    return out if result["angles"] else out + ["  none"]


def render_hooks(result: Dict[str, Any]) -> str:
    """The openings that stop people and the ones that do not, with hold rate and age; faded hooks set apart."""
    if not result.get("available"):
        return "\n".join([NONE_AVAILABLE, UNBACKED])
    hooks = result["hooks"]
    out = ["Hook evidence"] + _basis(result) + [
        "Hook rate = 3-second plays / impressions; hold rate = ThruPlays / 3-second plays. Bands are quartiles "
        "within the ad's format. Verdicts: %s." % result["verdicts_source"]]
    if result.get("hook_derived"):
        out.append("Hook rate (derived): 3-second plays are derived as spend / cost per 3-second view, not reported.")
    if hooks["note"]:
        return "\n".join(out + ["", "Hooks: " + hooks["note"]])

    def line(h: Dict[str, Any]) -> str:
        return "  %s %s (%s): hook %s [%s], hold %s [%s], %s days old%s; opening: %s" % (
            h["ad"], h["concept"], h["format"], _n(h["hook_rate"]), h["hook_band"], _n(h["hold_rate"]), h["hold_band"],
            h["age_days"] if h["age_days"] is not None else "n/a", ", verdict %s" % h["verdict"] if h["verdict"] else "",
            h["opening"] or h["opening_note"])

    out += ["", "Openings that stop people (top quartile, not faded): learn from these:"]
    out += [line(h) for h in hooks["top"]] or ["  none"]
    out += ["", "Openings that do not stop people (bottom quartile): do not reuse as they are:"]
    out += [line(h) for h in hooks["bottom"]] or ["  none"]
    out += ["", "Faded hooks (hook rate down by at least the min-change since the ad's first days): skip these as "
            "models, or vary them one change at a time:"]
    out += [line(h) for h in hooks["faded"]] or ["  none"]
    return "\n".join(out)


def render_ideation(result: Dict[str, Any]) -> str:
    """What the account has tried, what worked, what is crowded, and where nothing has been tried."""
    if not result.get("available"):
        lines = [NONE_AVAILABLE, UNBACKED]
        if result.get("competitor"):
            lines += [""] + _competitor_lines(result["competitor"])
        return "\n".join(lines)
    out = ["Ideation evidence"] + _basis(result) + ["Verdicts: %s." % result["verdicts_source"], ""] + _angle_lines(result)
    out += ["", "Concept x format coverage (spend share, best band of any ad in the cell, youngest ad's age):"]
    for c in result["coverage"]:
        out.append("  %s in %s: ads %s; %s; best %s; youngest %s days" % (
            c["concept"], c["format"], _ids(c["ads"]),
            _spend_text(c["spend_share"], c["spend_reported"], len(c["ads"])), c["best_band"],
            c["youngest_age_days"] if c["youngest_age_days"] is not None else "n/a"))
    out += ["", "Untried cells beside a winner (a hypothesis to test, not a result):"]
    out += ["  %s in %s" % (g["concept"], g["format"]) for g in result["gaps"]] or ["  none"]
    if result["competitor"]:
        out += [""] + _competitor_lines(result["competitor"])
    else:
        out += ["", "Competitor scan: not supplied (run competitor-scan and pass --competitor to add it)."]
    return "\n".join(out)


def _competitor_lines(comp: Dict[str, Any]) -> List[str]:
    out = ["Competitor scan (%s): %s ads from %s advertisers." % (
        comp.get("source") or "source not stated", comp.get("ads") if comp.get("ads") is not None else "n/a",
        comp.get("advertisers") if comp.get("advertisers") is not None else "n/a")]
    for label, key in (("Open ground", "open_ground"), ("Worth testing", "worth_testing"), ("Not to chase", "not_to_chase")):
        items = comp.get(key) or []
        out.append("  %s: %s" % (label, "; ".join(str(i.get("label") if isinstance(i, dict) else i) for i in items) or "none"))
    return out


RENDERERS = {"brief": render, "persona": render_persona, "hooks": render_hooks, "ideation": render_ideation}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Account evidence for briefs, personas, hooks and ideas.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--for", dest="view", choices=VIEWS, default="brief",
                        help="which view to print: brief (the Evidence block), persona, hooks or ideation")
    parser.add_argument("--segment", help="column or name field to read personas from (default: persona, audience, "
                                          "then ad set name, whichever the data has)")
    parser.add_argument("--verdicts", help="keep-or-kill --json output, so each ad carries its verdict")
    parser.add_argument("--competitor", help="competitor-scan --json output, for the ideation view")
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
    parser.add_argument("--top", type=int, default=TOP_N, help="openings listed at each end of the hooks view (arbitrary default)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        result = build_evidence(rows, args.window, args.min_change, args.min_impressions, args.max_gaps,
                                tuple(cm.normalise_ad_type(t) for t in args.include_types.split(",") if t.strip()),
                                key_map, segment=args.segment, verdicts=args.verdicts, competitor=args.competitor,
                                top_n=args.top)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["run_notes"] = run_notes
    print(json.dumps(result, indent=2) if args.json else "\n".join(run_notes + [RENDERERS[args.view](result)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
