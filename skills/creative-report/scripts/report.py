#!/usr/bin/env python3
"""Turn the analyse skills' outputs into one self-contained HTML report.

Usage:
  python3 report.py --grade grade.json --verdicts verdicts.json --mix mix.json \\
      [--profile creative-profile.md] [--title "Acme creative review"] -o report.html
  python3 report.py ads.csv -o report.html        # fallback: fewer sections

Standard library only. Produce the three JSON files with `--json` on
creative-grader, keep-or-kill and creative-mix. With only a CSV or JSON of ad
rows, the report grades the ads and reads fatigue and spend itself through the
shared metrics module, and says which sections need the other skills' output.
The page has inline CSS and SVG, no required JavaScript, and its only external
request is the font stylesheet. Every grade is relative to the account's own
ads, never a benchmark.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import creative_metrics as cm

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "report-template.html"
MISSING = re.compile(r"n/a \(missing [^)]*\)")
GRADED = ("cpm", "hook_rate", "hold_rate", "ctr", "cvr", "add_to_cart_rate", "cpa", "roas")
# The funnel is read in this order and the first bottom-quartile step is the diagnosis.
STEPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("reach cost", ("cpm",)), ("hook", ("hook_rate",)), ("hold", ("hold_rate",)),
    ("click", ("ctr",)), ("post-click", ("cvr", "add_to_cart_rate")), ("pays back", ("cpa", "roas")),
)
VERDICT_ORDER = ("iterate", "kill", "scale", "check", "keep", "early")
VERDICT_LABEL = {"iterate": "Iterate", "kill": "Kill", "scale": "Scale", "check": "Check before cutting",
                 "keep": "Keep", "early": "Too early to judge"}
FATIGUE_WINDOW = 6  # arbitrary default, as in keep-or-kill: set it from your own account
TOP_N = 3  # arbitrary default, as in keep-or-kill: how many top-spend ads the concentration line counts
MAX_ACTIONS = 3
MAX_GAPS_MARKED = 8  # arbitrary default, the same number creative-mix lists: how many of the strongest gaps the grid marks


# Display labels for metric ids (ids stay lowercase in JSON). Same ids as creative-context/references/metrics.md.
LABELS = {"hook_rate": "Hook rate", "hold_rate": "Hold rate", "video_completion_rate": "Video completion rate",
          "ctr": "CTR", "cvr": "CVR", "cpm": "CPM", "cpc": "CPC", "cpa": "CPA", "roas": "ROAS", "mer": "MER",
          "add_to_cart_rate": "Add-to-cart rate", "cost_per_add_to_cart": "Cost per add to cart"}
_LABEL_RE = re.compile(r"\b(%s)\b" % "|".join(sorted(LABELS, key=len, reverse=True)))
COST_METRICS = ("cpm", "cpc", "cpa", "cost_per_add_to_cart")
CURRENCY = None  # set per build: the account currency code, or None when the export does not say


def label(metric: str) -> str:
    return LABELS.get(metric, metric)


def money(text: str) -> str:
    """A column title for a currency value: 'Spend (USD)', or 'Spend (account currency)'."""
    return "%s (%s)" % (text, CURRENCY or "account currency")


def say(text: Any) -> str:
    """Escape display text and show metric ids by their labels, keeping a sentence start capital."""
    shown = _LABEL_RE.sub(lambda m: LABELS[m.group(1)], "" if text is None else str(text))
    return html.escape(shown, quote=True)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def verdict_class(verdict: str) -> str:
    text = (verdict or "").lower()
    if text.startswith("scale"):
        return "scale"
    if text.startswith("keep: check"):
        return "check"
    if text.startswith("keep"):
        return "keep"
    if text.startswith("iterate"):
        return "iterate"
    if text.startswith("kill"):
        return "kill"
    return "early"


def short_name(entry: Dict[str, Any]) -> str:
    name = entry.get("name") or entry.get("ad_name") or ""
    first = str(name).split("|")[0].strip()
    return first or str(entry.get("ad") or "unnamed ad")


def ad_cell(entry: Dict[str, Any], facts: Optional[str] = None) -> str:
    full = entry.get("name") or entry.get("ad_name") or ""
    extra = "<small>%s</small>" % esc(facts) if facts else ""
    return '<td class="adname" title="%s">%s<small>%s</small>%s</td>' % (esc(full), esc(short_name(entry)), esc(entry.get("ad")), extra)


def _num(value: Any, digits: int = 0) -> str:
    return "n/a" if value is None else "{:,.{d}f}".format(value, d=digits)


# ---------- charts ----------

def bar_chart(items: Sequence[Tuple[str, float, str, str]], label: str, unit: str, width: int = 420) -> str:
    """Horizontal bars: (name, value, css class, value text). Every bar carries its label and value."""
    if not items:
        return ""
    left, right, row = 150, 50, 28
    top = max(v for _, v, _, _ in items) or 1
    height = row * len(items) + 34
    parts = ['<figure class="chart"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for i, (name, value, css, text) in enumerate(items):
        y = i * row + 6
        length = max((width - left - right) * value / top, 2)
        shown = name if len(name) <= 22 else name[:21] + "..."
        parts.append('<text class="lbl" x="%d" y="%d" text-anchor="end">%s</text>' % (left - 9, y + 16, esc(shown)))
        parts.append('<rect class="bar %s" x="%d" y="%d" width="%.1f" height="20" rx="6"><title>%s: %s</title></rect>'
                     % (esc(css), left, y, length, esc(name), esc(text)))
        parts.append('<text x="%.1f" y="%d">%s</text>' % (left + length + 8, y + 15, esc(text)))
    parts.append('<line class="axis" x1="%d" y1="2" x2="%d" y2="%d"/>' % (left, left, height - 28))
    parts.append('<text x="%d" y="%d">%s</text>' % (left, height - 8, esc(unit)))
    parts.append("</svg><figcaption>%s</figcaption></figure>" % esc(label))
    return "".join(parts)


def _ticks(low: float, high: float, count: int = 4) -> List[float]:
    return [low + (high - low) * i / count for i in range(count + 1)]


def scatter(points: Sequence[Tuple[float, float, str]], xlabel: str, ylabel: str, label: str) -> str:
    """Dots with labelled axes and dashed medians of the plotted ads."""
    if len(points) < 2:
        return ""
    width, height, left, bottom, top, right = 480, 340, 50, 46, 14, 14
    xs, ys = [p[0] for p in points], [p[1] for p in points]

    def span(values):
        low, high = min(values), max(values)
        pad = (high - low) * 0.08 or 1.0
        return low - pad, high + pad

    (x0, x1), (y0, y1) = span(xs), span(ys)

    def px(x):
        return left + (x - x0) / (x1 - x0) * (width - left - right)

    def py(y):
        return height - bottom - (y - y0) / (y1 - y0) * (height - bottom - top)

    def median(values):
        ordered = sorted(values)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    parts = ['<figure class="chart"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - bottom))
    for value in _ticks(x0, x1):
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%.1f</text>' % (px(value), height - bottom + 16, value))
    for value in _ticks(y0, y1):
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%.1f</text>' % (left - 8, py(value) + 4, value))
    mx, my = median(xs), median(ys)
    parts.append('<line class="guide" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (px(mx), top, px(mx), height - bottom))
    parts.append('<line class="guide" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, py(my), width - right, py(my)))
    for x, y, name in points:
        parts.append('<circle class="dot" cx="%.1f" cy="%.1f" r="6"><title>%s: %s %.1f, %s %.1f</title></circle>'
                     % (px(x), py(y), esc(name), esc(xlabel), x, esc(ylabel), y))
    parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % ((left + width - right) / 2, height - 6, esc(xlabel)))
    parts.append('<text transform="rotate(-90 14 %.1f)" x="14" y="%.1f" text-anchor="middle">%s</text>'
                 % ((top + height - bottom) / 2, (top + height - bottom) / 2, esc(ylabel)))
    parts.append("</svg><figcaption>%s. Dashed lines mark the median of the plotted ads.</figcaption></figure>" % esc(label))
    return "".join(parts)


# ---------- grading from rows (fallback) ----------

def grade_from_rows(rows: Sequence[Dict[str, Any]], group_by: Sequence[str] = ("format",),
                    min_impressions: int = 1000) -> Dict[str, Any]:
    """The creative-grader result shape, built from rows with the shared metrics module only."""
    ads = cm.aggregate_by_ad(rows)
    entries = []
    for ad in ads:
        graded = (ad.get("impressions") or 0) >= min_impressions
        grades = {}
        for metric in GRADED:
            grade = cm.grade_against(ad, ads, metric, group_by=group_by, min_impressions=min_impressions)
            grade["display"] = cm.format_value(ad, metric)
            grades[metric] = grade
        skipped = ["%s %s" % (m, g["band"]) for m, g in grades.items()
                   if graded and g["band"].startswith("not graded")]
        diagnosis: Dict[str, Any] = {"step": "none", "metrics": [], "also_weak": [], "action": None,
                                     "summary": "no broken step", "skipped": skipped}
        if not graded:
            diagnosis.update(step="not graded", summary="not graded (low volume)", skipped=[])
        else:
            broken = [(s, [m for m in ms if grades[m]["band"] == cm.BAND_BOTTOM]) for s, ms in STEPS]
            broken = [(s, ms) for s, ms in broken if ms]
            if broken:
                step, metrics = broken[0]
                diagnosis.update(step=step, metrics=metrics, summary="%s (%s bottom quartile)" % (step, ", ".join(metrics)),
                                 also_weak=[m for _, later in broken[1:] for m in later])
        entries.append({"ad": ad.get("ad_id") or ad.get("ad_name"), "name": ad.get("ad_name"),
                        "format": ad.get("format"), "group": cm.group_key(ad, group_by), "graded": graded,
                        "impressions": ad.get("impressions"), "grades": grades, "diagnosis": diagnosis,
                        "spend": ad.get("spend")})
    start, end = cm.data_window(rows)
    sources = sorted({ad.get("conversions_source") for ad in ads if ad.get("conversions_source")})
    basis = "\n".join([
        "Graded against this account's own ads, never a benchmark.",
        "Window: %s to %s" % (start or "n/a (no dates)", end or "n/a (no dates)"),
        "Grouped by: %s. Bands: top quartile is at or above p75, bottom at or below p25 (costs inverted)." % ", ".join(group_by),
        "Ads under %d impressions are not graded (arbitrary default: set it from your own spend per ad)." % min_impressions,
        "Conversions column: %s." % (", ".join(sources) or "n/a (no conversions column)"),
    ])
    return {"basis": basis, "ads": entries, "source": "rows"}


def fatigue_rows(rows: Sequence[Dict[str, Any]], window: int = FATIGUE_WINDOW) -> List[Dict[str, Any]]:
    out = []
    for ad in cm.aggregate_by_ad(rows):
        key = ad.get("ad_id") or ad.get("ad_name")
        trend = cm.fatigue_trend(rows, key, "ctr", window)
        out.append({"ad": key, "name": ad.get("ad_name"), "format": ad.get("format"), "trend": trend})
    return out


# ---------- sections ----------

def section(eyebrow: str, heading: str, inner: str) -> str:
    return '<section class="card"><p class="eyebrow">%s</p><h2>%s</h2>%s</section>' % (esc(eyebrow), esc(heading), inner)


def table(header: Sequence[Tuple[str, bool]], body: Sequence[str], stack: bool = False) -> str:
    """A scrolling table; `stack` turns each row into a card on a narrow screen."""
    head = "".join('<th%s>%s</th>' % (' class="num"' if num else "", esc(text)) for text, num in header)
    return '<div class="scroll"><table%s><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        ' class="stack"' if stack else "", head, "".join(body))


def verdict_counts(verdicts: Optional[Dict[str, Any]]) -> Counter:
    return Counter(verdict_class(a["verdict"]) for a in (verdicts or {}).get("ads", []))


def top_actions(verdicts: Optional[Dict[str, Any]], grade: Optional[Dict[str, Any]]) -> List[str]:
    """Up to three actions: one per decision type first, largest spend first, then the next largest."""
    items: List[str] = []
    if verdicts and verdicts.get("ads"):
        by_class: Dict[str, List[Dict[str, Any]]] = {}
        for ad in sorted(verdicts["ads"], key=lambda a: -(a.get("spend") or 0)):
            by_class.setdefault(verdict_class(ad["verdict"]), []).append(ad)
        queue = [ad for cls in ("iterate", "kill", "scale") for ad in by_class.get(cls, [])]
        firsts = [by_class[c][0] for c in ("iterate", "kill", "scale") if by_class.get(c)]
        ordered = firsts + [ad for ad in queue if ad not in firsts]
        for ad in ordered[:MAX_ACTIONS]:
            reason = ad["reasons"][0].rstrip(".") + "." if ad.get("reasons") else ""
            check = " Before cutting: %s." % ad["check"].rstrip(".") if ad.get("check") else ""
            items.append("<strong>%s</strong>: %s. %s%s" % (esc(short_name(ad)), say(ad["verdict"]), say(reason), say(check)))
    elif grade and grade.get("ads"):
        steps = Counter(a["diagnosis"]["step"] for a in grade["ads"] if a["diagnosis"]["step"] not in ("none", "not graded"))
        for step, count in steps.most_common(MAX_ACTIONS):
            action = next((a["diagnosis"].get("action") for a in grade["ads"] if a["diagnosis"]["step"] == step), None)
            tail = (" " + action) if action else " Run creative-grader for the action to take."
            items.append("<strong>%d ad%s break first at %s.</strong>%s" % (count, "" if count == 1 else "s", esc(step), say(tail)))
    return items


def headline(verdicts, grade) -> str:
    counts = verdict_counts(verdicts)
    lead = ""
    if counts:
        tiles = "".join('<div class="stat"><b>%d</b><span>%s</span></div>' % (counts[c], esc(VERDICT_LABEL[c]))
                        for c in VERDICT_ORDER if counts.get(c))
        total = sum(counts.values())
        lead = '<p class="lead">%d ads read. Here is what to do with them.</p><div class="stats">%s</div>' % (total, tiles)
    elif grade and grade.get("ads"):
        steps = Counter(a["diagnosis"]["step"] for a in grade["ads"])
        tiles = "".join('<div class="stat"><b>%d</b><span>%s</span></div>' % (n, esc(s)) for s, n in steps.most_common(6))
        lead = ('<p class="lead">%d ads graded. Verdicts need the keep-or-kill output, so this page shows the '
                'first broken funnel step instead.</p><div class="stats">%s</div>' % (len(grade["ads"]), tiles))
    else:
        lead = '<p class="lead">No ad data was provided, so there is nothing to grade yet.</p>'
    actions = top_actions(verdicts, grade)
    listing = '<h3>Do these first</h3><ol class="actions">%s</ol>' % "".join("<li>%s</li>" % a for a in actions) if actions else ""
    return section("The answer", "What to do first", lead + listing)


def basis_section(grade, verdicts, mix, brand: Optional[str]) -> str:
    lines = ["Graded against this account's own baseline, not industry benchmarks."]
    if brand:
        lines.append("Account: %s." % brand.rstrip("."))
    if grade:
        lines += [l for l in str(grade.get("basis", "")).splitlines() if l.strip()]
    if verdicts:
        s = verdicts.get("settings") or {}
        lines.append("Verdict settings used (arbitrary defaults, set them from your own account): "
                     "young-days=%s, window=%s, min-impressions=%s, min-change=%s%%, top-n=%s, grouped by %s."
                     % (s.get("young_days", "n/a"), s.get("window", "n/a"), s.get("min_impressions", "n/a"),
                        s.get("min_change", "n/a"), s.get("top_n", "n/a"), s.get("group_by", "n/a")))
    if mix:
        window = mix.get("window") or []
        lines.append("Mix: window %s; %s ads classified by name, %s unclassified; spend shares are of classified spend."
                     % (" to ".join(str(w) for w in window) or "n/a", mix.get("classified", "n/a"),
                        (mix.get("unclassified") or {}).get("count", "n/a")))
    lines.append("Metric ids and formulas are defined in creative-context/references/metrics.md. Money is shown in %s." % (CURRENCY or "the account's own currency (the export did not name one)"))
    return section("How it was read", "Basis", '<div class="basis"><pre>%s</pre></div>' % esc("\n".join(lines)))


def verdict_section(verdicts, rows) -> str:
    if verdicts and verdicts.get("ads"):
        counts = verdict_counts(verdicts)
        chart = bar_chart([(VERDICT_LABEL[c], counts[c], c, str(counts[c])) for c in VERDICT_ORDER if counts.get(c)],
                          "Ads per verdict", "Number of ads")
        body = []
        ads = sorted(verdicts["ads"], key=lambda a: (VERDICT_ORDER.index(verdict_class(a["verdict"])), -(a.get("spend") or 0)))
        for ad in ads:
            cls = verdict_class(ad["verdict"])
            reasons = "".join("<li>%s</li>" % say(r) for r in ad.get("reasons", []))
            check = "<p class=\"muted\"><strong>Check first:</strong> %s</p>" % say(ad["check"]) if ad.get("check") else ""
            head, _, rest = ad["verdict"].partition(": ")
            if head == "kill":
                head, rest = ad["verdict"], ""
            detail = "<small>%s</small>" % say(rest) if rest else ""
            facts = "%s, %s days old" % (ad.get("format") or "no format", _num(ad.get("age_days")))
            body.append("<tr>%s<td class=\"num\" data-label=\"%s\">%s</td><td><span class=\"badge %s\">%s</span>%s</td>"
                        "<td class=\"why\"><ul class=\"reasons\">%s</ul>%s</td></tr>"
                        % (ad_cell({"ad": ad.get("ad"), "name": ad.get("ad_name")}, facts), money("Spend"), _num(ad.get("spend")),
                           cls, say(head), detail, reasons, check))
        grid = table([("Ad", False), (money("Spend"), True), ("Verdict", False), ("Why", False)], body, stack=True)
        concentration = (verdicts.get("summary") or {}).get("concentration_line")
        note = '<p class="muted">%s</p>' % esc(concentration) if concentration else ""
        return section("Verdicts", "Keep, kill, iterate, scale", chart + grid + note)
    msg = ('<p>Keep, kill, iterate or scale calls need the keep-or-kill output: run keep-or-kill with <code>--json</code> '
           'and pass the file with <code>--verdicts</code>.</p>')
    if not rows:
        return section("Verdicts", "Keep, kill, iterate, scale", msg)
    body = []
    for entry in fatigue_rows(rows):
        t = entry["trend"]
        if t["status"] == "ok":
            cells = "<td class=\"num\">%+.0f%%</td><td class=\"num\">%s</td><td>read</td>" % (
                t["pct_change"] if t["pct_change"] is not None else 0,
                "n/a" if t["frequency_pct_change"] is None else "%+.0f%%" % t["frequency_pct_change"])
            if t["pct_change"] is None:
                cells = "<td class=\"num\">n/a</td><td class=\"num\">n/a</td><td>read</td>"
        else:
            cells = "<td class=\"num\">n/a</td><td class=\"num\">n/a</td><td>needs %d delivery days, has %d</td>" % (
                t["needed"], t["delivery_days"])
        body.append("<tr>%s<td>%s</td>%s</tr>" % (ad_cell(entry), esc(entry["format"] or "-"), cells))
    grid = table([("Ad", False), ("Format", False), (label("ctr") + " change", True), ("Frequency change", True), ("Fatigue read", False)], body)
    note = ('<p class="muted">ctr and frequency compare each ad\'s first and last %d delivery days (an arbitrary '
            'default: set it from your own account). A move is not a verdict by itself.</p>' % FATIGUE_WINDOW)
    return section("Verdicts", "Keep, kill, iterate, scale", msg + "<h3>Fatigue read in the meantime</h3>" + grid + note)


def _cell(grade: Dict[str, Any]) -> str:
    value, band = grade.get("value"), grade.get("band") or ""
    if value is None:
        return '<td class="num" title="%s">n/a</td>' % esc(grade.get("display") or band)
    tag = ""
    if band == cm.BAND_BOTTOM:
        tag = '<span class="band low">low</span>'
    elif band == cm.BAND_TOP:
        tag = '<span class="band top">top</span>'
    elif band.startswith("not graded"):
        tag = '<span class="band">not graded</span>'
    return '<td class="num">%.2f%s</td>' % (value, tag)


def funnel_section(grade, rows) -> str:
    if not grade or not grade.get("ads"):
        return section("Funnel", "Funnel diagnosis", "<p>No graded ads. Pass the creative-grader output with <code>--grade</code>.</p>")
    ads = grade["ads"]
    order = [s for s, _ in STEPS] + ["none", "not graded"]
    counts = Counter(a["diagnosis"]["step"] for a in ads)
    chart = bar_chart([(s if s != "none" else "no broken step", counts[s], "keep" if s == "none" else "iterate", str(counts[s]))
                       for s in order if counts.get(s)], "Ads by first broken funnel step", "Number of ads")
    points = [(a["grades"]["hook_rate"]["value"], a["grades"]["hold_rate"]["value"], short_name(a)) for a in ads
              if a["grades"].get("hook_rate", {}).get("value") is not None and a["grades"].get("hold_rate", {}).get("value") is not None]
    plot = scatter(points, "Hook rate (%)", "Hold rate (%)", "Hook rate against hold rate, one dot per video ad")
    body = []
    for a in sorted(ads, key=lambda a: order.index(a["diagnosis"]["step"]) if a["diagnosis"]["step"] in order else 99):
        d = a["diagnosis"]
        action = d.get("action") or "Run creative-grader for the action to take."
        extra = " Also weak: %s." % ", ".join(d["also_weak"]) if d.get("also_weak") else ""
        body.append("<tr>%s<td>%s</td>%s<td><strong>%s</strong><small>%s%s</small></td></tr>" % (
            ad_cell(a), esc(a.get("format") or "-"), "".join(_cell(a["grades"][m]) for m in ("hook_rate", "hold_rate", "ctr", "cpm", "cpa", "roas")),
            say(d["summary"]), say(action), say(extra)))
    grid = table([("Ad", False), ("Format", False), (label("hook_rate") + " (%)", True), (label("hold_rate") + " (%)", True),
                  (label("ctr") + " (%)", True), (money(label("cpm")), True), (money(label("cpa")), True),
                  (label("roas") + " (x)", True), ("First broken step", False)], body)
    note = ('<p class="muted">Read the funnel in order and fix the first broken step. "low" is the bottom quartile and '
            '"top" the top quartile of this account\'s own ads in the same group; costs are inverted. n/a means a missing or '
            'zero operand and is never read as 0.</p>')
    return section("Funnel", "Funnel diagnosis", chart + plot + grid + note)


def mix_section(mix, rows) -> str:
    if mix:
        fmt = mix.get("by_format") or []
        chart = bar_chart([(f["format"], f["share"] or 0, "keep", "%.0f%%" % (f["share"] or 0)) for f in fmt],
                          "Share of spend by format", "Share of classified spend (%)")
        types = mix.get("by_type") or []
        type_chart = bar_chart([(t["ad_type"], t["share"] or 0, "check", "%.0f%%" % (t["share"] or 0)) for t in types],
                               "Share of spend by ad type", "Share of classified spend (%)")
        grid_data = mix.get("grid") or {}
        gaps = {(g["concept"], g["format"]) for g in mix.get("gaps", [])[:MAX_GAPS_MARKED]}
        header = [("Concept", False)] + [(f, False) for f in grid_data.get("formats", [])]
        body = []
        for family, cells in zip(grid_data.get("families", []), grid_data.get("cells", [])):
            tds = []
            for f in grid_data.get("formats", []):
                n = (cells.get(f) or {}).get("ads", 0)
                if n:
                    tds.append('<td class="grid-cell full">%d</td>' % n)
                elif (family, f) in gaps:
                    tds.append('<td class="grid-cell empty" title="a gap worth testing">gap</td>')
                else:
                    tds.append('<td class="grid-cell">-</td>')
            body.append("<tr><td>%s</td>%s</tr>" % (esc(family), "".join(tds)))
        grid = table(header, body) if body else ""
        grid_note = ('<p class="muted">Cells count ads. "gap" marks the %d strongest gaps creative-mix found: a top-quartile concept with no ad in a top-quartile format. '
                     'A gap is a place with no evidence yet, so treat it as a hypothesis worth testing.</p>' % MAX_GAPS_MARKED)
        findings = ""
        over = mix.get("over_reliance") or []
        if over:
            findings += "<h3>Over-reliance</h3><ul class=\"note-list\">%s</ul>" % "".join(
                "<li>%s %s holds %.0f%% of %s</li>" % (esc(o.get("kind")), esc(o.get("name")), o.get("share") or 0, esc(o.get("scope"))) for o in over)
        dups = mix.get("duplicates") or []
        if dups:
            findings += "<h3>Near-duplicates counted as one concept</h3><ul class=\"note-list\">%s</ul>" % "".join(
                "<li>%s: %s</li>" % (esc(d["concept"]), esc(", ".join(d["variants"]))) for d in dups)
        un = (mix.get("unclassified") or {}).get("count")
        un_note = ('<p class="muted">%s ads did not match the naming convention and are counted, never dropped.</p>' % esc(un)
                   if un else "")
        return section("Portfolio", "Creative mix", '<div class="cols two">%s%s</div>%s%s%s%s' % (chart, type_chart, grid, grid_note, findings, un_note))
    msg = ('<p>The concept by format grid, gaps and ad-type split need the creative-mix output: run creative-mix with '
           '<code>--json</code> and pass the file with <code>--mix</code>.</p>')
    if not rows:
        return section("Portfolio", "Creative mix", msg)
    ads = cm.aggregate_by_ad(rows)
    total = sum(a.get("spend") or 0 for a in ads)
    by_format: Dict[str, float] = {}
    for a in ads:
        by_format[a.get("format") or "unknown"] = by_format.get(a.get("format") or "unknown", 0) + (a.get("spend") or 0)
    items = [(k, v / total * 100, "keep", "%.0f%%" % (v / total * 100)) for k, v in sorted(by_format.items(), key=lambda kv: -kv[1])] if total else []
    chart = bar_chart(items, "Share of spend by format", "Share of spend (%)")
    share = cm.concentration(ads, top_n=TOP_N)
    line = ("<p class=\"muted\">Top %d ads (an arbitrary default: set your own) hold %s of spend.</p>"
            % (TOP_N, "n/a (no spend)" if share is None else "%.0f%%" % share))
    return section("Portfolio", "Creative mix", msg + chart + line)


def collect_notes(grade, verdicts, mix, rows_mode: bool) -> List[str]:
    notes: List[str] = []
    seen: Counter = Counter()
    for source in (grade, verdicts, mix):
        if not source:
            continue
        entries = source.get("ads") or []
        for entry in entries:
            for note in set(MISSING.findall(json.dumps(entry))):
                seen[note] += 1
        for note in set(MISSING.findall(json.dumps({k: v for k, v in source.items() if k != "ads"}))):
            seen.setdefault(note, 0)
    for note, count in sorted(seen.items()):
        where = "%d ad%s" % (count, "" if count == 1 else "s") if count else "the summary"
        notes.append("<code>%s</code> in %s. The metrics that need it are skipped, never counted as 0." % (esc(note), esc(where)))
    if grade:
        low = sum(1 for a in grade.get("ads", []) if a["diagnosis"]["step"] == "not graded")
        if low:
            notes.append("%d ad%s not graded for low volume." % (low, "" if low == 1 else "s"))
        skipped = sum(1 for a in grade.get("ads", []) if a["diagnosis"].get("skipped"))
        if skipped:
            notes.append("%d ad%s had a funnel step skipped for missing data; a skipped step is never read as healthy." % (skipped, "" if skipped == 1 else "s"))
    if verdicts:
        young = (verdicts.get("summary") or {}).get("too_young") or []
        if young:
            notes.append("%d ad%s too young to judge." % (len(young), "" if len(young) == 1 else "s"))
        blind = [a for a in verdicts.get("ads", []) if (a.get("fatigue") or {}).get("status") == "insufficient data"]
        if blind:
            notes.append("Fatigue could not be read for %d ad%s (fewer than two windows of delivery days); those are held, not scaled." % (len(blind), "" if len(blind) == 1 else "s"))
    if mix and (mix.get("unclassified") or {}).get("count"):
        notes.append("%s ads did not match the naming convention, so the mix describes only part of the account." % esc(mix["unclassified"]["count"]))
    missing_sources = [name for name, src in (("keep-or-kill (verdicts)", verdicts), ("creative-mix (grid, gaps, ad types)", mix),
                                              ("creative-grader (full diagnoses and actions)", grade if not grade or grade.get("source") != "rows" else None)) if not src]
    if grade and grade.get("source") == "rows":
        missing_sources.append("creative-grader (actions for each step)")
    for name in missing_sources:
        notes.append("Section content from %s is not in this report: run it with <code>--json</code> and pass the file." % esc(name))
    return notes


def notes_section(notes: Sequence[str]) -> str:
    inner = ('<ul class="note-list">%s</ul>' % "".join("<li>%s</li>" % n for n in notes)) if notes else "<p>Nothing was missing from the inputs.</p>"
    return section("Caveats", "Notes and missing data", inner)


def brand_from_profile(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"^- Name:\s*(.+)$", text, re.M) or re.search(r"^#\s*Creative profile:\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else None


def build_html(rows: Optional[Sequence[Dict[str, Any]]] = None, grade: Optional[Dict[str, Any]] = None,
               verdicts: Optional[Dict[str, Any]] = None, mix: Optional[Dict[str, Any]] = None,
               profile: Optional[str] = None, title: str = "Creative review",
               generated: Optional[str] = None, currency: Optional[str] = None) -> str:
    """Render the report. `rows` are normalised ad rows (creative_metrics.load_rows)."""
    global CURRENCY
    CURRENCY = currency
    rows_mode = grade is None
    if grade is None and rows:
        grade = grade_from_rows(rows)
    brand = brand_from_profile(profile)
    start_end = re.search(r"Window: (\S+) to (\S+)", (grade or {}).get("basis", ""))
    window = "Window %s to %s. " % start_end.groups() if start_end else ""
    body = "".join([
        headline(verdicts, grade),
        basis_section(grade, verdicts, mix, brand),
        verdict_section(verdicts, rows),
        funnel_section(grade, rows),
        mix_section(mix, rows),
        notes_section(collect_notes(grade, verdicts, mix, rows_mode)),
    ])
    words = title.strip().split()
    heading = (esc(" ".join(words[:-1])) + " " if len(words) > 1 else "") + '<span class="grad">%s</span>' % esc(words[-1] if words else "review")
    text = TEMPLATE.read_text(encoding="utf-8")
    fills = {"title": esc(title), "heading": heading, "eyebrow": esc(brand or "Creative review"),
             "subtitle": esc(window + "Every ad is read against this account's own ads, not industry benchmarks."),
             "generated": esc(generated or dt.date.today().isoformat()), "body": body}
    for key, value in fills.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def detect_currency(path: Optional[str]) -> Optional[str]:
    """The currency code in an export's spend header, e.g. "Amount spent (USD)"; None when it is not stated."""
    if not path or str(path).lower().endswith(".json"):
        return None
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            header = handle.readline()
    except OSError:
        return None
    found = re.search(r"amount spent\s*\(([A-Za-z]{3})\)", header, re.I)
    return found.group(1).upper() if found else None


