"""The dashboard's interaction layer: per-ad records, facets, smart views, group subtotals and how-to-improve text.

Pure data and wording, no HTML. The records become the JSON block the page script reads; the same functions
render the default (scripts-off) view, so both views come from one source. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

LABEL_WORDS = 64  # arbitrary: where a fallback ad name is cut, at a word boundary
LABELS = {"hook_rate": "Hook rate", "hold_rate": "Hold rate", "video_completion_rate": "Video completion rate",
          "ctr": "CTR", "cvr": "CVR", "cpm": "CPM", "cpc": "CPC", "cpa": "CPA", "roas": "ROAS", "mer": "MER",
          "add_to_cart_rate": "Add-to-cart rate", "cost_per_add_to_cart": "Cost per add to cart",
          "cost_per_lead": "Cost per lead", "engagement_rate": "Engagement rate"}

# verdict_id -> display class; the five classes plus the two the board lists last.
ID_CLASS = {"scale": "scale", "keep": "keep", "iterate": "iterate", "cant_judge": "cant", "too_early": "early"}
BOARD = (("scale", "Scale"), ("keep", "Keep"), ("iterate", "Iterate"), ("check", "Check before cutting"),
         ("kill", "Pause"), ("early", "Too early"), ("cant", "Can't judge"))
VERDICT_LABEL = dict(BOARD)
NEXT_STEP = {
    "scale": "Raise the budget in steps and re-read payback after each step.",
    "keep": "Leave it running and read it again at the next review.",
    "iterate": "Brief a new opening or creator and keep the concept.",
    "check": "Check whether it feeds your other ads before you cut anything.",
    "kill": "Pause it once the check below comes back clean.",
    "early": "Give it more delivery before judging it.",
    "cant": "Add the missing data, then run keep-or-kill again.",
}
PAUSE_CHECK = "Rule out tracking, the site and the audience first."
# What a reader sees in a link, a filter chip or the page data: the board's own words, never the internal class name.
PUBLIC_ID = {"kill": "pause", "early": "too-early", "cant": "cant-judge"}
PUBLIC_LABEL = {PUBLIC_ID.get(cls, cls): label for cls, label in BOARD}
PUBLIC_ORDER = [PUBLIC_ID.get(cls, cls) for cls, _ in BOARD]

FACETS = (("verdict", "Verdict"), ("confidence", "Confidence"), ("format", "Format"), ("ad_type", "Ad type"),
          ("concept", "Concept"), ("market", "Market"), ("funnel_stage", "Funnel stage"), ("creator", "Creator"),
          ("objective", "Objective"))
GROUPS = ("verdict", "format", "concept", "ad_type", "market", "creator")
SORTS = (("stake", "Spend at stake"), ("spend", "Spend"), ("roas", "ROAS (best first)"), ("cpa", "CPA (lowest first)"),
         ("ctr", "CTR"), ("hook", "Hook rate"), ("age", "Age (oldest first)"))
FACET_MIN_VALUES = 2  # arbitrary: a facet with one value cannot narrow anything
FACET_KNOWN = (3, 5)  # arbitrary: a facet shows only when it is known for at least 3 in 5 ads
BIGGEST_N = 9  # arbitrary default: how many ads the "Biggest spenders" view keeps; set it from your own account

PRESETS = (
    {"id": "money", "label": "Money at risk", "filters": {"verdict": ["pause", "check"]}, "sort": "stake",
     "note": "Pause and Check before cutting, biggest spend at stake first."},
    {"id": "scale", "label": "Ready to scale", "filters": {"verdict": ["scale"]},
     "note": "Ads whose payback holds up well against your similar ads."},
    {"id": "tiring", "label": "Tiring out", "filters": {}, "fatiguing": True,
     "note": "Ads whose clicks fall while people see them more often."},
    {"id": "cant", "label": "Can't judge yet", "filters": {"verdict": ["cant-judge", "too-early"]},
     "note": "Too early, or the data to judge them is missing."},
    {"id": "spenders", "label": "Biggest spenders", "filters": {}, "top": BIGGEST_N,
     "note": "The top %d ads by spend (an arbitrary default)." % BIGGEST_N},
)

STEP_WORDS = {
    "reach cost": "reaching people costs more than for your similar ads",
    "hook": "the opening is not stopping the scroll",
    "hold": "people drop off before the message lands",
    "click": "people watch but do not click",
    "post-click": "clicks do not turn into carts or purchases",
    "pays back": "the funnel reads normally but payback is weak",
}
STEP_FIX = {
    "reach cost": "Rule out the audience and the auction before you change the ad.",
    "hook": "Try a new opening: a different first moment, creator or visual.",
    "hold": "Tighten the middle of the ad so the promise carries through.",
    "click": "Make the call to action or the offer stronger.",
    "post-click": "Check that the landing page and the offer match the ad, then the audience.",
    "pays back": "Check price, margin, offer and attribution before blaming the creative.",
}
NOTHING_WEAK = "Nothing in the funnel reads weak against this account."
NO_FIX = "Not enough data to suggest a fix."
BAND_WORDS = {cm.BAND_TOP: "among your best", cm.BAND_MID: "middle", cm.BAND_BOTTOM: "among your weakest"}
METRIC_KIND = {"hook_rate": "pct", "hold_rate": "pct", "video_completion_rate": "pct", "ctr": "pct", "cvr": "pct",
               "add_to_cart_rate": "pct", "engagement_rate": "pct", "roas": "x", "cpm": "money", "cpa": "money",
               "cpc": "money", "cost_per_lead": "money", "cost_per_add_to_cart": "money"}
AD_FUNNEL = (("Impressions", "impressions"), ("3-second plays", "video_views_3s"), ("ThruPlays", "video_thruplay"),
             ("Link clicks", "link_clicks"), ("Adds to cart", "add_to_carts"), ("Purchases", "conversions"))


STEP_SLUG = {"reach cost": "reach-cost", "hook": "hook", "hold": "hold", "click": "click", "post-click": "post-click", "pays back": "pays-back"}
UNSLUG = {slug: step for step, slug in STEP_SLUG.items()}
WEAK_VALUES = list(STEP_SLUG.values()) + ["none", "undiagnosed"]
ACRONYMS = {"ugc": "UGC", "bau": "BAU", "npr": "NPR", "cta": "CTA", "roas": "ROAS", "cpa": "CPA", "ctr": "CTR", "cpm": "CPM"}
FIELD_WORDS = {"spend": "spend", "impressions": "impressions", "reach": "reach", "video_views_3s": "3-second plays", "video_thruplay": "ThruPlays",
               "link_clicks": "link clicks", "clicks": "clicks", "conversions": "purchases", "conversion_value": "purchase value",
               "add_to_carts": "adds to cart", "revenue": "revenue", "leads": "leads", "shares": "shares", "saves": "saves", "comments": "comments",
               "engagements": "engagements", "landing_page_views": "landing page views", "checkouts": "checkouts", "ad_type": "ad type",
               "funnel_stage": "funnel stage", "age_days": "age", "ad_id": "ad ID", "ad_name": "ad name", "video_views": "video views"}
_ID_RE = re.compile(r"(?<![\w-])(%s)(?![\w])" % "|".join(sorted(FIELD_WORDS, key=len, reverse=True)))
_SNAKE_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")


def plain_ids(text: Any) -> str:
    """Field ids in generated wording shown as the words a reader knows; any other snake_case token loses its underscores."""
    shown = _ID_RE.sub(lambda m: FIELD_WORDS[m.group(1)], "" if text is None else str(text))
    return _SNAKE_RE.sub(lambda m: m.group(0).replace("_", " "), shown)


def humanise(value: Any, sentence: bool = False) -> str:
    """A slug read as words: hyphens and underscores become spaces, known acronyms upper-case; sentence case on request.
    A value with no lower-case letter (a market code) is kept as written."""
    text = str(value if value is not None else "").strip()
    if not text or not any(c.islower() for c in text):
        return text
    out = " ".join(ACRONYMS.get(w.lower(), w) for w in re.split(r"[-_\s]+", text) if w)
    return out[:1].upper() + out[1:] if sentence else out


# ---------- verdicts and labels (shared with panels.py) ----------

def recognised(entry: Dict[str, Any]) -> bool:
    vid = entry.get("verdict_id") or ""
    return vid.startswith(("pause", "check")) or vid in ID_CLASS or vid == "keep"


def entry_class(entry: Dict[str, Any]) -> str:
    """The board class of a verdict entry, from its stable verdict_id. An unknown or missing id is Can't judge, never a soft pass."""
    vid = entry.get("verdict_id") or ""
    if vid.startswith("pause"):
        return "kill"
    if vid.startswith("check"):
        return "check"
    return ID_CLASS.get(vid, "cant")


