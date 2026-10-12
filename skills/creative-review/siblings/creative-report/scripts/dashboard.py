"""The creative report as a native Claude dashboard: a bundle of datasets and page files, and an offline check of one.

`write_bundle(ctx, out_dir)` writes, from the context report.build_report filled while it rendered the HTML:

  datasets/<id>.json   a JSON array of flat row objects per dataset, every number computed here in Python
  files/<name>         the page (index.html, dashboard.css, dashboard.js); it only formats and draws
  store/<doc>.json     the same page files and the title as ready store documents, for a write by file path
  manifest.json        {title, datasets: [{id, title, description, file, format}], files, store}

A value that could not be read is null with a reason column beside it ("n/a (missing <field>)"), never 0 and
never a dropped row. `check_bundle(dir)` lists what is wrong with a bundle; [] when nothing is. Standard library only.
"""
from __future__ import annotations

import base64
import datetime as dt
import errno
import html
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402
import interact  # noqa: E402
import panels  # noqa: E402
from panels import Ctx  # noqa: E402
from previews import Previews  # noqa: E402

PAGE = Path(__file__).resolve().parent.parent / "assets" / "claude-dashboard"
SCHEMA = Path(__file__).resolve().parent.parent / "references" / "dashboard-schema.json"
PAGE_FILES = ("index.html", "fonts.css", "dashboard.css", "dashboard.js")
DATASET_MAX = 8 * 1024 * 1024  # the dashboard type refuses an attached file over 8 MB
DOC_MAX = 256 * 1024  # and any one store document over 256 KB
ID_PATTERN = re.compile(r"[a-z0-9-]+\Z")
DIGITS = 6  # decimals kept on a computed number; the page formats it for show
THUMBS_NONE = "No previews or thumbnails were supplied."
REACH_REASON = "n/a (needs an account-level reach and frequency for this window)"
REACH_NOTE = ("Reach and frequency don't add up across ads, so the account's Reach and Frequency key numbers need an account-level figure for "
              "this window and read n/a; none was supplied. Each ad's own frequency still shows on its card and in its detail. "
              "To get the key numbers: pull account-level reach and frequency for the same window and add them when you rebuild this report.")
VIDEO_PREVIEWS = "Video plays only in the HTML version of this report; the dashboard shows each ad's image or video still."
TABLE_METRICS = ("roas", "cpa", "ctr", "hook_rate")


def _blank(value: Any) -> Any:
    """An empty string is a missing value: it is null with its reason, never a set value beside a note."""
    return None if value is None or (isinstance(value, str) and not value.strip()) else value


def _num(value: Optional[float]) -> Optional[float]:
    value = _blank(value)
    return None if value is None else round(float(value), DIGITS)


def _plain(text: str) -> str:
    """A note written for the HTML page as plain words: tags dropped, entities read."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _ad_key(record: Dict[str, Any]) -> str:
    return str(record["id"])


ID_PART = re.compile(r"\u2026?\d{6,}|\u2026\d+")


def short_label(label: str) -> str:
    """An ad's label for a title: the parts of its name, without the long ad id or the id tail the label adds to tell ads apart."""
    parts = [part for part in label.split(" \u00b7 ") if not ID_PART.fullmatch(part.strip())]
    return " \u00b7 ".join(parts) or label


def _is_video(ad: Optional[Dict[str, Any]]) -> bool:
    """A video ad: one with 3-second plays, or whose format names video when the pull has no play counts."""
    plays = ad.get("video_views_3s") if ad else None
    return (plays is not None and plays > 0) or "video" in str((ad or {}).get("format") or "").lower()


NOT_VIDEO = "n/a (not a video ad)"
FORMAT_NOT_KNOWN = "n/a (format not known, so not known to be a video ad)"
VIDEO_METRICS = ("hook_rate", "hold_rate")


def _video_flag(ad: Optional[Dict[str, Any]]) -> Optional[bool]:
    """True for a video ad (plays, or a format that names video); False when its format is known and is not video; None when the format is
    not known and it has no plays, since a recorded 0 plays does not say what the ad is."""
    if ad is None:
        return None
    if _is_video(ad):
        return True
    return None if _video_note(ad) == FORMAT_NOT_KNOWN else False


def _video_note(ad: Optional[Dict[str, Any]]) -> str:
    """Why a video-only rate is blank on an ad with no plays: not a video when its format says so, unknown when the pull names no format."""
    return FORMAT_NOT_KNOWN if str((ad or {}).get("format") or "").strip().lower() in ("", "unknown") else NOT_VIDEO


# ---------- datasets: each a list of flat rows, computed by the same code the HTML uses ----------

def unscored_formats(ctx: Ctx) -> str:
    """Which ads the format scorecard leaves out: ads whose format is not one the mix file scored, with their share of spend."""
    found = panels.format_cells(ctx)
    if not found:
        return "n/a (no format scorecard in this run)"
    scored = {str(f["format"]) for f in found["formats"]}
    left = [r for r in ctx.records if str(r.get("format") or "unknown") not in scored]
    if not left:
        return "Every ad's format is in the scorecard."
    whole = sum(r.get("spend") or 0.0 for r in ctx.records)
    names = sorted({ctx.format_name(r.get("format") or "unknown") for r in left})
    share = " (%.1f%% of spend)" % (sum(r.get("spend") or 0.0 for r in left) / whole * 100) if whole else ""
    return "%d of %d ads%s are left out of the scorecard because their format was not scored: %s." % (len(left), len(ctx.records), share, ", ".join(names))


def concepts_shown(ctx: Ctx) -> str:
    found = panels.heatmap_grid(ctx) if ctx.mix and not ctx.mix.get("concepts_unread") else None
    if not found:
        return "n/a (no concept grid in this run)"
    shown, total = len(found["shown"]), len(found["families"])
    if shown == total:
        return "All %d concepts are shown." % total
    return "Showing the top %d of %d concepts by spend (an arbitrary display cap); %d hidden." % (shown, total, total - shown)


TOTALS_WORDS = {"neutral": "not checked against the account's own totals", "ok": "match the account's own totals"}


def header_rows(ctx: Ctx, images: str, payback: str, launched: str) -> List[Dict[str, Any]]:
    tone, words = ctx.completeness
    rows = [{"fact": "Title", "value": ctx.page_title, "tone": None}]
    rows += [{"fact": label, "value": value, "tone": None} for label, value in ctx.header_facts]
    rows += [{"fact": "Completeness", "value": words, "tone": tone}, {"fact": "Totals", "value": TOTALS_WORDS.get(tone, words), "tone": tone},
             {"fact": "Generated", "value": ctx.generated, "tone": None},
             {"fact": "Ad images", "value": images, "tone": None}, {"fact": "Previews", "value": VIDEO_PREVIEWS, "tone": None},
             {"fact": "Payback metric", "value": payback, "tone": None}, {"fact": "Launched in the window", "value": launched, "tone": None},
             {"fact": "Formats not scored", "value": unscored_formats(ctx), "tone": None},
             {"fact": "Concepts shown", "value": concepts_shown(ctx), "tone": None},
             {"fact": SCHEMA_FACT, "value": str(load_schema()["x-version"]), "tone": None}]
    return rows


def kpi_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    gone = {item["metrics"]: item["why"] for item in panels.not_in_pull(ctx)}
    out = []
    for tile in panels.kpi_tiles(ctx):
        reason: Optional[str] = None
        if tile["value"] is None:
            if tile["reason"]:
                reason = "n/a (%s)" % tile["reason"]
            elif tile["metric"] in panels.ACCOUNT_KPIS:
                reason = REACH_REASON
            else:
                reason = "n/a (%s)" % next((why for names, why in gone.items() if tile["base_name"] in names), "not in this pull")
        change = tile["change_pct"]
        out.append({"metric": tile["metric"], "name": tile["name"], "unit": tile["unit"].strip(" ()"), "value": _num(tile["value"]),
                    "value_note": reason, "shown": tile["shown"], "detail": "; ".join(n for n in tile["notes"] if n != tile["reason"]) or None,
                    "change_pct": _num(change), "change_pct_note": tile["change_note"] if ctx.prior else "n/a (no prior period supplied)",
                    "change_tone": panels.delta_tone(tile["metric"], change) if change is not None else None, "against": tile["against"]})
    return out


# Key numbers the HTML's over-time chart does not draw, so each key number card has its own daily line.
EXTRA_DAILY = (("impressions", "Impressions", "count"), ("conversions", "Purchases", "count"), ("conversion_value", "Purchase value", "money"),
               ("hold_rate", "Hold rate", "pct"))


def daily_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    cal = panels.calendar(ctx.rows)
    days = [day for day, _ in cal]
    found = []
    for key, name, kind in panels.TIME_METRICS + EXTRA_DAILY:
        values = panels.day_values(cal, key)
        if any(v is not None for v in values):
            unit = "%s (%s)" % (name, ctx.currency or "account currency") if kind == "money" else "%s (%%)" % name if kind == "pct" else \
                "%s (x)" % name if kind == "x" else name
            found.append({"key": key, "name": name, "kind": kind, "unit": unit, "values": values, "average": panels.rolling_values(cal, key)})
    gap = "n/a (fewer than %d days with data in the %d-day window)" % (panels.charts.ROLLING_MIN_VALUES, panels.charts.SPARK_AVERAGE_DAYS)
    totals = [panels.totals(rows) if rows else None for _, rows in cal]
    return [{"day": day, "metric": s["key"], "name": s["name"], "kind": s["kind"], "unit": s["unit"],
             "value": _num(value), "value_note": None if value is not None else _day_note(total, s["key"]),
             "average": _num(average), "average_note": None if average is not None else gap}
            for s in found for day, value, average, total in zip(days, s["values"], s["average"], totals)]


def _day_note(total: Optional[Dict[str, Any]], key: str) -> str:
    """Why a day has no value for a series: what that day's rows are missing, or no rows at all."""
    if total is None:
        return "n/a (no data this day)"
    if key in cm.METRICS:
        return _metric_note(total, key)
    return "n/a (missing %s)" % interact.FIELD_WORDS.get(key, key)