def _load_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a self-contained HTML creative report.")
    parser.add_argument("data", nargs="?", help="optional Ads Manager CSV (or JSON rows): fallback when the analyse JSON is missing")
    parser.add_argument("--grade", help="creative-grader --json output")
    parser.add_argument("--verdicts", help="keep-or-kill --json output")
    parser.add_argument("--mix", help="creative-mix --json output")
    parser.add_argument("--profile", help="creative-profile.md, used for the account name")
    parser.add_argument("--csv", help="the Ads Manager CSV behind the JSON files, only to read the currency code from its spend header")
    parser.add_argument("--currency", help="three-letter currency code to show; default: read from the export's spend header")
    parser.add_argument("--title", default="Creative review", help="report title; its last word gets the gradient")
    parser.add_argument("-o", "--output", default="report.html", help="where to write the HTML (default report.html)")
    args = parser.parse_args(argv)
    if not any((args.data, args.grade, args.verdicts, args.mix)):
        parser.error("give a CSV of ad rows, or at least one of --grade, --verdicts, --mix")
    rows = cm.load_rows(args.data) if args.data else None
    profile = Path(args.profile).read_text(encoding="utf-8") if args.profile else None
    page = build_html(rows=rows, grade=_load_json(args.grade), verdicts=_load_json(args.verdicts),
                      mix=_load_json(args.mix), profile=profile, title=args.title,
                      currency=args.currency or detect_currency(args.data) or detect_currency(args.csv))
    Path(args.output).write_text(page, encoding="utf-8")
    print("wrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