def first_segment(name: Optional[str]) -> str:
    return re.split(r"\s*\|\s*|\s_\s|\s-\s", str(name or "").strip())[0].strip()


def _truncate(text: str, limit: int = LABEL_WORDS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" |-_,") + "..."


def readable_label(fields: Dict[str, Any], name: Optional[str], ad_id: Any = None) -> str:
    """concept · creator · format · ad type, skipping what did not parse; never the raw first name segment."""
    parts = [humanise(fields[k]) if k in ("format", "ad_type") else str(fields[k]) for k in ("concept", "creator", "format", "ad_type") if fields.get(k)]
    label = " · ".join(parts)
    if label and label.lower() != first_segment(name).lower():
        return label
    if name:
        return _truncate(str(name))
    return label or "Ad %s" % (ad_id if ad_id is not None else "(no id)")


def metric_label(metric: str) -> str:
    return LABELS.get(metric, metric.replace("_", " "))


def plain_metric(metric: str) -> str:
    """A metric name inside a sentence: lower case unless it is an acronym."""
    label = metric_label(metric)
    return label if label.isupper() else label[:1].lower() + label[1:]


def format_label(fmt: Any) -> str:
    return humanise(fmt, True) or "Format n/a"


# ---------- records ----------

def _num(value: Any) -> Optional[float]:
    return None if value is None else value