def pareto_rows(ctx: Ctx) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    info = panels.pareto_cut(ctx)
    if not info:
        return [], []
    ranked = info["ranked"]
    rows = [{"rank": i + 1, "ad_id": str(a.get("ad_id") or a.get("ad_name")), "label": ctx.label(a.get("ad_id") or a.get("ad_name")),
             "short_label": short_label(ctx.label(a.get("ad_id") or a.get("ad_name"))),
             "format": ctx.format_name(a.get("format") or "unknown"), "spend": _num(a["spend"]), "conversion_value": _num(a.get("conversion_value")),
             "conversion_value_note": None if a.get("conversion_value") is not None else "n/a (no purchase value recorded)",
             "cum_spend_pct": _num(info["cum_spend"][i]), "cum_basis_pct": _num(info["cum_basis"][i]), "in_head": i < info["cut"]}
            for i, a in enumerate(ranked)]
    tail = ranked[info["cut"]:]
    unread = sum(1 for a in tail if a.get("conversion_value") is None)
    tail_value_note = ("n/a (no purchase value)" if not info["has_value"] else
                       "n/a (%d of %d long-tail ads have no purchase value recorded)" % (unread, len(tail)) if unread else None)
    share = cm.concentration(ranked, top_n=ctx.concentration_n)
    whole = sum(a["spend"] for a in ranked)
    unspent = sum(1 for r in ctx.records if not r.get("spend"))
    cut = [{"ads": len(ranked), "cut": info["cut"], "ads_pct": _num(info["cut"] / len(ranked) * 100), "head_share_pct": _num(info["head_basis"]),
            "basis": "purchase value" if info["has_value"] else "spend", "setting_pct": _num(ctx.pareto_share),
            "sentence": panels.pareto_sentence(ctx, info), "coverage": info.get("coverage"),
            "top_n": ctx.concentration_n, "concentration_pct": _num(share),
            "concentration_pct_note": None if share is not None else "n/a (no spend to share out)",
            "tail_ads": len(tail), "tail_spend": _num(sum(a["spend"] for a in tail)),
            "tail_spend_pct": _num(sum(a["spend"] for a in tail) / whole * 100) if whole else None,
            "tail_spend_pct_note": None if whole else "n/a (no spend to share out)",
            "head_spend_pct": _num(info["cum_spend"][info["cut"] - 1]) if info["cut"] else None,
            "head_spend_pct_note": None if info["cut"] else "n/a (no ad in the head)",
            "all_ads": len(ctx.records), "no_spend_ads": unspent,
            "tail_conversion_value": None if tail_value_note else _num(sum(a["conversion_value"] for a in tail)),
            "tail_conversion_value_note": tail_value_note}]
    return rows, cut


def _verdict_entries(ctx: Ctx) -> List[Dict[str, Any]]:
    return [dict(e, verdict_id=e.get("verdict_id") or "") for e in (ctx.verdicts or {}).get("ads") or []]


def board_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """One row per verdict, money at risk first, as the verdict board orders them; no rows without verdicts."""
    entries = _verdict_entries(ctx)
    if not entries:
        return []
    out = []
    for cls in panels.BOARD_ORDER:
        group = [e for e in entries if interact.entry_class(e) == cls]
        checks = list(dict.fromkeys(e.get("check") or interact.PAUSE_CHECK for e in group)) if cls == "kill" else []
        unread = sum(1 for e in group if e.get("spend_at_stake") is None and e.get("spend") is None)
        out.append({"verdict_class": interact.PUBLIC_ID.get(cls, cls), "verdict": interact.VERDICT_LABEL[cls], "ads": len(group),
                    "spend_at_stake": None if unread else _num(sum(panels._stake(e) for e in group)),
                    "spend_at_stake_note": "n/a (%d of %d ads have no spend recorded)" % (unread, len(group)) if unread else None,
                    "check": "; ".join(checks) or None, "next_step": interact.NEXT_STEP[cls]})
    return out


def verdict_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Every ad, grouped by verdict money-at-risk first and by spend at stake within; metric columns null with a reason when unread."""
    order = {interact.PUBLIC_ID.get(cls, cls): n for n, cls in enumerate(panels.BOARD_ORDER)}
    records = sorted(ctx.records, key=lambda r: (order.get(r["verdict"], len(order)), -(r.get("stake") or 0)))
    out = []
    for rec in records:
        key = _ad_key(rec)
        ad, entry = ctx.ad_index.get(key), ctx.verdict_index.get(key)
        cls = interact.entry_class(entry) if entry else None
        confidence, age_days, fatiguing = (_blank(rec.get(k)) for k in ("confidence", "age_days", "fatiguing"))
        spend, stake = _blank(rec.get("spend")), _blank(rec.get("stake"))
        row = {"ad_id": key, "label": rec["label"], "short_label": short_label(rec["label"]), "ad_name": rec.get("name"), "format": ctx.format_name(rec.get("format") or "unknown"),
               "verdict": interact.VERDICT_LABEL[cls] if cls else None,
               "verdict_note": None if cls else "n/a (no keep-or-kill verdict for this ad)",
               "verdict_class": interact.PUBLIC_ID.get(cls, cls) if cls else None, "confidence": confidence,
               "confidence_note": None if confidence is not None else "n/a (%s)" % ("no confidence given for this verdict" if cls else "no verdict supplied"),
               "spend": _num(spend), "spend_note": None if spend is not None else "n/a (no spend recorded for this ad)",
               "spend_at_stake": _num(stake),
               "spend_at_stake_note": None if stake is not None else "n/a (no spend recorded for this ad)", "age_days": age_days,
               "age_days_note": None if age_days is not None else "n/a (no ad age in the data)",
               "fatiguing": fatiguing,
               "fatiguing_note": None if fatiguing is not None else "n/a (fatigue could not be read for this ad)", "next_step": interact.NEXT_STEP.get(cls) if cls else None,
               "check": (entry.get("check") or interact.PAUSE_CHECK) if cls == "kill" else None}
        for metric in TABLE_METRICS:
            value = _blank(ad.get(metric)) if ad else None
            row[metric] = _num(value)
            row[metric + "_note"] = None if value is not None else (
                "n/a (%s)" % (cm.describe_missing(ad, metric) or "no value") if ad else "n/a (ad not in the data file)")
            if value is None and ad:
                row[metric + "_note"] = _video_note(ad) if metric in VIDEO_METRICS and not _is_video(ad) else interact.plain_ids(row[metric + "_note"])
        out.append(row)
    return out


def format_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    found = panels.format_cells(ctx)
    if not found:
        return []
    out = []
    for fmt in found["formats"]:
        name, line = fmt["format"], found["cells"][fmt["format"]]
        row = {"format": str(name), "name": ctx.format_name(name), "ads": fmt["ads"], "spend_share": _num(fmt.get("share")),
               "spend_share_note": None if fmt.get("share") is not None else "n/a (no spend)"}
        for key, _ in panels.FORMAT_COLUMNS:
            value, reason = line[key]
            row[key] = _num(value)
            row[key + "_note"] = None if value is not None else reason
            grade = found["bands"][key].get(name) if value is not None else None
            if grade and key == "hook_rate" and name in found["derived_formats"]:
                grade = "(derived) " + grade
            row[key + "_grade"] = grade
        out.append(row)
    return out


def white_space_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    found = panels.heatmap_grid(ctx) if ctx.mix and not ctx.mix.get("concepts_unread") else None
    if not found:
        return []
    gaps = panels._gap_cells(ctx, found["shown"])
    return [{"concept": interact.humanise(concept, True), "format": ctx.format_name(fmt), "ads": found["cells"][i][j][0],
             "spend": _num(found["cells"][i][j][1]), "gap": gaps.get((i, j))}
            for i, concept in enumerate(found["shown"]) for j, fmt in enumerate(found["formats"])]


def gap_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    if not ctx.mix or ctx.mix.get("concepts_unread"):
        return []
    found = panels.heatmap_grid(ctx)
    shown = set(found["shown"]) if found else set()
    out = []
    for gap, row in zip(ctx.gaps, panels.gap_rows(ctx)):
        concept, fmt = panels._plain(gap["concept"]), panels._plain(gap["format"])
        because = row["why"].split(", and %s in %s " % (concept, fmt))[0]
        out.append({"number": row["number"], "label": row["label"], "why": row["why"], "because": because,
                    "concept": interact.humanise(gap["concept"], True), "format": ctx.format_name(gap["format"]),
                    "cell_ads": gap["ads"], "in_grid": gap["concept"] in shown})
    return out


def _refs(ctx: Ctx, ids: Sequence[Any]) -> str:
    return "; ".join(ctx.label(i) if str(i) in ctx.record_index else "%s (ad not in this data)" % i for i in ids) or "n/a (no neighbouring ad found)"


def briefing_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Finished briefs from the briefs file, else the brief starters the HTML shows; one shape for both."""
    if ctx.briefs:
        not_stated = panels.briefing.NOT_STATED
        return [{"number": n, "kind": "brief", "title": b["title"],
                 "details": "\n".join("%s: %s" % pair for pair in (
                     ("Objective", b["objective"]), ("Persona", b["persona"]), ("Stage", b["stage"]), ("Message", b["message"]),
                     ("Hook options", "; ".join(b["hooks"]) or not_stated), ("Format", b["format"]), ("Specs", b["specs"]))),
                 "references": _refs(ctx, b["reference_ads"]) if b["reference_ads"] else not_stated,
                 "judged": "; ".join(interact.metric_label(m["id"]) if m["defined"] else "%s (not a defined metric)" % m["id"]
                                     for m in b["judged_by"]) or not_stated,
                 "prompt": None, "prompt_note": "n/a (a finished brief)"} for n, b in enumerate(ctx.briefs, 1)]
    return [{"number": n, "kind": "starter", "title": s["title"],
             "details": "\n".join(["Why: %s" % s["why"], "Format: %s" % interact.humanise(s["format"], True)]
                                  if panels._says_title(s["make"], s["title"]) else
                                  ["What to make: %s" % s["make"], "Why: %s" % s["why"], "Format: %s" % interact.humanise(s["format"], True)]),
             "references": _refs(ctx, s["refs"]), "judged": s["judged"], "prompt": s["prompt"], "prompt_note": None}
            for n, s in enumerate(panels._starters(ctx), 1)]