def _record(key: str, base: Dict[str, Any], verdict: Optional[Dict[str, Any]], grade: Optional[Dict[str, Any]],
            label_of: Callable[..., str]) -> Dict[str, Any]:
    verdict, grade = verdict or {}, grade or {}
    name = base.get("ad_name") or verdict.get("ad_name") or verdict.get("name") or grade.get("name")
    fields = dict(base) if base else dict(cm.parse_name(name) if name else {})
    fmt = fields.get("format") or verdict.get("format") or grade.get("format")
    fields["format"] = fmt
    cls = entry_class(verdict) if verdict else None
    spend = base.get("spend") if base else verdict.get("spend")
    stake = verdict.get("spend_at_stake")
    step = (grade.get("diagnosis") or {}).get("step")
    fatigue = verdict.get("fatigue") or {}
    unknown_fatigue = not verdict or "fatiguing" not in verdict or fatigue.get("status") == "insufficient data"
    assumed = verdict.get("objective_assumed", grade.get("objective_assumed"))
    objective = None if assumed else (verdict.get("objective") or grade.get("objective"))
    return {
        "id": key, "label": label_of(fields, name, key), "name": name,
        "verdict": PUBLIC_ID.get(cls, cls) if cls else None, "verdict_id": verdict.get("verdict_id"),
        "confidence": verdict.get("confidence"),
        "format": fmt, "ad_type": fields.get("ad_type"), "concept": fields.get("concept"), "market": fields.get("market"),
        "funnel_stage": fields.get("funnel_stage"), "creator": fields.get("creator"), "objective": objective,
        "spend": _num(spend), "conversions": _num(base.get("conversions")), "conversion_value": _num(base.get("conversion_value")),
        "impressions": _num(base.get("impressions") if base else grade.get("impressions")),
        "link_clicks": _num(base.get("link_clicks")), "clicks": _num(base.get("clicks")),
        "video_views_3s": _num(base.get("video_views_3s")), "video_thruplay": _num(base.get("video_thruplay")),
        "fatiguing": None if unknown_fatigue else bool(verdict["fatiguing"]),
        "age_days": base.get("age_days") if base and base.get("age_days") is not None else verdict.get("age_days"),
        "stake": stake if stake is not None else _num(spend),
        "weak": STEP_SLUG.get(step, "none" if step == "none" else None),
    }


def ad_records(ads: Sequence[Dict[str, Any]], verdict_entries: Optional[Sequence[Dict[str, Any]]],
               grade_entries: Optional[Sequence[Dict[str, Any]]], label_of: Callable[..., str] = readable_label) -> List[Dict[str, Any]]:
    """One record per ad: every ad in the rows, plus any the verdicts or grades name that the rows lack."""
    verdicts = {str(e.get("ad")): e for e in verdict_entries or []}
    grades = {str(e.get("ad")): e for e in grade_entries or []}
    out, seen = [], set()
    for ad in ads:
        key = str(ad.get("ad_id") or ad.get("ad_name"))
        out.append(_record(key, ad, verdicts.get(key), grades.get(key), label_of))
        seen.add(key)
    for key in list(verdicts) + list(grades):
        if key not in seen:
            seen.add(key)
            out.append(_record(key, {}, verdicts.get(key), grades.get(key), label_of))
    return out


def facets(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Facets that can narrow the list: 2+ distinct values, known for at least 3 in 5 ads; values sorted by spend."""
    out = []
    for key, label in FACETS:
        found: Dict[str, Dict[str, Any]] = {}
        known = 0
        for rec in records:
            value = rec.get(key)
            if value in (None, ""):
                continue
            known += 1
            entry = found.setdefault(value, {"value": value, "label": PUBLIC_LABEL.get(value, str(value)) if key == "verdict" else humanise(value, True),
                                             "count": 0, "spend": 0.0})
            entry["count"] += 1
            entry["spend"] += rec.get("spend") or 0
        if len(found) >= FACET_MIN_VALUES and known * FACET_KNOWN[1] >= len(records) * FACET_KNOWN[0]:
            values = sorted(found.values(), key=lambda v: (-v["spend"], -v["count"], str(v["value"])))
            out.append({"key": key, "label": label, "values": values})
    return out


def display_names(records: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Raw value -> words, per facet, so the page script shows what the Python view shows."""
    names: Dict[str, Dict[str, str]] = {}
    for key, _ in FACETS:
        if key == "verdict":
            continue
        for rec in records:
            if rec.get(key) not in (None, ""):
                names.setdefault(key, {})[rec[key]] = humanise(rec[key], True)
    return names


def payload(records: Sequence[Dict[str, Any]], currency: Optional[str], top_n: int, default_group: str) -> Dict[str, Any]:
    return {"ads": list(records), "presets": list(PRESETS), "names": display_names(records), "weak_steps": WEAK_VALUES, "currency": currency,
            "unit_note": "" if currency else " (account currency)", "top_n": top_n,
            "defaults": {"group": default_group, "sort": "stake"}, "verdict_labels": PUBLIC_LABEL}


def payload_json(data: Dict[str, Any]) -> str:
    """JSON that cannot close or open a tag: < > & become unicode escapes, which JSON.parse reads back unchanged."""
    text = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# ---------- group subtotals ----------

def ratio_text(num: Optional[float], den: Optional[float], num_name: str, den_name: str) -> Optional[str]:
    """Why a ratio of sums cannot be read, in the metric library's words, or None when it can."""
    if num is None:
        return "n/a (missing %s)" % num_name
    if den is None:
        return "n/a (missing %s)" % den_name
    if den == 0:
        return "n/a (zero %s)" % den_name
    return None


def _sum(records: Sequence[Dict[str, Any]], field: str) -> Optional[float]:
    values = [r[field] for r in records if r.get(field) is not None]
    return sum(values) if values else None


def ratio_of_sums(records: Sequence[Dict[str, Any]], num: str, den: str, num_words: str, den_words: str) -> Dict[str, Any]:
    """Sum of num over sum of den across the ads that have both; says how many ads that was when it is not all of them."""
    pairs = [r for r in records if r.get(num) is not None and r.get(den) is not None]
    if not pairs:
        known = any(r.get(num) is not None for r in records)
        return {"value": None, "n": 0, "suffix": "", "why": "n/a (missing %s)" % (den_words if known else num_words)}
    top, bottom = sum(r[num] for r in pairs), sum(r[den] for r in pairs)
    if bottom == 0:
        return {"value": None, "n": len(pairs), "suffix": "", "why": "n/a (zero %s)" % den_words}
    suffix = " (%d of %d ads)" % (len(pairs), len(records)) if len(pairs) < len(records) else ""
    return {"value": top / bottom, "n": len(pairs), "suffix": suffix, "why": None}


def totals_of(records: Sequence[Dict[str, Any]], total_spend: Optional[float], money: Optional[Callable[..., str]] = None) -> Dict[str, Any]:
    """Ads, spend, share of account spend, ROAS and CPA of a set of ads: ratios of sums over the ads that have both operands."""
    spend, conv, value = _sum(records, "spend"), _sum(records, "conversions"), _sum(records, "conversion_value")
    roas = ratio_of_sums(records, "conversion_value", "spend", "purchase value", "spend")
    cpa = ratio_of_sums(records, "spend", "conversions", "spend", "purchases")
    show_money = money or (lambda v, d=0: "%.*f" % (d, v))
    return {"ads": len(records), "spend": spend, "conversions": conv, "conversion_value": value,
            "share": None if not total_spend or spend is None else spend / total_spend * 100,
            "roas": roas["value"], "cpa": cpa["value"], "roas_n": roas["n"], "cpa_n": cpa["n"],
            "roas_suffix": roas["suffix"], "cpa_suffix": cpa["suffix"],
            "roas_text": roas["why"] or "%.2fx%s" % (roas["value"], roas["suffix"]),
            "cpa_text": cpa["why"] or "%s%s" % (show_money(cpa["value"], 2), cpa["suffix"])}


def group_records(records: Sequence[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """[{key, label, records}]: the verdict board's order for verdicts, else largest spend first; unknown last."""
    found: Dict[Any, List[Dict[str, Any]]] = {}
    for rec in records:
        found.setdefault(rec.get(key) or None, []).append(rec)
    known = [k for k in found if k is not None]
    if key == "verdict":
        known.sort(key=lambda k: PUBLIC_ORDER.index(k) if k in PUBLIC_ORDER else len(PUBLIC_ORDER))
    else:
        known.sort(key=lambda k: -(sum(r.get("spend") or 0 for r in found[k])))
    order = known + ([None] if None in found else [])
    names = PUBLIC_LABEL if key == "verdict" else {}
    unknown = "No verdict yet" if key == "verdict" else "Not known"
    return [{"key": k, "label": unknown if k is None else names.get(k) or humanise(k, True), "records": found[k]} for k in order]


def by_stake(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Spend at stake, largest first; an ad whose stake is unknown goes last, never ranked as zero."""
    return sorted(records, key=lambda r: (r.get("stake") is None, -(r.get("stake") or 0)))


def group_subtotals(records: Sequence[Dict[str, Any]], key: str, total_spend: Optional[float] = None,
                    money: Optional[Callable[..., str]] = None) -> List[Dict[str, Any]]:
    total = total_spend if total_spend is not None else sum(r.get("spend") or 0 for r in records)
    return [dict(totals_of(g["records"], total, money), key=g["key"], label=g["label"]) for g in group_records(records, key)]


# ---------- how to improve ----------

def improvement(grade: Optional[Dict[str, Any]], verdict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The verdict's next step, the fix for the ad's first weak funnel step, then what else is weak. Never invents a fix."""
    lead = NEXT_STEP[entry_class(verdict)] if verdict else None
    diag = (grade or {}).get("diagnosis") or {}
    step = diag.get("step")
    if step in STEP_FIX:
        also = [plain_metric(m) for m in diag.get("also_weak") or []]
        return {"lead": lead, "fix": diag.get("action") or STEP_FIX[step], "step": step,
                "also": "Also weak: %s." % ", ".join(also) if also else None, "note": None, "has_data": True}
    if step == "none":
        return {"lead": lead, "fix": diag.get("action") or NOTHING_WEAK, "step": step, "also": None, "note": None, "has_data": True}
    return {"lead": lead, "fix": None, "step": None, "also": None, "note": NO_FIX, "has_data": False}


def next_version_prompt(rec: Dict[str, Any], grade: Optional[Dict[str, Any]]) -> str:
    """A prompt for the hook-writer and creative-brief skills: what worked, what to change, in words."""
    worked = ["%s is %s" % (plain_metric(m), BAND_WORDS[cm.BAND_TOP])
              for m, g in ((grade or {}).get("grades") or {}).items() if g.get("band") == cm.BAND_TOP]
    step = ((grade or {}).get("diagnosis") or {}).get("step")
    change = ("%s. %s" % (STEP_WORDS[step].capitalize(), STEP_FIX[step])) if step in STEP_FIX else "Not enough graded data to name one step; read the ad's numbers first."
    return ("Use the hook-writer and creative-brief skills to make the next version of this ad.\n"
            "Ad: %s (format: %s).\n"
            "What worked: %s.\n"
            "What to change: %s\n"
            "Keep the concept and change only what needs fixing." % (
                rec.get("label"), humanise(rec.get("format")) or "not known",
                "; ".join(worked) if worked else "no metric reads among your best yet", change))


def is_video(fmt: Any) -> Optional[bool]:
    """True for a video format, False for a known non-video one, None when the format is not known."""
    text = str(fmt or "").lower()
    return None if not text else "video" in text or "reel" in text


VIDEO_METRICS = ("hook_rate", "hold_rate", "video_completion_rate")


def band_rows(grade: Optional[Dict[str, Any]], money: Callable[..., str], fmt: Any = None) -> List[Dict[str, str]]:
    """Each graded metric in plain words, with its value and unit."""
    rows = []
    for metric, entry in ((grade or {}).get("grades") or {}).items():
        band = str(entry.get("band") or "")
        if band == "not banded":
            continue
        value, kind = entry.get("value"), METRIC_KIND.get(metric)
        if band.startswith("not graded"):
            reason = band[len("not graded"):].strip(" ()") or "no value"
            if metric in VIDEO_METRICS and is_video(fmt) is False:
                reason = "not a video ad"
            reason = plain_ids(reason)
            words, text = "not graded: %s" % reason, "n/a (%s)" % reason
        else:
            words = BAND_WORDS.get(band, band)
            text = "n/a" if value is None else "%.2f%%" % value if kind == "pct" else "%.2fx" % value if kind == "x" else money(value, 2) if kind == "money" else "%.2f" % value
        rows.append({"metric": metric, "label": metric_label(metric), "value": text, "band": words})
    return rows


def ad_funnel(base: Optional[Dict[str, Any]], fmt: Any = None) -> List[Dict[str, str]]:
    base = base or {}
    impressions = base.get("impressions")
    rows = []
    for name, field in AD_FUNNEL:
        value = base.get(field)
        if value is None:
            why = "not a video ad" if field in ("video_views_3s", "video_thruplay") and is_video(fmt) is False else "missing %s" % FIELD_WORDS.get(field, field)
            rows.append({"step": name, "count": "n/a (%s)" % why, "share": "n/a"})
        else:
            rows.append({"step": name, "count": "{:,.0f}".format(value),
                         "share": "n/a" if not impressions else "%.2f%%" % (value / impressions * 100)})
    return rows


def weak_groups(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ads by first weak funnel step, largest spend first; then 'nothing weak', then ads with no diagnosis. Every ad lands in one row."""
    total = sum(r.get("spend") or 0 for r in records)
    found: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for rec in records:
        found.setdefault(rec.get("weak"), []).append(rec)

    def row(step: Optional[str]) -> Dict[str, Any]:
        members = found[step]
        spend = sum(r.get("spend") or 0 for r in members)
        return {"step": step, "ads": len(members), "spend": spend, "share": spend / total * 100 if total else None,
                "words": STEP_WORDS.get(UNSLUG.get(step), "no weak step found" if step == "none" else "not diagnosed (missing data)"),
                "fix": STEP_FIX.get(UNSLUG.get(step))}

    actionable = sorted((s for s in found if s in UNSLUG), key=lambda s: -sum(r.get("spend") or 0 for r in found[s]))
    return [row(s) for s in actionable + [s for s in ("none", None) if s in found]]