def note_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Every footer and caveat line, plus what this pull could not show; numbered so a table can key on them."""
    lines = [("not-in-pull", "%s: %s. To get it: %s." % (i["metrics"], i["why"], i["how"])) for i in panels.not_in_pull(ctx)]
    if "reach" in panels.gone_metrics(ctx):
        lines.append(("not-in-pull", REACH_NOTE))
    lines += [("method", line) for line in ctx.method_lines]
    lines += [("caveat", _plain(note)) for note in ctx.caveats] or [("caveat", "Nothing was missing from the inputs.")]
    return [{"id": n, "section": section, "text": text} for n, (section, text) in enumerate(lines, 1)]


# ---------- ad-level series, media and baselines (the page's ad cards, ad detail and trends) ----------

SERIES_METRICS = ("payback", "hook_rate", "ctr", "frequency")  # per ad per day, beside spend; payback is the account objective's metric
BASELINE_METRICS = ("roas", "cpa", "ctr", "cpm", "hook_rate", "hold_rate", "frequency")
LOW_DELIVERY = 1000  # the impressions an ad needs before its rates are compared, as in creative_metrics.baseline
CURVE_MIN_ADS = 3  # arbitrary default: a delivery day's median band needs this many ads with a value that day; set your own
THUMB_MAX_KB = 160  # arbitrary default: a preview larger than this is not carried; the connector's thumbnail is tried instead
MEDIA_BUDGET_KB = 5600  # the images' share of the 8 MB data file, leaving room for base64 and the other columns
NO_DELIVERY = "n/a (no delivery this day)"
SERIES_LEFT_OUT = "n/a (left out: with this ad's daily rows the data file would pass the 8 MB limit)"
THUMB_REASONS = {"too large": "n/a (thumbnail not included: over the size limit for one image)",
                 "size budget reached": "n/a (thumbnail not included: the size limit for all images was reached)",
                 "no preview fetched": "n/a (no preview or thumbnail was supplied for this ad)",
                 "unrecognised image type": "n/a (the image file is not a PNG, JPEG, GIF or WebP)"}


def payback_metric(ctx: Ctx) -> Tuple[str, str]:
    """(metric id, note) for the payback measure the page charts per ad: the first payback metric of the account's most common objective."""
    counts: Dict[str, List[float]] = {}
    for rec in ctx.records:
        if rec.get("objective"):
            counts.setdefault(rec["objective"], []).append(rec.get("spend") or 0.0)
    ranked = sorted(counts, key=lambda o: (-len(counts[o]), -sum(counts[o]), str(o)))
    found = cm.payback_metrics(ranked[0] if ranked else None)
    metric = found["metrics"][0]
    return metric, "%s, the payback measure for %s%s" % (interact.metric_label(metric), found["objective"],
                                                         " (%s)" % found["note"] if found["note"] else "")


def _metric_note(total: Dict[str, Any], metric: str) -> str:
    return interact.plain_ids("n/a (%s)" % (cm.describe_missing(total, metric) or "no value"))


def _ad_days(ctx: Ctx, key: str) -> List[Tuple[str, Dict[str, Any]]]:
    """An ad's own days, each with its rows summed; days the ad has no row for are not its days."""
    days: Dict[str, List[Dict[str, Any]]] = {}
    for row in ctx.rows_by_ad.get(key, []):
        day = panels._day(row)
        if day:
            days.setdefault(day, []).append(row)
    out = []
    for day in sorted(days):
        total = panels.totals(days[day])
        if len(days[day]) == 1:
            total["reach"] = days[day][0].get("reach")
        out.append((day, total))
    return out


BEFORE_WINDOW = "n/a (running before the window began; its launch day is not in the data)"


def window_start(ctx: Ctx) -> Optional[str]:
    days = [d for d in (panels._day(r) for r in ctx.rows) if d]
    return min(days) if days else None


def launch_day(ctx: Ctx, series: Sequence[Dict[str, Any]], start: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(launch day, note): the ad's first day with impressions, else null with the reason. An ad with a row of any kind on the window's
    first day (`start`, from window_start), or created before it, was already running when the window opened, so its first delivery
    here is not its launch."""
    first = next((r["day"] for r in series if r["delivery_day"] == 1), None)
    if first is None:
        return None, "n/a (no day with impressions in the window)"
    start = start or first
    created = [d for d in (cm._parse_date(r.get("created_time")) for r in ctx.rows_by_ad.get(series[0]["ad_id"], [])) if d]
    if series[0]["day"] <= start or (created and min(created).isoformat() < start):
        return None, BEFORE_WINDOW
    return first, None


def ad_series(ctx: Ctx, key: str, payback: str) -> List[Dict[str, Any]]:
    """One row per day the ad has data: spend and each series metric, null with its reason; delivery_day counts days with impressions."""
    out, delivered = [], 0
    video = _is_video(ctx.ad_index.get(key))
    for day, total in _ad_days(ctx, key):
        live = (total.get("impressions") or 0) > 0
        delivered += live
        values = cm.compute_metrics(total)
        row = {"ad_id": key, "day": day, "delivery_day": delivered if live else None, "delivery_day_note": None if live else NO_DELIVERY,
               "spend": _num(total.get("spend")), "spend_note": None if total.get("spend") is not None else "n/a (no spend recorded this day)"}
        for column in SERIES_METRICS:
            metric = payback if column == "payback" else column
            value = values.get(metric) if live else None
            row[column] = _num(value)
            row[column + "_note"] = (None if value is not None else NO_DELIVERY if not live else
                                     _video_note(ctx.ad_index.get(key)) if metric in VIDEO_METRICS and not video else _metric_note(total, metric))
        out.append(row)
    return out


def _by_spend(ctx: Ctx) -> List[Dict[str, Any]]:
    return sorted(ctx.records, key=lambda r: (-(r.get("spend") or 0), str(r["id"])))


def ad_daily_rows(ctx: Ctx, payback: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Every ad's daily rows, largest spend first, while the file stays under the 8 MB limit; {ad: reason} for each ad left out."""
    rows: List[Dict[str, Any]] = []
    size, left_out = 2, {}
    for rec in _by_spend(ctx):
        series = ad_series(ctx, str(rec["id"]), payback)
        cost = len(_dump(series))
        if left_out or size + cost > DATASET_MAX:
            if series:
                left_out[str(rec["id"])] = SERIES_LEFT_OUT
            continue
        rows += series
        size += cost
    return rows, left_out


def _thumbs(ctx: Ctx) -> Dict[str, Dict[str, Optional[str]]]:
    """{ad: {thumb, thumb_note}}: the preview if it is small enough, else the connector's thumbnail, largest spend first within the budget."""
    previews = ctx.previews
    if not (previews.preview_dir or previews.thumb_dir):
        return {}
    found = Previews(str(previews.preview_dir) if previews.preview_dir else None, str(previews.thumb_dir) if previews.thumb_dir else None,
                     THUMB_MAX_KB, MEDIA_BUDGET_KB)
    out = {}
    for rec in _by_spend(ctx):
        key = str(rec["id"])
        uri = found.embed(key)
        reason = found.resolve(key)["reason"]
        out[key] = {"thumb": uri, "thumb_note": None if uri else THUMB_REASONS.get(str(reason), "n/a (%s)" % reason)}
    return out


def media_rows(ctx: Ctx, left_out: Dict[str, str], series_days: Dict[str, int], payback: str) -> List[Dict[str, Any]]:
    """One row per ad: label, format, verdict, whether it is a video, its image or why there is none, and why it got its verdict."""
    thumbs = _thumbs(ctx)
    start = window_start(ctx)
    out = []
    for rec in _by_spend(ctx):
        key = str(rec["id"])
        entry = ctx.verdict_index.get(key)
        cls = interact.entry_class(entry) if entry else None
        ad = ctx.ad_index.get(key)
        sentence = panels.strip_confidence(str(entry["sentence"]), entry.get("confidence")) if entry and entry.get("sentence") else None
        image = thumbs.get(key) or {"thumb": None, "thumb_note": "n/a (no preview or thumbnail folder was passed)"}
        days = series_days.get(key)
        series = ad_series(ctx, key, payback)
        launched, launch_note = launch_day(ctx, series, start)
        spends = [r["spend"] for r in series if r["spend"] is not None]
        impressions = ad.get("impressions") if ad else None
        out.append({"ad_id": key, "label": rec["label"], "short_label": short_label(rec["label"]), "format": ctx.format_name(rec.get("format") or "unknown"),
                    "verdict": interact.VERDICT_LABEL[cls] if cls else None, "verdict_note": None if cls else "n/a (no keep-or-kill verdict for this ad)",
                    "verdict_class": interact.PUBLIC_ID.get(cls, cls) if cls else None,
                    "low_delivery": None if impressions is None else impressions < LOW_DELIVERY,
                    "low_delivery_note": None if impressions is not None else "n/a (no impressions recorded for this ad)",
                    "spend": _num(rec.get("spend")), "spend_note": None if rec.get("spend") is not None else "n/a (no spend recorded for this ad)",
                    "is_video": _video_flag(ad),
                    "is_video_note": "n/a (ad not in the data file)" if ad is None else FORMAT_NOT_KNOWN if _video_flag(ad) is None else None,
                    "thumb": image["thumb"], "thumb_note": image["thumb_note"],
                    "reason": interact.plain_ids(sentence) if sentence else None,
                    "reason_note": None if sentence else "n/a (%s)" % ("no reason given with the verdict" if cls else "no keep-or-kill verdict for this ad"),
                    "check": (entry.get("check") or interact.PAUSE_CHECK) if cls == "kill" else None,
                    "series_days": days, "series_days_note": None if days else left_out.get(key, "n/a (no dated rows for this ad)"),
                    "launch_day": launched, "launch_day_note": launch_note,
                    "peak_spend": max(spends) if spends else None, "peak_spend_note": None if spends else "n/a (no spend recorded on any day)"})
    return out


def _label(metric: str) -> str:
    """A metric's label as a heading: its first letter capitalised."""
    text = interact.metric_label(metric)
    return text[:1].upper() + text[1:]


def _kind(metric: str) -> str:
    return "money" if metric in ("cpa", "cpm", "cpc", "cost_per_lead", "spend") else "x" if metric == "roas" else "num" if metric == "frequency" else "pct"


def ad_metric_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Each ad's key rates beside the median and quartiles of the other ads in this account: the same format when enough share it, else all."""
    out = []
    for rec in _by_spend(ctx):
        key = str(rec["id"])
        ad = ctx.ad_index.get(key)
        others = [a for a in ctx.ads if str(a.get("ad_id") or a.get("ad_name")) != key]
        group_key = str((ad or {}).get("format") or "unknown")
        for metric in BASELINE_METRICS:
            base = cm.baseline(others, metric, group_by=("format",))
            stats = base["groups"].get(group_key) or base["account"]
            value = _blank(ad.get(metric)) if ad else None
            same = stats.get("basis") == "group"
            group = ("the other %d %s ads" % (stats["n_group"], ctx.format_name(group_key)) if same else
                     "no other ad with %s" % interact.metric_label(metric) if not base["account"]["n"] else
                     "the other %d ads with %s (too few other %s ads to compare within)" % (base["account"]["n"], interact.metric_label(metric),
                                                                                           ctx.format_name(group_key)))
            note = None
            if value is None:
                note = (_video_note(ad) if metric in VIDEO_METRICS and ad and not _is_video(ad) else
                        _metric_note(ad, metric) if ad else "n/a (ad not in the data file)")
            out.append({"ad_id": key, "metric": metric, "name": _label(metric), "kind": _kind(metric),
                        "better": "higher" if metric in cm.HIGHER_IS_BETTER else "lower" if metric in cm.LOWER_IS_BETTER else None,
                        "value": _num(value), "value_note": note,
                        "median": _num(stats["median"]), "p25": _num(stats["p25"]), "p75": _num(stats["p75"]),
                        "median_note": None if stats["median"] is not None else "n/a (no ad with at least %d impressions has a value)" % base["min_impressions"],
                        "group": group})
    return out


def age_curve_rows(ctx: Ctx, payback: str) -> List[Dict[str, Any]]:
    """Per series metric and day since launch: the median and quartiles across the ads launched inside the window with a value that day."""
    by_metric: Dict[str, Dict[int, List[float]]] = {m: {} for m in SERIES_METRICS}
    start = window_start(ctx)
    for rec in ctx.records:
        series = ad_series(ctx, str(rec["id"]), payback)
        if launch_day(ctx, series, start)[0] is None:
            continue  # day N of an ad already running when the window opened is not day N since launch
        for row in series:
            for metric in SERIES_METRICS:
                if row["delivery_day"] is not None and row[metric] is not None:
                    by_metric[metric].setdefault(row["delivery_day"], []).append(row[metric])
    out = []
    for metric in SERIES_METRICS:
        days = by_metric[metric]
        real = payback if metric == "payback" else metric
        for day in range(1, max(days) + 1 if days else 1):
            stats = cm._stats(sorted(days.get(day, [])))
            enough = stats["n"] >= CURVE_MIN_ADS
            out.append({"metric": metric, "name": _label(real), "kind": _kind(real), "delivery_day": day, "ads": stats["n"],
                        "median": _num(stats["median"]) if enough else None, "p25": _num(stats["p25"]) if enough else None,
                        "p75": _num(stats["p75"]) if enough else None,
                        "median_note": None if enough else "n/a (fewer than %d ads launched in the window had a value on delivery day %d)" % (CURVE_MIN_ADS, day)})
    return out


def share_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Each day's spend split by format and by verdict, as a share of that day's spend; days with no spend are left out."""
    verdict_of = {str(r["id"]): r.get("verdict") or "none" for r in ctx.records}
    groups = {"format": lambda key: str(ctx.ad_format.get(key) or "unknown"), "verdict": lambda key: verdict_of.get(key, "none")}
    names = {"format": ctx.format_name, "verdict": lambda v: interact.PUBLIC_LABEL.get(v, "No verdict")}
    out = []
    for dimension, group_of in groups.items():
        totals: Dict[str, float] = {}
        days: Dict[str, Dict[str, float]] = {}
        for row in ctx.rows:
            day, spend = panels._day(row), row.get("spend")
            if not day or spend is None:
                continue
            group = group_of(str(row.get("ad_id") or row.get("ad_name")))
            days.setdefault(day, {})
            days[day][group] = days[day].get(group, 0.0) + spend
            totals[group] = totals.get(group, 0.0) + spend
        ranked = [g for g in sorted(totals, key=lambda g: (-totals[g], g)) if totals[g] > 0]
        for day in sorted(days):
            whole = sum(days[day].values())
            if whole <= 0:
                continue
            out += [{"dimension": dimension, "day": day, "group": group, "name": names[dimension](group), "rank": n,
                     "spend": _num(days[day].get(group, 0.0)), "share_pct": _num(days[day].get(group, 0.0) / whole * 100)}
                    for n, group in enumerate(ranked, 1)]
    return out


VALUE_GAP_MAX_PCT = 5  # method setting, not a benchmark: past this share of spend in ad-days with no recorded value, the running return stops


def _unvalued(row: Dict[str, Any]) -> bool:
    """An ad-day with purchases but no recorded purchase value: its return cannot be read, so the running sums leave it out."""
    return (row.get("conversions") or 0) > 0 and row.get("conversion_value") is None


NO_VALUE = "No ad in the data carries a purchase value, so there is no running return."


def _left_out(ad_days: int, spend: float, whole: float) -> str:
    if not ad_days:
        return "Nothing left out: every ad-day with purchases has a recorded purchase value."
    return "%d ad-day%s with purchases but no recorded value %s left out (%s of spend)." % (
        ad_days, "" if ad_days == 1 else "s", "is" if ad_days == 1 else "are", "%.1f%%" % (spend / whole * 100 if whole else 0.0))


def cumulative_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Spend and purchase value per calendar day and summed from the first day, over the ad-days whose return can be read. An ad-day with
    purchases but no recorded value is left out of both running sums, and basis_note says how many and what share of spend so far; a blank
    purchase count is no purchases, as in the key numbers. If the left-out ad-days hold more than VALUE_GAP_MAX_PCT of the window's spend,
    the running value and return stop from the first of them on, with that reason. When no ad in the data carries a purchase value at all,
    every value, running spend and return is null with that reason, never 0, whatever share of spend the purchases hold. A day whose rows
    record neither spend nor purchases has no value either."""
    cal = panels.calendar(ctx.rows)
    whole = sum(r["spend"] for _, rows in cal for r in rows if r.get("spend") is not None)
    gap_spend = sum(r.get("spend") or 0.0 for _, rows in cal for r in rows if _unvalued(r))
    over = bool(whole) and gap_spend / whole * 100 > VALUE_GAP_MAX_PCT
    no_value = _metric_note({"spend": 1.0}, "roas")
    has_value = any(r.get("conversion_value") is not None for _, rows in cal for r in rows)
    out, cum_spend, cum_value, left_days, left_spend, broken = [], 0.0, 0.0, 0, 0.0, None
    for day, rows in cal:
        spends = [r["spend"] for r in rows if r.get("spend") is not None]
        spend = sum(spends) if spends else None
        unvalued = [r for r in rows if _unvalued(r)]
        read = [r for r in rows if not _unvalued(r)]
        recorded = [r["conversion_value"] for r in read if r.get("conversion_value") is not None]
        seen = any(r.get("spend") is not None or r.get("conversions") is not None for r in read)
        value = sum(recorded) if recorded else 0.0 if seen and has_value else None
        left_days += len(unvalued)
        left_spend += sum(r.get("spend") or 0.0 for r in unvalued)
        cum_spend += sum(r.get("spend") or 0.0 for r in read)
        cum_value += value or 0.0
        if over and unvalued and broken is None and has_value:
            broken = "ad-days with purchases but no recorded value hold %.1f%% of spend, over the %d%% this report allows; the first is on %s" % (
                gap_spend / whole * 100, VALUE_GAP_MAX_PCT, day)
        running = None if broken or not has_value else cum_value
        stopped = "n/a (%s)" % broken if broken else no_value
        out.append({"day": day, "spend": _num(spend), "spend_note": None if spend is not None else "n/a (no spend recorded this day)",
                    "cum_spend": _num(cum_spend) if has_value else None, "cum_spend_note": None if has_value else no_value,
                    "value": _num(value), "value_note": None if value is not None else no_value if rows else "n/a (no data this day)",
                    "cum_value": _num(running), "cum_value_note": None if running is not None else stopped,
                    "cum_roas": _num(running / cum_spend) if running is not None and cum_spend else None,
                    "cum_roas_note": None if running is not None and cum_spend else (
                        "n/a (no spend yet)" if running is not None else stopped),
                    "basis_note": _left_out(left_days, left_spend, cum_spend + left_spend) if has_value else NO_VALUE})
    return out


EMPTY = re.compile(r'<div class="empty"><p><b>Why this is empty:</b> (.*?)</p><p><b>How to get it:</b> (.*?)</p></div>', re.S)
UNREAD = re.compile(r'<div class="empty"><p>(.*?)</p></div>', re.S)


def section_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    """Each HTML panel's state as it rendered, with why and how for an empty one, so a section never shows a blank as an answer."""
    out = []
    for p in ctx.panel_states:
        found, unread = EMPTY.search(p["html"]), UNREAD.fullmatch(p["html"])
        why = found.group(1) if found else unread.group(1) if unread else None
        out.append({"tab": p["tab"], "panel": p["panel"], "heading": p["heading"], "state": p["state"],
                    "why": html.unescape(why) if why and p["state"] != "data" else None,
                    "how": html.unescape(found.group(2)) if found and p["state"] != "data" else None})
    return out


# ---------- the bundle ----------

DATASETS = (
    ("header", "Report header facts", "The report's title, window, scope, currency, source, attribution and whether the totals were reconciled."),
    ("sections", "Panel data states", "Whether each panel of the report had its data, and why and how to get it when it did not."),
    ("kpis", "Key numbers", "Account totals for the window, one row per key number, with the change against the prior period when one was supplied."),
    ("daily", "Daily performance", "Each measure per calendar day as a ratio of that day's sums, with a rolling average; a day with no data is a gap."),
    ("pareto", "Ads ranked by spend", "Every ad with spend, largest first, with the cumulative share of spend and of purchase value."),
    ("pareto-cut", "Pareto cut and concentration", "How many top-spend ads carry the set share of purchase value, and how concentrated spend is."),
    ("verdict-board", "Verdict counts", "How many ads got each keep-or-kill verdict and the spend at stake behind them."),
    ("verdicts", "Ad verdicts", "Every ad with its keep-or-kill verdict, confidence, spend at stake and key rates."),
    ("formats", "Format scorecard", "One row per format: ads, spend share and each rate, graded only against the account's other formats."),
    ("white-space", "Concept by format grid", "Ads and spend in each concept and format cell, with the numbered gaps worth testing."),
    ("gaps", "Gaps worth testing", "Empty or single-ad cells beside a concept or format that performs well in this account, strongest first."),
    ("briefing", "Briefs and starters", "Finished briefs from the briefs file, or brief starters built from the gaps and Iterate verdicts."),
    ("notes", "Method and caveats", "The basis, every default used, what was read from which column, and what was missing from the inputs."),
    ("ad-media", "Ad images and reasons", "One row per ad, largest spend first: its image as a data URL or why there is none, whether it is a video, and why it got its verdict."),
    ("ad-daily", "Daily series per ad", "Each ad's own days: spend, the payback measure, hook rate, CTR and frequency; null with the reason on a day the ad did not deliver."),
    ("ad-metrics", "Ads against comparable ads", "Each ad's key rates beside the median and middle half of ads in the same format in this account, or of all ads when too few share it."),
    ("age-curve", "Rates by delivery day", "For each series measure and day of an ad's delivery, the median and middle half across the ads with a value that day."),
    ("share-daily", "Daily spend share", "Each day's spend split by format and by verdict, as a share of that day's spend; days with no spend are left out."),
    ("cumulative", "Spend against value over time", "Spend and purchase value per day and summed from the first day, with the running return on spend."),
)


def build_datasets(ctx: Ctx) -> Tuple[Dict[str, List[Dict[str, Any]]], str]:
    """Every dataset's rows, and the words for the Ad images header fact."""
    pareto, cut = pareto_rows(ctx)
    metric, payback = payback_metric(ctx)
    ad_daily, left_out = ad_daily_rows(ctx, metric)
    series_days: Dict[str, int] = {}
    for row in ad_daily:
        series_days[row["ad_id"]] = series_days.get(row["ad_id"], 0) + 1
    media = media_rows(ctx, left_out, series_days, metric)
    size = len(_dump(media))
    for row in reversed(media):
        if size <= DATASET_MAX:
            break
        if row["thumb"]:
            before = len(_dump(row))
            row.update(thumb=None, thumb_note=THUMB_REASONS["size budget reached"])
            size -= before - len(_dump(row))
    images = THUMBS_NONE
    if ctx.previews.preview_dir or ctx.previews.thumb_dir:
        have = sum(1 for row in media if row["thumb"])
        images = "Images for %d of %d ads." % (have, len(media))
    started = sum(1 for row in media if row["launch_day"])
    launched = ("%d of %d ads first delivered after the window's first day; the day-of-delivery band uses only these, since an ad already "
                "running when the window opened has no launch day in the data." % (started, len(media)))
    rows = {"header": header_rows(ctx, images, payback, launched), "sections": section_rows(ctx), "kpis": kpi_rows(ctx), "daily": daily_rows(ctx),
            "pareto": pareto, "pareto-cut": cut, "verdict-board": board_rows(ctx), "verdicts": verdict_rows(ctx), "formats": format_rows(ctx),
            "white-space": white_space_rows(ctx), "gaps": gap_rows(ctx), "briefing": briefing_rows(ctx), "notes": note_rows(ctx),
            "ad-media": media, "ad-daily": ad_daily, "ad-metrics": ad_metric_rows(ctx), "age-curve": age_curve_rows(ctx, metric),
            "share-daily": share_rows(ctx), "cumulative": cumulative_rows(ctx)}
    return rows, images


def _dump(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _store_name(doc: str) -> str:
    return doc.replace("/", "-") + ".json"


LOGO = re.compile(r"\{\{logo ([a-z-]+\.svg)\}\}")


def logo_url(filename: str) -> str:
    """One of the report's brand SVGs as a data: URL, read from the assets the HTML report inlines."""
    return "data:image/svg+xml;base64," + base64.b64encode((PAGE.parent / filename).read_bytes()).decode("ascii")


def page_text(name: str) -> str:
    """A page file as the bundle ships it: the lockup's {{logo <file>}} slots become data: URLs of the report's own logo files."""
    text = (PAGE / name).read_text(encoding="utf-8")
    return LOGO.sub(lambda m: logo_url(m.group(1)), text) if name == "index.html" else text


def _write_into(root: Path, ctx: Ctx) -> Dict[str, Any]:
    for sub in ("datasets", "files", "store"):
        (root / sub).mkdir(parents=True)
    rows, _ = build_datasets(ctx)
    entries = []
    for dataset_id, title, description in DATASETS:
        path = "datasets/%s.json" % dataset_id
        (root / path).write_bytes(_dump(rows[dataset_id]))
        entries.append({"id": dataset_id, "title": title, "description": description, "file": path, "format": "json"})
    store = [{"doc": "dash/meta", "file": "store/" + _store_name("dash/meta")}]
    (root / store[0]["file"]).write_bytes(_dump({"title": ctx.page_title}))
    for name in PAGE_FILES:
        text = page_text(name)
        (root / "files" / name).write_text(text, encoding="utf-8")
        doc = "files/" + name
        store.append({"doc": doc, "file": "store/" + _store_name(doc)})
        (root / store[-1]["file"]).write_bytes(_dump({"text": text}))
    manifest = {"title": ctx.page_title, "datasets": entries, "files": list(PAGE_FILES), "store": store}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


SUBS = ("datasets", "files", "store")


def _swap_in(root: Path, scratch: Path) -> None:
    """Move the freshly built folders into root; if a move fails midway, put back what was moved before raising."""
    try:
        for sub in SUBS:
            if (root / sub).exists():
                (root / sub).rename(scratch / ("old-" + sub))
            (scratch / "new" / sub).rename(root / sub)
        os.replace(str(scratch / "new" / "manifest.json"), str(root / "manifest.json"))
    except OSError:
        for sub in SUBS:
            if (scratch / ("old-" + sub)).exists():
                shutil.rmtree(root / sub, ignore_errors=True)
                (scratch / ("old-" + sub)).rename(root / sub)
        raise


def _copy_in(root: Path, built: Path) -> None:
    for sub in SUBS:
        shutil.rmtree(root / sub, ignore_errors=True)
        shutil.copytree(built / sub, root / sub)
    shutil.copyfile(str(built / "manifest.json"), str(root / "manifest.json"))


def write_bundle(ctx: Ctx, out_dir: str) -> Dict[str, Any]:
    """Write the bundle for a rendered report's context into out_dir and return its manifest.

    The bundle is built in a scratch folder beside out_dir and moved in last, so a failed write leaves the old bundle whole
    and never a mix of old and new files; other files already in out_dir are left alone. Where a scratch folder beside
    out_dir cannot be made or moved across (a read-only parent, another filesystem), the bundle is written into out_dir
    in place instead and a warning says so."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    try:
        scratch = Path(tempfile.mkdtemp(prefix=".%s-" % (root.name or "bundle"), dir=str(root.resolve().parent)))
    except OSError as error:
        return _write_in_place(ctx, root, error)
    try:
        manifest = _write_into(scratch / "new", ctx)
        try:
            _swap_in(root, scratch)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            return _write_in_place(ctx, root, error)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return manifest


def _write_in_place(ctx: Ctx, root: Path, error: OSError) -> Dict[str, Any]:
    print("warning: cannot build the bundle beside %s (%s); writing it into the folder in place, so a failed write may leave a mix of old and new files"
          % (root, error), file=sys.stderr)
    with tempfile.TemporaryDirectory() as built:
        manifest = _write_into(Path(built) / "new", ctx)
        _copy_in(root, Path(built) / "new")
    return manifest


# ---------- the schema ----------

SCHEMA_FACT = "Schema version"
TYPES = {"string": lambda v: isinstance(v, str), "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
         "integer": lambda v: isinstance(v, int) and not isinstance(v, bool), "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None}


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def schema_columns(schema: Dict[str, Any], dataset_id: str) -> Dict[str, Dict[str, Any]]:
    return schema["$defs"][dataset_id]["items"]["properties"]


def _is_date(value: str) -> bool:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_rows(dataset_id: str, rows: Any, schema: Dict[str, Any]) -> List[str]:
    """Problems with one dataset's rows against dashboard-schema.json: the subset of JSON Schema it uses (type, required,
    additionalProperties false, enum, pattern, format date) plus its x-note rule: a value is null exactly when its note is set."""
    if dataset_id not in schema["$defs"]:
        return ["dataset %s has no entry in the schema" % dataset_id]
    if not isinstance(rows, list):
        return ["dataset %s is not an array of row objects" % dataset_id]
    spec = schema["$defs"][dataset_id]["items"]
    columns, required = spec["properties"], spec["required"]
    problems: List[str] = []
    for n, row in enumerate(rows):
        where = "dataset %s row %d" % (dataset_id, n)
        if not isinstance(row, dict):
            problems.append("%s is not an object" % where)
            continue
        problems += ["%s lacks the required column %s" % (where, c) for c in required if c not in row]
        problems += ["%s has a column the schema does not define: %s" % (where, c) for c in row if c not in columns]
        for name, value in row.items():
            rule = columns.get(name)
            if rule is None:
                continue
            kinds = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            if not any(TYPES[k](value) for k in kinds):
                problems.append("%s column %s is %r, not %s" % (where, name, value, " or ".join(kinds)))
                continue
            if "enum" in rule and value not in rule["enum"]:
                problems.append("%s column %s is %r, not one of %s" % (where, name, value, rule["enum"]))
            if isinstance(value, str) and "pattern" in rule and not re.search(rule["pattern"], value):
                problems.append("%s column %s does not read like %s: %r" % (where, name, rule["pattern"], value))
            if isinstance(value, str) and rule.get("format") == "date" and not _is_date(value):
                problems.append("%s column %s is not an ISO date: %r" % (where, name, value))
            note = rule.get("x-note")
            if note and (value is None) != (row.get(note) not in (None, "")):
                problems.append("%s column %s is %s but %s is %s: a missing value is null with its reason, never 0"
                                % (where, name, "null" if value is None else "set", note, "empty" if value is None else "set"))
    return problems


# ---------- the offline check ----------

HTML_SPACE = "\t\n\f\r "
HTML_TAG_OPEN = re.compile(r"</?[A-Za-z]")
HTML_COMMENT_END = re.compile(r"<!--(?:->|>|.*?--!?>)", re.S)  # "<!-->" and "<!--->" are whole comments; else up to "-->" or "--!>"
RAW_TEXT = ("script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript", "plaintext")  # no tags inside
REFUSED_TAGS = ("iframe", "frame", "frameset", "embed", "object", "base", "portal", "svg", "math", "noscript")  # frames, plug-ins, foreign markup
REFUSED_ATTRS = ("srcdoc", "attributionsrc")  # a whole page in an attribute; a request the browser sends on its own
LOCAL_FILE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9_-]+)*\.(?:html|css|js)\Z")  # a page file: a bare lowercase name, a type the check reads
FILE_ROLE = {"script": ("src", ".js"), "link": ("href", ".css")}  # the one file type each tag may load from the bundle
URL_ATTRS = ("src", "href", "srcset", "imagesrcset", "poster", "xlink:href", "action", "formaction", "data", "ping", "background")  # can load or link
IMAGE_DATA = re.compile(r"data:image/(?:png|jpeg|gif|webp|svg\+xml)(?:;[^,]*)?,", re.I)  # the data: URLs an <img> may show
TEXT_ATTRS = ("title", "alt", "value", "placeholder", "aria-label")  # attributes whose words a reader sees
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MARKUP_NUMBERS_OK: frozenset = frozenset()  # digit runs the page's visible text may carry; every other number comes from a dataset
FORBIDDEN_JS = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|localStorage|sessionStorage|indexedDB|eval)\b"
                          r"|\bFunction\s*\(|\bdocument\s*\.\s*coo[k]ie\b|\[\s*['\"`]coo[k]ie['\"`]\s*\]|\b(?:import|export)\b"
                          r"|\.\s*src\s*=(?!=)|\blocation\s*(?:\.\s*(?:href|assign|replace)\b|=(?!=))"
                          r"|\b(?:setTimeout|setInterval)\s*\(\s*['\"`]"
                          r"|\b(?:Worker|SharedWorker|serviceWorker|importScripts|srcset)\b|\bdocument\s*\.\s*write|\.\s*constructor\b"
                          r"|\b(?:window|self|globalThis|top|parent|opener)\s*\.\s*open\b|(?<![.\w])open\s*\(|\\[ux]", re.M)  # a \u or \x escape could spell any of these
_NUMBER = r"-?\d+(?:\.\d+)?"
NUMBER_ARRAY = re.compile(r"\[\s*%s(?:\s*,\s*%s)+\s*,?\s*\]" % (_NUMBER, _NUMBER))
NUMBER_OBJECT = re.compile(r"\{\s*[\w'\"]+\s*:\s*%s(?:\s*,\s*[\w'\"]+\s*:\s*%s)+\s*,?\s*\}" % (_NUMBER, _NUMBER))
CSS_NAME = re.compile(r"[\w\-\u0080-\U0010ffff]+")
CSS_HEX = re.compile(r"[0-9a-fA-F]{1,6}")
CSS_STRING_RUN = {q: re.compile(r"[^%s\\\n]+" % q) for q in "\"'"}
CSS_URL_RUN = re.compile(r"[^)\\]+")
CSS_LOADS = ("url", "src", "image", "image-set", "-webkit-image-set", "cross-fade", "-webkit-cross-fade")  # functions whose strings are addresses
CSS_FONT_LABELS = ("format", "tech", "local")  # functions in a src: whose strings are names, not addresses
ROOT_SELECTOR = re.compile(r"\.cr(?:-[\w-]*)?(?![\w-])")
OUTSIDE_SELECTOR = re.compile(r"(?<![\w.#-])(?:html|body)(?![\w-])|:(?:root|host)(?![\w-])", re.I)  # the host's page, never the dashboard's
FONT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 -]*\Z")  # a quoted family name in a custom property, as in "DM Sans"
RASTER_DATA = re.compile(r"data:image/(?:png|jpeg|gif|webp)(?:;[^,]*)?,", re.I)
FONT_DATA = re.compile(r"data:font/woff2;base64,[A-Za-z0-9+/]*={0,2}\Z")  # the one font type fonts.css embeds


def _html_parts(text: str) -> List[Tuple[str, str, str, Dict[str, str]]]:
    """Markup as a browser's tokenizer reads it: (kind, raw, name, attributes) with kind tag, end, text or raw (a script or style body).
    A ">" inside a quoted value does not end a tag, the first of two same-named attributes wins, and a script, style or other raw-text
    element runs to its own end tag."""
    out: List[Tuple[str, str, str, Dict[str, str]]] = []
    i, size = 0, len(text)

    def skip(j: int, chars: str) -> int:
        while j < size and text[j] in chars:
            j += 1
        return j

    while i < size:
        if text.startswith("<!--", i):
            found = HTML_COMMENT_END.match(text, i)
            i = found.end() if found else size
        elif HTML_TAG_OPEN.match(text, i):
            start, closing = i, text[i + 1] == "/"
            j = i + 1 + closing
            k = j
            while k < size and text[k] not in HTML_SPACE + "/>":
                k += 1
            name, attrs, j = text[j:k].lower(), {}, k
            while True:
                j = skip(j, HTML_SPACE + "/")
                if j >= size or text[j] == ">":
                    break
                k = j + 1
                while k < size and text[k] not in HTML_SPACE + "/>=":
                    k += 1
                attr, value, j = text[j:k].lower(), "", skip(k, HTML_SPACE)
                if j < size and text[j] == "=":
                    j = skip(j + 1, HTML_SPACE)
                    if j < size and text[j] in "\"'":
                        k = text.find(text[j], j + 1)
                        k = size if k < 0 else k
                        value, j = text[j + 1:k], k + 1
                    else:
                        k = j
                        while k < size and text[k] not in HTML_SPACE + ">":
                            k += 1
                        value, j = text[j:k], k
                attrs.setdefault(attr, value)
            i = min(size, j + 1)
            out.append(("end" if closing else "tag", text[start:i], name, attrs))
            if not closing and name in RAW_TEXT:
                found = re.compile(r"</%s(?=[%s/>])" % (name, HTML_SPACE), re.I).search(text, i) if name != "plaintext" else None
                body_end = found.start() if found else size
                out.append(("raw" if name in ("script", "style") else "text", text[i:body_end], name, {}))
                i = body_end
        elif text.startswith(("<!", "<?", "</"), i):
            end = text.find(">", i + 1)
            i = size if end < 0 else end + 1
        else:
            end = text.find("<", i + 1)
            end = size if end < 0 else end
            out.append(("text", text[i:end], "", {}))
            i = end
    return out


def _code(text: str) -> str:
    """Script source without its comments, so words in a comment are not read as calls."""
    return re.sub(r"(?m)(?<![:\"'\\])//.*$", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def _script_problems(name: str, source: str) -> List[str]:
    """Every script rule, run on the source as written and on it with comments dropped, so a comment-stripping slip hides nothing."""
    out: List[str] = []
    for text in (source, _code(source)):
        if re.search(r"\.innerHTML\b|\.outerHTML\b|insertAdjacentHTML|\.html\(", text):
            out.append("%s writes markup from script (innerHTML or .html()); use textContent or .text()" % name)
        found = FORBIDDEN_JS.search(text)
        if found:
            out.append("%s uses %s, which the dashboard does not allow: no network, storage, cookies, modules, eval, redirects or script loads"
                       % (name, found.group(0).strip()))
        if NUMBER_ARRAY.search(text) or NUMBER_OBJECT.search(text):
            out.append("%s has an array or object of number literals; every number must come from a dataset" % name)
    return list(dict.fromkeys(out))


def _css_escape(css: str, i: int) -> Tuple[str, int]:
    """The character a backslash at css[i] stands for, and where reading resumes: a browser reads CSS escapes before anything else."""
    found = CSS_HEX.match(css, i + 1)
    if found:
        end = found.end() + (found.end() < len(css) and css[found.end()] in " \t\n")
        code = int(found.group(), 16)
        return (chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "\ufffd"), end
    return (css[i + 1], i + 2) if i + 1 < len(css) else ("\ufffd", i + 1)


def _css_tokens(css: str) -> List[Tuple[str, str]]:
    """CSS as a browser tokenizes it, escapes decoded: (kind, value) with kind ws, string, url, function, at, ident or delim.
    A comment is only a comment outside a string, and an escaped character is part of a name, never punctuation."""
    css = re.sub(r"\r\n?|\f", "\n", css).replace("\0", "\ufffd")
    out: List[Tuple[str, str]] = []
    i, size = 0, len(css)

    def name(i: int) -> Tuple[str, int]:
        text = ""
        while i < size:
            run = CSS_NAME.match(css, i)
            if run:
                text, i = text + run.group(), run.end()
            elif css[i] == "\\" and css[i + 1:i + 2] != "\n":
                char, i = _css_escape(css, i)
                text += char
            else:
                break
        return text, i

    while i < size:
        char = css[i]
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = size if end < 0 else end + 2
            out.append(("ws", " "))
        elif char in " \t\n":
            i += 1
            out.append(("ws", " "))
        elif char in "\"'":
            parts, i = [], i + 1
            while i < size and css[i] != char and css[i] != "\n":
                run = CSS_STRING_RUN[char].match(css, i)
                if run:
                    parts.append(run.group())
                    i = run.end()
                elif css[i + 1:i + 2] == "\n":
                    i += 2
                else:
                    decoded, i = _css_escape(css, i)
                    parts.append(decoded)
            i += i < size and css[i] == char
            out.append(("string", "".join(parts)))
        elif CSS_NAME.match(css, i) or (char == "\\" and css[i + 1:i + 2] != "\n"):
            text, i = name(i)
            if css.startswith("(", i):
                i += 1
                rest = i
                while rest < size and css[rest] in " \t\n":
                    rest += 1
                if text.lower() == "url" and not (rest < size and css[rest] in "\"'"):
                    parts, i = [], rest
                    while i < size and css[i] != ")":
                        run = CSS_URL_RUN.match(css, i)
                        if run:
                            parts.append(run.group())
                            i = run.end()
                        else:
                            decoded, i = _css_escape(css, i)
                            parts.append(decoded)
                    i += 1
                    out.append(("url", "".join(parts)))
                else:
                    out.append(("function", text.lower()))
            else:
                out.append(("ident", text))
        elif char == "@" and i + 1 < size and (CSS_NAME.match(css, i + 1) or css[i + 1] == "\\"):
            text, i = name(i + 1)
            out.append(("at", text.lower()))
        else:
            i += 1
            out.append(("delim", char))
    return out


def _css_text(tokens: Sequence[Tuple[str, str]]) -> str:
    """Tokens written back as CSS text, a string's words dropped so a comma or brace in one is not read as punctuation."""
    return "".join('""' if k == "string" else v + "(" if k == "function" else "url()" if k == "url" else "@" + v if k == "at" else v
                   for k, v in tokens).strip()


def _address(value: str) -> str:
    """An address as a browser's URL parser reads it: outer spaces and control characters dropped, tabs and newlines removed."""
    return re.sub(r"[\t\n\r]", "", value).strip("".join(map(chr, range(0x21))))


def _outside_selector(selector: str) -> bool:
    """Whether a selector can match outside the dashboard: it does not start at a .cr class, names the host's html, body or :root, or
    steps from its first compound to a sibling with ~ or +, which from the .cr root is an element of the host's page."""
    if not ROOT_SELECTOR.match(selector) or OUTSIDE_SELECTOR.search(selector):
        return True
    depth = 0
    for i, char in enumerate(selector):
        depth += (char in "([") - (char in ")]")
        if depth == 0 and (char in HTML_SPACE + ">~+"):
            return selector[i:].lstrip(HTML_SPACE)[:1] in ("~", "+")
    return False


def _style_problems(name: str, css: str) -> List[str]:
    """Problems in one stylesheet, read from its tokens as a browser reads them: a selector outside the page's own .cr classes, any
    load (url(), image-set(), src:, @import) of anything but a data: URL of a png, jpeg, gif or webp image (and in fonts.css the woff2
    font it embeds), an outside address in any string, a custom property holding a string that is not a font name or such a data: URL,
    a var() inside a loading function (it could carry an address in), and a number in a content string."""
    fonts = name == "fonts.css"
    allowed = "a data: URL of a png, jpeg, gif or webp image" + (" or a woff2 font" if fonts else "")

    def ok(value: str) -> bool:
        address = _address(value)
        return bool(RASTER_DATA.match(address) or (fonts and FONT_DATA.match(address)))

    out: List[str] = []
    stack: List[Tuple[str, bool]] = []  # open blocks "{", brackets "(" "[" and functions, each with whether it holds a string
    prelude: List[Tuple[str, str]] = []
    prop: Optional[str] = None
    tokens = _css_tokens(css)
    for n, (kind, value) in enumerate(tokens):
        functions = [f for f, _ in reversed(stack[next((k + 1 for k in range(len(stack) - 1, -1, -1) if stack[k][0] == "{"), 0):])]
        in_parens = bool(functions)
        if kind == "at" and value == "import":
            out.append("%s imports a stylesheet: %s" % (name, _css_text(tokens[n:n + 4])[:60]))
        elif kind == "at" and value in ("font-face", "page") and not fonts:
            out.append("%s has an @%s rule, which only the bundle's fonts.css may carry" % (name, value) if value == "font-face"
                       else "%s has an @page rule, which the dashboard does not use" % name)
        elif kind == "url" and not ok(value):
            out.append("%s loads %s from a url(), which must be %s" % (name, _address(value)[:60], allowed))
        elif kind == "string":
            if stack and stack[-1][0] != "{":
                stack[-1] = (stack[-1][0], True)
            address = _address(value)
            if re.match(r"(?:https?:|[/\\]{2})", address, re.I):
                out.append("%s names %s in a string, which must be a data: URL" % (name, address[:60]))
            loader = next((f for f in functions if f in CSS_LOADS), None)
            if loader and not ok(value):
                out.append("%s loads %s from %s(), which must be %s" % (name, address[:60], loader, allowed))
            elif prop == "src" and not ok(value) and not (functions and functions[0] in CSS_FONT_LABELS):
                out.append("%s loads %s from src:, which must be %s" % (name, address[:60], allowed))
            elif prop and prop.startswith("--") and not ok(value) and not FONT_NAME.match(value):
                out.append("%s puts %r in the custom property %s, which may hold only a font name or %s" % (name, value[:60], prop, allowed))
            if prop and prop.endswith("content"):
                out += ["%s has the number %s in a content string; every number must come from a dataset" % (name, found)
                        for found in sorted(set(NUMBER.findall(value)) - MARKUP_NUMBERS_OK)]
        if kind == "function":
            loader = next((f for f in functions if f in CSS_LOADS), None)
            if value in ("var", "attr") and loader:
                out.append("%s reads %s() inside %s(), which must hold %s written out" % (name, value, loader, allowed))
            stack.append((value, False))
        elif kind == "delim" and value in "([":
            stack.append((value, False))
        elif kind == "delim" and value in ")]" and stack and (stack[-1][0] == "[") == (value == "]") and stack[-1][0] != "{":
            closed, held = stack.pop()
            if closed in ("url", "src") and not held:
                out.append("%s has a %s() with no address in it, which must be %s" % (name, closed, allowed))
        elif kind == "delim" and value == "{":
            if not in_parens:
                head = _css_text(prelude)
                if not head.startswith("@"):
                    out += ["%s styles %r, which is not under the page's own .cr classes" % (name, sel.strip())
                            for sel in re.split(r",(?![^()\[\]]*[)\]])", head) if _outside_selector(sel.strip())]
            stack.append(("{", False))
            prelude, prop = [], None
        elif kind == "delim" and value == "}" and stack and stack[-1][0] == "{":
            stack.pop()
            prelude, prop = [], None
        elif kind == "delim" and value == ";" and not in_parens:
            prelude, prop = [], None
        if kind != "delim" or value not in "{};" or in_parens:
            if kind == "delim" and value == ":" and not in_parens and stack and prop is None and [k for k, _ in prelude if k != "ws"] == ["ident"]:
                prop = next(v for k, v in prelude if k == "ident").lower()
            prelude.append((kind, value))
    if stack:
        out.append("%s leaves a block, bracket or function open, so a browser would read what follows it differently" % name)
    return list(dict.fromkeys(out))


def _mark_problems(name: str, text: str, files: Sequence[Any], columns: Dict[str, set]) -> List[str]:
    """Problems in one page's tags: frames, plug-ins and foreign markup, loads from outside the bundle, data: URLs anywhere but an
    image on <img>, on...= attributes and every data-* mark."""
    out: List[str] = []
    table_source = ""
    for kind, tag, element, attrs in _html_parts(text):
        if kind == "end" and element == "table":
            table_source = ""
        if kind != "tag":
            continue
        if element in REFUSED_TAGS or element == "meta" and "http-equiv" in attrs:
            out.append("%s has a <%s> tag, which the dashboard does not allow: %s" % (name, element, tag[:80]))
        out += ["%s has a %s attribute, which the dashboard does not allow: %s" % (name, attr, tag[:80]) for attr in REFUSED_ATTRS if attr in attrs]
        if "style" in attrs:
            out += _style_problems(name + " style attribute", ".cr{%s}" % html.unescape(attrs["style"]))
        if element == "script" and attrs.get("type", "").strip().lower() not in ("", "text/javascript"):
            out.append("%s has a script of type %r, which the dashboard does not run: only a plain script is allowed" % (name, attrs["type"]))
        if any(attr.startswith("on") for attr in attrs):
            out.append("%s has an on...= attribute, which the dashboard does not run: %s" % (name, tag[:80]))
        for attr in URL_ATTRS:
            if attr not in attrs:
                continue
            raw = _address(html.unescape(attrs[attr]))
            values = ([t.rstrip(",") for t in raw.split() if not re.fullmatch(r"\d+(?:\.\d+)?[wx],?", t)]
                      if attr.endswith("srcset") else [raw])
            for value in values:
                if value in files:
                    if element in FILE_ROLE and FILE_ROLE[element][0] == attr and not value.endswith(FILE_ROLE[element][1]):
                        out.append("%s loads %s with <%s>, which may load only a %s file" % (name, value, element, FILE_ROLE[element][1]))
                    continue
                if value.startswith("#"):
                    continue
                if value.lower().startswith("data:"):
                    if not (element == "img" and attr in ("src", "srcset") and IMAGE_DATA.match(value)):
                        out.append("%s has a data: URL in %s on <%s>, which the dashboard allows only as a png, jpeg, gif, webp or svg image "
                                   "on <img>: %s" % (name, attr, element, value[:60]))
                    continue
                action = "loads a script" if element == "script" else "links to something" if element == "link" else "loads %s" % attr
                out.append("%s %s that is not a bundle file or a data: URL: %s" % (name, action, value))
        for attr in TEXT_ATTRS:
            out += ["%s has the number %s in its %s attribute; every number must come from a dataset" % (name, found, attr)
                    for found in sorted(set(NUMBER.findall(html.unescape(attrs.get(attr, "")))) - MARKUP_NUMBERS_OK)]
        sources = attrs.get("data-source", "").split()
        if element == "table":
            table_source = sources[0] if sources else ""
        out += ["%s marks data-source %r, which is not a dataset in the manifest" % (name, source) for source in sources if source not in columns]
        fields = [attrs["data-field"]] if "data-field" in attrs else []
        fields += [part.split("=", 1)[0] for part in html.unescape(attrs.get("data-where", "")).split("&") if part]
        fields += [part for part in attrs.get("data-row-key", "").split(",") if part]
        owner = sources[0] if sources else table_source if element == "th" else ""
        for field in fields:
            if not owner:
                out.append("%s marks field %r with no data-source to read it from: %s" % (name, field, tag[:80]))
            elif owner in columns and field not in columns[owner]:
                out.append("%s marks field %r on %s, which has no such column" % (name, field, owner))
    return out


STORE_DOCS = ("dash/meta",) + tuple("files/" + name for name in PAGE_FILES)  # the store documents a bundle carries, no others
LOGO_SLOT = r"(data:image/(?:png|jpeg|gif|webp|svg\+xml)(?:;[\w=.+-]+)*,[A-Za-z0-9+/=%._~-]*)"  # a lockup image as the bundle writes it


def _shipped_problem(name: str, data: bytes) -> Optional[str]:
    """Whether a page file differs from this package's own, reviewed one, read as bytes so a rewritten line ending counts. index.html may
    differ only in its lockup slots, each an image data: URL; the other page files must be the shipped bytes exactly."""
    shipped = (PAGE / name).read_bytes()
    if name == "index.html":
        parts = LOGO.split(shipped.decode("utf-8"))
        pattern = "".join(re.escape(part) if n % 2 == 0 else LOGO_SLOT for n, part in enumerate(parts))
        same = re.fullmatch(pattern, data.decode("utf-8")) is not None
    else:
        same = data == shipped
    return None if same else ("page file %s differs from the package's shipped, reviewed %s: the dashboard runs only the package's own page "
                              "code, so build the bundle again with --claude-dashboard" % (name, name))


def check_bundle(directory: str) -> List[str]:
    """Problems with a bundle, [] when none: manifest, dataset files, page files, marks and the store documents. The page files must be
    exactly the package's own, reviewed ones (index.html with only its lockup images filled in), so the page runs the package's code on
    the bundle's data; the markup, style and script checks below run as well, as a second line. It is not a sandbox for other code."""
    root = Path(directory)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ["manifest.json cannot be read: %s" % error]
    problems: List[str] = []
    if not isinstance(manifest, dict) or not isinstance(manifest.get("title"), str) or not manifest.get("title"):
        problems.append("manifest has no title")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("datasets"), list) or not isinstance(manifest.get("files"), list):
        return problems + ["manifest needs a datasets list and a files list"]
    schema = load_schema()
    columns: Dict[str, set] = {}
    listed = [e.get("id") for e in manifest["datasets"] if isinstance(e, dict)]
    problems += ["manifest has no dataset %s, which the schema defines" % d for d in schema["$defs"] if d not in listed]
    problems += ["manifest lists dataset %r, which the schema does not define" % d for d in listed if d not in schema["$defs"]]
    problems += ["manifest files lack %s, a file every bundle carries" % f for f in PAGE_FILES if f not in manifest["files"]]
    for entry in manifest["datasets"]:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry.get(k) for k in ("id", "title", "description", "file", "format")):
            problems.append("a dataset entry lacks id, title, description, file or format: %r" % (entry,))
            continue
        dataset_id = entry["id"]
        if not ID_PATTERN.match(dataset_id):
            problems.append("dataset id %r is not lowercase letters, digits and hyphens" % dataset_id)
        if not 2 <= len(entry["title"].split()) <= 5:
            problems.append("dataset %s title %r is not two to five words" % (dataset_id, entry["title"]))
        path = root / entry["file"]
        if entry["file"] != "datasets/%s.json" % dataset_id or not path.is_file():
            problems.append("dataset %s file %s is missing or misnamed" % (dataset_id, entry["file"]))
            continue
        if path.stat().st_size > DATASET_MAX:
            problems.append("dataset %s is %d bytes, over the 8 MB limit" % (dataset_id, path.stat().st_size))
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append("dataset %s does not parse: %s" % (dataset_id, error))
            continue
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            problems.append("dataset %s is not an array of row objects" % dataset_id)
            continue
        problems += validate_rows(dataset_id, rows, schema)
        columns[dataset_id] = set(schema_columns(schema, dataset_id)) if dataset_id in schema["$defs"] else {key for row in rows for key in row}
        if dataset_id == "header" and not any(r.get("fact") == SCHEMA_FACT and r.get("value") == str(schema["x-version"]) for r in rows):
            built = next((r.get("value") for r in rows if r.get("fact") == SCHEMA_FACT), None)
            problems.append("this bundle was built with schema version %s and this report.py reads version %s: build the bundle again with "
                            "--claude-dashboard" % (built, schema["x-version"]) if built else
                            "dataset header does not carry %s %s" % (SCHEMA_FACT.lower(), schema["x-version"]))
    local = [f for f in manifest["files"] if isinstance(f, str) and LOCAL_FILE.match(f)]
    problems += ["manifest files entry %r is not a bare file name like dashboard.js" % (f,) for f in manifest["files"] if f not in local]
    problems += ["manifest files list %s, which is not one of the package's page files (%s)" % (f, ", ".join(PAGE_FILES))
                 for f in local if f not in PAGE_FILES]
    problems += ["manifest files list %s more than once" % f for f in PAGE_FILES if manifest["files"].count(f) > 1]
    for name in local:
        path = root / "files" / str(name)
        if not path.is_file():
            problems.append("page file %s is missing" % name)
            continue
        if path.stat().st_size > DOC_MAX:
            problems.append("page file %s is %d bytes, over the 256 KB limit" % (name, path.stat().st_size))
        try:
            data = path.read_bytes()
            text = data.decode("utf-8")
        except (OSError, ValueError) as error:
            problems.append("page file %s cannot be read as UTF-8 text: %s" % (name, error))
            continue
        shipped = _shipped_problem(name, data) if name in PAGE_FILES else None
        if shipped:
            problems.append(shipped)
        if name.endswith(".js"):
            problems += _script_problems(name, text)
        elif name.endswith(".css"):
            problems += _style_problems(name, text)
        elif name.endswith(".html"):
            parts = _html_parts(text)
            for _, body, element, _ in (p for p in parts if p[0] == "raw"):
                problems += (_script_problems if element == "script" else _style_problems)(name, body)
                if element == "script" and re.search(r"<!--|<script", body, re.I):
                    problems.append("%s has <!-- or <script inside a script, where a browser may read past its first </script>" % name)
            problems += _mark_problems(name, text, local, columns)
            words = " ".join(body for kind, body, _, _ in parts if kind == "text")
            for found in sorted(set(NUMBER.findall(words)) - MARKUP_NUMBERS_OK):
                problems.append("%s has the number %s in its markup; every number must come from a dataset" % (name, found))
    store = manifest.get("store") or []
    if not isinstance(store, list):
        problems.append("manifest store is not a list of documents: %r" % (store,))
        store = []
    docs = [str(doc.get("doc", "")) for doc in store if isinstance(doc, dict)]
    problems += ["manifest store lacks %s, a document every bundle carries" % d for d in STORE_DOCS if d not in docs]
    problems += ["manifest store lists %s more than once" % d for d in STORE_DOCS if docs.count(d) > 1]
    for sub, listed in (("files", set(local)), ("store", {_store_name(d) for d in STORE_DOCS})):
        problems += ["%s/%s is in the bundle but not in its manifest; the bundle carries no other file there" % (sub, extra.relative_to(root / sub))
                     for extra in sorted((root / sub).rglob("*")) if extra.relative_to(root / sub).as_posix() not in listed]
    for doc in store:
        if not isinstance(doc, dict):
            problems.append("a store entry is not an object: %r" % (doc,))
            continue
        name = str(doc.get("doc", ""))
        if name not in STORE_DOCS:
            problems.append("store document %r is not one this package writes (%s)" % (name, ", ".join(STORE_DOCS)))
            continue
        if doc.get("file") != "store/" + _store_name(name):
            problems.append("store document %s names the file %r, which must be %s" % (name, doc.get("file"), "store/" + _store_name(name)))
            continue
        path = root / "store" / _store_name(name)
        if not path.is_file():
            problems.append("store document %s is missing" % name)
            continue
        if path.stat().st_size > DOC_MAX:
            problems.append("store document %s is %d bytes, over the 256 KB limit" % (name, path.stat().st_size))
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append("store document %s does not parse: %s" % (name, error))
            continue
        if not isinstance(body, dict) or set(body) != ({"text"} if name.startswith("files/") else {"title"}):
            problems.append("store document %s is not an object holding only its %s" % (name, "text" if name.startswith("files/") else "title"))
        elif name.startswith("files/"):
            source = root / "files" / name[len("files/"):]
            try:
                same = source.is_file() and body.get("text") == source.read_bytes().decode("utf-8")
            except (OSError, ValueError):
                same = False
            if not same:
                problems.append("store document %s does not match %s" % (name, source.relative_to(root)))
        elif name == "dash/meta" and body.get("title") != manifest.get("title"):
            problems.append("store document dash/meta does not carry the manifest title")
    return problems
