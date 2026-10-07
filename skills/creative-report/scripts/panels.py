"""The dashboard's panels: one function each, returning (html, state).

state is "data" when the panel was filled from the inputs and "empty" when it
shows a labelled empty state saying why and how to get the data. A panel is
never dropped and an empty state never looks like an answer. Standard library
only; every string that came from the data is escaped.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import creative_metrics as cm  # noqa: E402
import interact  # noqa: E402
from interact import (BOARD, ID_CLASS, LABEL_WORDS, LABELS, NEXT_STEP, PAUSE_CHECK, VERDICT_LABEL, entry_class,  # noqa: E402,F401
                      readable_label, recognised)
from previews import Previews  # noqa: E402

_first_segment = interact.first_segment

TOP_N_CARDS = 8  # arbitrary default: how many ad cards each list shows before collapsing the rest
CONCENTRATION_N = 3  # arbitrary default, as in keep-or-kill: how many top-spend ads the concentration gauge counts
PARETO_SHARE = 80.0  # the common Pareto convention, not a rule: set it from your own account
LIST_CAP = 60  # arbitrary display cap on a collapsed list, so a 500-ad account stays readable
_LABEL_RE = re.compile(r"\b(%s)\b" % "|".join(sorted(LABELS, key=len, reverse=True)))

KPI_ORDER = (
    ("spend", "Spend", "money0"), ("impressions", "Impressions", "int"), ("reach", "Reach", "int"),
    ("frequency", "Frequency", "x2"), ("ctr", "CTR (link)", "pct"), ("cpm", "CPM", "money2"),
    ("conversions", "Purchases", "int"), ("cpa", "CPA", "money2"), ("conversion_value", "Purchase value", "money0"),
    ("roas", "ROAS", "x2"), ("hook_rate", "Hook rate", "pct"), ("hold_rate", "Hold rate", "pct"),
)
NEEDS_ACCOUNT = "n/a (needs account-level reach)"
FUNNEL_COLUMNS = {
    "landing_page_views": ("landingpageviews", "landingpageview", "omnilandingpageview", "websitelandingpageviews"),
    "checkouts": ("checkoutsinitiated", "initiatedcheckout", "omniinitiatedcheckout", "websitecheckoutsinitiated", "checkouts"),
}
FUNNEL_STEPS = (
    ("Impressions", "impressions"), ("3-second plays", "video_views_3s"), ("ThruPlays", "video_thruplay"),
    ("Link clicks", "link_clicks"), ("Landing page views", "landing_page_views"), ("Adds to cart", "add_to_carts"),
    ("Checkouts", "checkouts"), ("Purchases", "conversions"),
)


def esc(value: Any) -> str:
    return charts.esc(value)


def say(text: Any) -> str:
    """Escape display text and show metric ids by their labels."""
    shown = _LABEL_RE.sub(lambda m: LABELS[m.group(1)], "" if text is None else str(text))
    return esc(interact.plain_ids(shown))


def section(eyebrow: str, heading: str, inner: str) -> str:
    return '<section class="card"><p class="eyebrow">%s</p><h2>%s</h2>%s</section>' % (esc(eyebrow), esc(heading), inner)


def table(header: Sequence[Tuple[str, bool]], body: Sequence[str], stack: bool = False) -> str:
    """A scrolling table; `stack` turns each row into a card on a narrow screen."""
    head = "".join('<th%s>%s</th>' % (' class="num"' if num else "", esc(text)) for text, num in header)
    return '<div class="scroll"><table%s><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        ' class="stack"' if stack else "", head, "".join(body))


def empty_state(why: str, how: str) -> Tuple[str, str]:
    return ('<div class="empty"><p><b>Why this is empty:</b> %s</p><p><b>How to get it:</b> %s</p></div>'
            % (esc(why), esc(how)), "empty")


class Ctx:
    """Everything a panel reads: rows, per-ad aggregates, the analyse outputs and the run settings."""

    def __init__(self, rows: Optional[Sequence[Dict[str, Any]]] = None, verdicts: Optional[Dict[str, Any]] = None,
                 grade: Optional[Dict[str, Any]] = None, mix: Optional[Dict[str, Any]] = None,
                 currency: Optional[str] = None, top_n: int = TOP_N_CARDS, pareto_share: float = PARETO_SHARE,
                 account: Optional[Dict[str, float]] = None, prior: Optional[Sequence[Dict[str, Any]]] = None,
                 previews: Optional[Previews] = None) -> None:
        self.rows = list(rows or [])
        self.ads = cm.aggregate_by_ad(self.rows) if self.rows else []
        self.ad_index = {str(a.get("ad_id") or a.get("ad_name")): a for a in self.ads}
        self.verdicts, self.grade, self.mix = verdicts, grade, mix
        self.currency, self.top_n, self.pareto_share = currency, top_n, pareto_share
        self.account, self.prior = account, list(prior) if prior else None
        self.previews = previews or Previews()
        self.records = interact.ad_records(self.ads, (verdicts or {}).get("ads"), (grade or {}).get("ads"))
        self.record_index = {r["id"]: r for r in self.records}
        self.verdict_index = {str(e.get("ad")): e for e in (verdicts or {}).get("ads") or []}
        self.grade_index = {str(e.get("ad")): e for e in (grade or {}).get("ads") or []}
        self.facets = interact.facets(self.records)
        self.video_lengths = video_lengths(self.rows)
        self.funnel_headers: Dict[str, Optional[str]] = {}
        settings = (verdicts or {}).get("settings") or {}
        self.concentration_n = int(settings.get("top_n") or CONCENTRATION_N)

    def money(self, value: Optional[float], digits: int = 0) -> str:
        if value is None:
            return "n/a"
        text = "{:,.{d}f}".format(value, d=digits)
        return "%s %s" % (self.currency, text) if self.currency else "%s (account currency)" % text


# ---------- ad cards ----------

VIDEO_LENGTH_HEADERS = ("videolength", "videolengthseconds", "videoduration", "videodurationseconds")


def video_lengths(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Seconds of video per ad id, from a length column in the export when there is one."""
    found: Dict[str, float] = {}
    for row in rows:
        key = str(row.get("ad_id") or row.get("ad_name"))
        if key in found:
            continue
        for header, value in row.items():
            if re.sub(r"[^a-z0-9]", "", str(header).lower()) in VIDEO_LENGTH_HEADERS:
                try:
                    found[key] = float(str(value).replace(",", ""))
                except ValueError:
                    pass
    return found


def clock(seconds: float) -> str:
    return "%d:%02d" % divmod(int(round(seconds)), 60)


def _fields_for(ctx: Ctx, entry: Dict[str, Any]) -> Dict[str, Any]:
    base = ctx.ad_index.get(str(entry.get("ad")))
    if base:
        return base
    fields = dict(cm.parse_name(entry.get("ad_name") or entry.get("name")) if (entry.get("ad_name") or entry.get("name")) else {})
    if entry.get("format"):
        fields["format"] = entry["format"]
    return fields


def strip_confidence(sentence: str, confidence: Optional[str]) -> str:
    """The sentence without its trailing confidence clause: the chip already says it."""
    if confidence:
        cut = sentence.find(" %s:" % confidence)
        if cut > 0:
            return sentence[:cut].rstrip()
    return sentence


OPEN_MAX_PX = 460  # the largest an ad's preview is shown in the open view


def _image(ctx: Ctx, ad_id: Any, label: str, fmt: str, big: bool = False) -> str:
    alt = "%s (%s)" % (label, fmt or "format not known")
    found = ctx.previews.resolve(ad_id)
    size = " big" if big else ""
    if found["symbol"]:
        limit = ' style="max-width:%dpx"' % min(int(found["width"]), OPEN_MAX_PX) if big else ""
        return ('<svg class="pv%s" role="img" aria-label="%s" viewBox="0 0 %d %d" width="%d" height="%d"%s><use href="#%s" width="%d" height="%d"/></svg>'
                % (size, esc(alt), found["width"], found["height"], found["width"], found["height"], limit, esc(found["symbol"]), found["width"], found["height"]))
    return ('<svg class="ph%s" viewBox="0 0 300 300" width="300" height="300" role="img" aria-label="%s">'
            '<rect class="ph-bg" x="0" y="0" width="300" height="300" rx="16"/>'
            '<text class="ph-format" x="150" y="140" text-anchor="middle">%s</text>'
            '<text x="150" y="172" text-anchor="middle">preview unavailable:</text>'
            '<text x="150" y="192" text-anchor="middle">%s</text></svg>'
            % (size, esc(alt + ", preview unavailable: " + str(found["reason"])), esc((fmt or "format n/a").upper()), esc(found["reason"])))


PROMPT_CLASSES = ("iterate", "check", "kill")


def entry_for(ctx: Ctx, rec: Dict[str, Any]) -> Dict[str, Any]:
    """The verdict entry for a record, or a bare entry when the ad was not judged."""
    return ctx.verdict_index.get(rec["id"]) or {"ad": rec["id"], "ad_name": rec["name"]}


def _table_of(rows: Sequence[Sequence[str]], header: Sequence[Tuple[str, bool]]) -> str:
    body = ["<tr>%s</tr>" % "".join('<td%s data-label="%s">%s</td>' % (' class="num"' if num else "", esc(head), esc(cell))
                                    for (head, num), cell in zip(header, row)) for row in rows]
    return table(header, body, stack=True)


def ad_detail(ctx: Ctx, key: str, label: str, fmt: str, full: Dict[str, Any], base: Dict[str, Any]) -> str:
    """The "Open this ad" view: the plain answer first (preview, verdict, confidence, how to improve), then the numbers, then the technical reasons."""
    grade = ctx.grade_index.get(key)
    judged = "verdict_id" in full
    cls = entry_class(full) if judged else None
    fix = interact.improvement(grade, full if judged else None)
    chip = '<span class="badge %s">%s</span>' % (cls, esc(VERDICT_LABEL[cls])) if cls else ""
    sentence = say(strip_confidence(str(full["sentence"]), full.get("confidence"))) if full.get("sentence") else "n/a (no verdict sentence)"
    reasons = full.get("reasons") or []
    why = '<ul class="reasons">%s</ul>' % "".join("<li>%s</li>" % say(r) for r in reasons) if reasons else '<p class="muted">n/a (no verdict reasons supplied)</p>'
    conf = ("%s (%s)" % (full["confidence"], full.get("confidence_reason") or "no reason given")) if full.get("confidence") else "n/a (no verdict supplied)"
    bands = interact.band_rows(grade, ctx.money, fmt)
    metrics = (_table_of([(b["label"], b["value"], b["band"]) for b in bands], [("Metric", False), ("Value", True), ("Against your own ads", False)])
               if bands else '<p class="muted">not graded: no grade data for this ad. Run creative-grader with --json and pass --grade.</p>')
    funnel_rows = interact.ad_funnel(ctx.ad_index.get(key), fmt)
    funnel_table = _table_of([(f["step"], f["count"], f["share"]) for f in funnel_rows], [("Step", False), ("Count", True), ("Share of impressions", True)])
    age = full.get("age_days") if full.get("age_days") is not None else base.get("age_days")
    basis = full.get("age_basis") or base.get("age_basis")
    age_text = "%d days%s" % (age, " (%s)" % basis if basis else "") if age is not None else "n/a (age is not in the data)"
    lines = []
    if fix["lead"]:
        lines.append('<p><b>First:</b> %s</p>' % esc(fix["lead"]))
    if fix["fix"]:
        lines.append("<p><b>Then:</b> %s</p>" % say(fix["fix"]))
    if fix["also"]:
        lines.append("<p>%s</p>" % say(fix["also"]))
    if fix["note"]:
        lines.append('<p class="muted">%s</p>' % esc(fix["note"]))
    prompt = ""
    if cls in PROMPT_CLASSES:
        prompt = ('<div class="next-version"><h5>Make the next version</h5><p class="muted">Copy this into your agent. It points at the '
                  'hook-writer and creative-brief skills.</p><pre class="prompt">%s</pre>'
                  '<button type="button" class="btn" data-action="copy-prompt">Make the next version</button></div>'
                  % esc(interact.next_version_prompt(ctx.record_index.get(key) or {"label": label, "format": fmt}, grade)))
    return ('<details class="open-ad"><summary>Open this ad</summary><div class="open-body"><div class="ob-top"><div class="ob-media">%s</div>'
            '<div class="ob-main"><p class="chips">%s</p><p class="sentence">%s</p><h5>Confidence</h5><p>%s</p>'
            '<h5>How to improve</h5><div class="improve">%s</div>%s</div></div>'
            '<h5>Graded metrics</h5>%s<h5>Funnel for this ad</h5>%s<h5>Age</h5><p>%s</p>'
            '<details class="tech"><summary>Technical detail: why this verdict</summary>%s</details></div></details>'
            % (_image(ctx, key, label, fmt, big=True), chip, sentence, esc(conf), "".join(lines), prompt,
               metrics, funnel_table, esc(age_text), why))


def ad_card(ctx: Ctx, entry: Dict[str, Any], driver: str = "", next_step: bool = False) -> str:
    """The one ad component: image, label, id, spend, what placed it, verdict, confidence and sentence."""
    base = _fields_for(ctx, entry)
    ad_id = entry.get("ad") or base.get("ad_id")
    key = str(ad_id)
    name = entry.get("ad_name") or entry.get("name") or base.get("ad_name")
    label = readable_label(base, name, ad_id)
    fmt = str(base.get("format") or "")
    spend = (ctx.ad_index.get(key) or {}).get("spend", entry.get("spend"))
    judged = "verdict_id" in entry
    cls = entry_class(entry) if judged else None
    chip = ('<span class="badge %s">%s</span>' % (cls, esc(VERDICT_LABEL[cls]))) if cls else ""
    conf = ('<span class="conf" title="%s">%s</span>' % (esc(entry.get("confidence_reason") or ""), esc(entry["confidence"]))
            if entry.get("confidence") else "")
    sentence = ('<p class="sentence">%s</p>' % say(strip_confidence(str(entry["sentence"]), entry.get("confidence")))
                if entry.get("sentence") else "")
    if judged and not recognised(entry):
        sentence += '<p class="muted">Can\'t judge: unrecognised verdict.</p>'
    step = '<p class="next"><b>Next:</b> %s</p>' % esc(NEXT_STEP[cls]) if (next_step and cls) else ""
    check = ""
    if cls == "kill":
        check = '<p class="check"><b>Check first:</b> %s</p>' % esc(entry.get("check") or PAUSE_CHECK)
    drive = '<p class="driver">%s</p>' % esc(driver) if driver else ""
    full = ctx.verdict_index.get(key) or entry
    full_cls = entry_class(full) if "verdict_id" in full else None
    action = ('<p class="card-actions"><button type="button" class="btn" data-action="copy-prompt">Make the next version</button></p>'
              if full_cls in PROMPT_CLASSES else "")
    badge = interact.format_label(fmt) + (" %s" % clock(ctx.video_lengths[key]) if key in ctx.video_lengths else "")
    return ('<article class="ad-card" data-ad="%s"><div class="ad-img"><span class="fmt-badge">%s</span>%s</div><div class="ad-body"><h4>%s</h4>'
            '<p class="adid">Ad ID %s</p><p class="ad-spend"><b>%s</b> spend</p>%s<p class="chips">%s%s</p>%s%s%s%s%s</div></article>'
            % (esc(key), esc(badge), _image(ctx, ad_id, label, fmt), esc(label), esc(ad_id if ad_id is not None else "n/a"),
               esc(ctx.money(spend)), drive, chip, conf, sentence, step, check, action, ad_detail(ctx, key, label, fmt, full, base)))


def card_grid(cards: Sequence[str]) -> str:
    return '<div class="ad-grid">%s</div>' % "".join(cards)


def compact_list(ctx: Ctx, entries: Sequence[Dict[str, Any]], what: str, cap: Optional[int] = LIST_CAP) -> str:
    """A closed <details> holding a compact table of the ads not shown as cards, capped at `cap` rows (None: every ad)."""
    if not entries:
        return ""
    shown = entries if cap is None else entries[:cap]
    body = []
    for e in shown:
        base = _fields_for(ctx, e)
        ad_id = e.get("ad") or base.get("ad_id")
        spend = (ctx.ad_index.get(str(ad_id)) or {}).get("spend", e.get("spend"))
        cls = entry_class(e) if "verdict_id" in e else None
        body.append('<tr data-ad="%s"><td class="adname">%s<small>Ad ID %s</small></td><td class="num" data-label="Spend">%s</td><td>%s</td></tr>'
                    % (esc(ad_id), esc(readable_label(base, e.get("ad_name") or e.get("name") or base.get("ad_name"), ad_id)),
                       esc(ad_id), esc(ctx.money(spend)), esc(VERDICT_LABEL[cls]) if cls else ""))
    more = "" if cap is None or len(entries) <= cap else '<p class="muted">Showing the %d largest of %d; %d more are not listed.</p>' % (
        cap, len(entries), len(entries) - cap)
    return ('<details class="rest"><summary>%d more %s (compact list)</summary>%s%s</details>'
            % (len(entries), esc(what), table([("Ad", False), ("Spend", True), ("Verdict", False)], body, stack=True), more))


# ---------- numbers from rows ----------

def _day(row: Dict[str, Any]) -> Optional[str]:
    parsed = cm._parse_date(row.get("date"))
    return parsed.isoformat() if parsed else None


def coverage(rows: Sequence[Dict[str, Any]], fields: Sequence[str]) -> List[str]:
    """One note per field that is present on some rows and missing on others; fully present or fully missing is not partial."""
    notes = []
    for field in dict.fromkeys(fields):
        missing = sum(1 for r in rows if r.get(field) is None)
        if 0 < missing < len(rows):
            notes.append("%s missing on %d of %d rows" % (interact.FIELD_WORDS.get(field, field), missing, len(rows)))
    return notes


def totals(rows: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Sum each base field over rows. Reach never adds up across ads and days, so it stays None."""
    out: Dict[str, Optional[float]] = {}
    for field in cm.NUMERIC_FIELDS:
        values = [r[field] for r in rows if r.get(field) is not None]
        out[field] = sum(values) if values else None
    out["reach"] = None
    out["video_views_3s_source"] = ("derived" if any(str(r.get("video_views_3s_source") or "").startswith("derived") for r in rows) else None)
    return out


def daily(rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Optional[float]]]]:
    """Per-day totals. A day made of one row keeps that row's reach (so one ad's daily frequency can be read); more rows never add reach."""
    days: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = _day(row)
        if key:
            days.setdefault(key, []).append(row)
    out = []
    for day in sorted(days):
        day_total = totals(days[day])
        if len(days[day]) == 1:
            day_total["reach"] = days[day][0].get("reach")
        out.append((day, day_total))
    return out


def _pct_change(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior) * 100


def _kpi_value(total: Dict[str, Optional[float]], key: str) -> Optional[float]:
    return total.get(key) if key in cm.NUMERIC_FIELDS else cm.compute_metrics(total).get(key)


def _kpi_text(ctx: Ctx, total: Dict[str, Optional[float]], key: str, kind: str) -> str:
    value = _kpi_value(total, key)
    if value is None:
        if key in cm.METRICS:
            return interact.plain_ids(cm.format_value(total, key))
        return "n/a (missing %s)" % interact.FIELD_WORDS.get(key, key)
    if kind.startswith("money"):
        return ctx.money(value, int(kind[-1]))
    if kind == "int":
        return "{:,.0f}".format(value)
    if kind == "pct":
        return "%.2f%%" % value
    return "%.2fx" % value


VIDEO_KPIS = {"hook_rate": ("video_views_3s",), "hold_rate": ("video_views_3s", "video_thruplay")}


def video_rows(rows: Optional[Sequence[Dict[str, Any]]], key: str) -> List[Dict[str, Any]]:
    """Rows that can have the plays a video rate needs: a static or carousel ad has none, and must not dilute the rate."""
    return [r for r in rows or [] if all(r.get(f) is not None for f in VIDEO_KPIS[key])]


def video_ads(ads: Sequence[Dict[str, Any]], key: str) -> int:
    return sum(1 for a in ads if all(a.get(f) is not None for f in VIDEO_KPIS[key]))


def kpi_strip(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state("There are no ad rows, so no totals can be added up.",
                           "Pass an Ads Manager export or the connector pull as the data file.")
    total = totals(ctx.rows)
    prior_total = totals(ctx.prior) if ctx.prior else None
    series = daily(ctx.rows)
    ctr_basis = cm.metric_basis(total, "ctr")["numerator"]
    derived = total.get("video_views_3s_source") == "derived"
    tiles = []
    needs = {"spend": ("spend",), "impressions": ("impressions",), "conversions": ("conversions",), "conversion_value": ("conversion_value",),
             "cpm": ("spend", "impressions"), "ctr": (ctr_basis or "link_clicks", "impressions"), "cpa": ("spend", "conversions"),
             "roas": ("conversion_value", "spend"), "hook_rate": ("video_views_3s", "impressions"), "hold_rate": ("video_thruplay", "video_views_3s")}
    for key, name, kind in KPI_ORDER:
        tot, ptot, sser, video_note = total, prior_total, series, ""
        if key in VIDEO_KPIS:
            vrows = video_rows(ctx.rows, key)
            tot, sser = totals(vrows), daily(vrows)
            ptot = totals(video_rows(ctx.prior, key)) if ctx.prior else None
            video_note = "video ads only (%d of %d ads)" % (video_ads(ctx.ads, key), len(ctx.ads))
        if key == "reach":
            text = "{:,.0f}".format(ctx.account["reach"]) if ctx.account else NEEDS_ACCOUNT
        elif key == "frequency":
            text = "%.2f" % ctx.account["frequency"] if ctx.account else NEEDS_ACCOUNT
        else:
            text = _kpi_text(ctx, tot, key, kind)
        label = name
        if key == "ctr" and ctr_basis == "clicks":
            label = "CTR (all clicks)"
        if key == "hook_rate" and derived:
            label += " (derived)"
        if key in ("reach", "frequency") or prior_total is None:
            delta = "no prior period" if prior_total is None else "n/a (reach is account-level only)"
        else:
            change = _pct_change(_kpi_value(tot, key), _kpi_value(ptot, key)) if ptot is not None else None
            delta = "n/a (prior value missing or zero)" if change is None else "%+.1f%% vs prior period" % change
        spark = ""
        if key not in ("reach", "frequency"):
            spark = charts.sparkline([_kpi_value(day_total, key) for _, day_total in sser], "%s by day" % name)
        spark_note = spark or ('<span class="muted">%s</span>' % ("one day of data" if len(sser) == 1 else
                                                                   "no sparkline for reach or frequency" if key in ("reach", "frequency") else "no dated rows"))
        unit = " (%s)" % (ctx.currency or "account currency") if kind.startswith("money") else ""
        partial = [] if video_note else coverage(ctx.rows, needs.get(key, ()))
        unknown = " unknown" if text.startswith("n/a") else ""
        notes = ([video_note] if video_note else []) + partial
        note_html = '<p class="kpi-note">%s</p>' % esc("; ".join(notes)) if notes else ""
        tiles.append('<div class="kpi%s%s"><p class="kpi-name">%s%s</p><p class="kpi-value">%s</p>%s<p class="kpi-delta">%s</p><div class="kpi-spark">%s</div></div>'
                     % (unknown, " partial" if partial else "", esc(label), esc(unit), esc(text), note_html, esc(delta), spark_note))
    note = ""
    if not ctx.account:
        note = ('<p class="muted">Reach and frequency do not add up across ads and days, so they come only from an account-level pull. '
                'Pull account-level reach and frequency for this window, save them as JSON with a "reach" and a "frequency" number and pass the file with <code>--account</code>.</p>')
    return '<div class="kpis">%s</div>%s' % ("".join(tiles), note), "data"


def over_time(ctx: Ctx) -> Tuple[str, str]:
    series = daily(ctx.rows)
    if not series:
        return empty_state("The rows carry no dates, so there is no daily series.",
                           "Export or pull daily rows (a day column), not one summary row per ad.")
    labels = [d for d, _ in series]
    spend = [t["spend"] for _, t in series]
    roas = [cm.compute_metrics(t)["roas"] for _, t in series]
    use_roas = any(v is not None for v in roas)
    line = roas if use_roas else [cm.compute_metrics(t)["cpa"] for _, t in series]
    unit = "ROAS (x)" if use_roas else "CPA (%s)" % (ctx.currency or "account currency")
    chart = charts.combo_chart(labels, spend, line, "Spend (%s)" % (ctx.currency or "account currency"), unit,
                               "Daily spend with %s" % unit.split(" (")[0])
    note = ""
    if len(series) == 1:
        note = '<p class="muted">One day of data: there is no trend to read yet.</p>'
    elif not use_roas:
        note = '<p class="muted">No purchase value in the data, so the line shows CPA instead of ROAS.</p>'
    if not chart:
        return empty_state("Neither spend nor %s could be read from the rows." % unit, "Include the spend and purchase columns in the export.")
    return chart + note, "data"


def do_first(ctx: Ctx) -> Tuple[str, str]:
    items = [e for e in (((ctx.verdicts or {}).get("summary") or {}).get("do_first") or []) if entry_class(e) != "cant"]
    if not items:
        return empty_state("The keep-or-kill verdicts were not supplied, or no ad needs an action.",
                           "Run keep-or-kill with --json and pass --verdicts.")
    cards = [ad_card(ctx, e, driver="Spend at stake: %s" % ctx.money(e.get("spend_at_stake")), next_step=True) for e in items]
    return card_grid(cards), "data"


def _sum_column(rows: Sequence[Dict[str, Any]], aliases: Sequence[str]) -> Tuple[Optional[float], Optional[str]]:
    header, total = None, None
    for row in rows:
        for key, value in row.items():
            if re.sub(r"[^a-z0-9]", "", str(key).lower()) in aliases:
                try:
                    number = float(str(value).replace(",", "")) if value not in (None, "") else None
                except ValueError:
                    number = None
                if number is not None:
                    header = header or str(key)
                    total = (total or 0.0) + number
    return total, header


def video_step(rows: Sequence[Dict[str, Any]], field: str, value: float) -> Tuple[str, str]:
    """Share and step rate of a video step, read on video impressions: static and carousel ads have no plays, so counting their impressions would dilute it."""
    played = [r for r in rows if r.get("video_views_3s") is not None]
    base = sum(r.get("impressions") or 0 for r in played)
    if not base:
        return "n/a (no video impressions)", "n/a (no video impressions)"
    share = "%.2f%% of video impressions" % (value / base * 100)
    if field == "video_views_3s":
        return share, share
    both = [r for r in played if r.get("video_thruplay") is not None]
    plays = sum(r["video_views_3s"] for r in both)
    return share, "n/a (no 3-second plays)" if not plays else "%.2f%% of 3-second plays" % (sum(r["video_thruplay"] for r in both) / plays * 100)


def funnel(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state("There are no ad rows to count funnel steps from.", "Pass an Ads Manager export or the connector pull as the data file.")
    counts = totals(ctx.rows)
    for field, aliases in FUNNEL_COLUMNS.items():
        counts[field], ctx.funnel_headers[field] = _sum_column(ctx.rows, aliases)
    base = counts.get("impressions")
    rows_html, previous, gap = [], None, None
    for name, field in FUNNEL_STEPS:
        value = counts.get(field)
        if value is None:
            rows_html.append('<tr><td>%s</td><td class="num" data-label="Count">n/a (missing %s)</td><td class="num" data-label="Share of impressions">n/a</td>'
                             '<td class="num" data-label="From the step before">n/a</td></tr>' % (esc(name), esc(interact.FIELD_WORDS.get(field, field))))
            gap = gap or name
            continue
        share = "n/a" if not base else "%.2f%%" % (value / base * 100)
        video_rate = video_step(ctx.rows, field, value) if field in VIDEO_KPIS.get("hold_rate") else None
        if video_rate:
            share, rate = video_rate
        elif previous is None and name != "Impressions":
            rate = "n/a (no earlier step)"
        elif gap:
            rate = "n/a (not computed across the missing %s step)" % gap
        elif name == "Impressions":
            rate = "start"
        else:
            rate = "n/a (step before is zero)" if not previous else "%.2f%%" % (value / previous * 100)
        rows_html.append('<tr><td>%s</td><td class="num" data-label="Count">%s</td><td class="num" data-label="Share of impressions">%s</td>'
                         '<td class="num" data-label="From the step before">%s</td></tr>'
                         % (esc(name), "{:,.0f}".format(value), esc(share), esc(rate)))
        previous, gap = value, None
    note = ('<p class="muted">Video steps count video ads only, so a step can be larger than the one before it where other formats add '
            'clicks. 3-second plays and ThruPlays are rated on video impressions (%d of %d ads are video); the other steps on all impressions.</p>'
            % (video_ads(ctx.ads, "hook_rate"), len(ctx.ads)))
    partial = coverage(ctx.rows, [f for _, f in FUNNEL_STEPS if f in cm.NUMERIC_FIELDS])
    if partial:
        note += '<p class="muted">Partial coverage, so a step may be understated: %s.</p>' % esc("; ".join(partial))
    if counts.get("video_views_3s_source") == "derived":
        note += '<p class="muted">3-second plays (derived): spend divided by cost per 3-second view, not reported.</p>'
    return table([("Step", False), ("Count", True), ("Share of impressions", True), ("From the step before", True)], rows_html, stack=True) + note, "data"


# ---------- Pareto ----------

def pareto_rows(ctx: Ctx) -> Tuple[List[Dict[str, Any]], bool]:
    """Ads with spend, largest first, and whether the cut is read on purchase value (else on spend)."""
    ranked = sorted((a for a in ctx.ads if a.get("spend")), key=lambda a: -a["spend"])
    has_value = sum(a.get("conversion_value") or 0 for a in ranked) > 0
    return ranked, has_value


def pareto_cut(ctx: Ctx) -> Optional[Dict[str, Any]]:
    ranked, has_value = pareto_rows(ctx)
    if not ranked:
        return None
    key = "conversion_value" if has_value else "spend"
    total_spend = sum(a["spend"] for a in ranked)
    total_basis = sum(a.get(key) or 0 for a in ranked)
    cum_spend, cum_basis, run_s, run_b, cut = [], [], 0.0, 0.0, None
    for i, a in enumerate(ranked):
        run_s += a["spend"]
        run_b += a.get(key) or 0
        cum_spend.append(run_s / total_spend * 100)
        cum_basis.append(run_b / total_basis * 100)
        if cut is None and cum_basis[-1] >= ctx.pareto_share:
            cut = i + 1
    ads_with = sum(1 for a in ranked if a.get("conversion_value") is not None)
    rows_missing = sum(1 for r in ctx.rows if r.get("conversion_value") is None)
    partial = has_value and (ads_with < len(ranked) or 0 < rows_missing < len(ctx.rows))
    return {"ranked": ranked, "has_value": has_value, "cum_spend": cum_spend, "cum_basis": cum_basis, "cut": cut or len(ranked),
            "head_basis": cum_basis[(cut or len(ranked)) - 1],
            "coverage": ("Purchase value is present for %d of %d ads and on %d of %d rows; an ad or row without it counts as no value."
                         % (ads_with, len(ranked), len(ctx.rows) - rows_missing, len(ctx.rows))) if partial else None}


def pareto_sentence(ctx: Ctx, info: Dict[str, Any]) -> str:
    n, total = info["cut"], len(info["ranked"])
    what = "purchase value" if info["has_value"] else "spend"
    text = "%d ads (%.0f%% of ads) drive %.0f%% of %s." % (n, n / total * 100, info["head_basis"], what)
    if not info["has_value"]:
        text += " There is no purchase value in the data, so this is read on spend."
    if info.get("coverage"):
        text += " " + info["coverage"]
    return text


def pareto(ctx: Ctx) -> Tuple[str, str]:
    info = pareto_cut(ctx)
    if not info:
        return empty_state("No ad has any spend, so there is nothing to rank.", "Pass an export or connector pull that includes spend per ad.")
    chart = charts.pareto_chart([a["spend"] for a in info["ranked"]], info["cum_spend"], info["cum_basis"] if info["has_value"] else None,
                                info["cut"], "Pareto: ads ranked by spend", ctx.currency or "account currency")
    lead = '<p class="lead">%s</p>' % esc(pareto_sentence(ctx, info))
    note = ('<p class="muted">The cut is the fewest top-spend ads whose cumulative %s reaches %.0f%%. That share is a common convention, not a rule: '
            'change it with <code>--pareto-share</code> to suit your account.</p>' % ("purchase value" if info["has_value"] else "spend", ctx.pareto_share))
    return lead + chart + note, "data"


def head_tail(ctx: Ctx) -> Tuple[str, str]:
    info = pareto_cut(ctx)
    if not info:
        return empty_state("No ad has any spend, so there is no head or tail to show.", "Pass an export or connector pull that includes spend per ad.")
    ads = info["ranked"]
    share = cm.concentration(ads, top_n=ctx.concentration_n)
    gauge = charts.gauge(share, "Share of spend in the top %d ads" % ctx.concentration_n,
                         "Top %d ads (N=%d, an arbitrary default: set your own) hold this share of spend." % (ctx.concentration_n, ctx.concentration_n))
    head = ads[:info["cut"]]
    shown, held = head[:ctx.top_n], head[ctx.top_n:]
    cards = [ad_card(ctx, {"ad": a.get("ad_id") or a.get("ad_name"), "ad_name": a.get("ad_name")},
                     driver="Cumulative %s: %.0f%%" % ("value" if info["has_value"] else "spend", info["cum_basis"][i]))
             for i, a in enumerate(shown)]
    gallery = "<h3>The ads that carry the account (top %d of %d in the head)</h3>%s" % (len(shown), len(head), card_grid(cards))
    tail = ads[info["cut"]:]
    rest = held + tail
    tail_spend = sum(a["spend"] for a in tail)
    tail_value = sum(a.get("conversion_value") or 0 for a in tail)
    summary = ('<p class="muted">Long tail: %d ads, %s spend, %s purchase value.%s</p>'
               % (len(tail), esc(ctx.money(tail_spend)), esc(ctx.money(tail_value) if info["has_value"] else "n/a (no purchase value)"),
                  " %d more head ads are listed below the cards." % len(held) if held else ""))
    entries = [{"ad": a.get("ad_id") or a.get("ad_name"), "ad_name": a.get("ad_name")} for a in rest]
    return gauge + gallery + summary + compact_list(ctx, entries, "ads outside the gallery"), "data"


# ---------- Keep / kill ----------

def _stake(entry: Dict[str, Any]) -> float:
    return entry.get("spend_at_stake") or entry.get("spend") or 0


def verdict_board(ctx: Ctx) -> Tuple[str, str]:
    ads = [dict(e, verdict_id=e.get("verdict_id") or "") for e in (ctx.verdicts or {}).get("ads") or []]
    if not ads:
        return empty_state("The keep-or-kill verdicts were not supplied, so no ad has a call.",
                           "Run keep-or-kill with --json and pass --verdicts.")
    columns = {cls: [] for cls, _ in BOARD}
    for entry in ads:
        columns[entry_class(entry)].append(entry)
    thin = ((ctx.verdicts.get("summary") or {}).get("thin_groups")) or []
    note = ""
    if thin:
        note = ('<p class="muted">Small comparison groups, read as early: %s. Fewer than %d similar ads make a grade less certain.</p>'
                % (esc(", ".join("%s (%s ads)" % (t.get("group"), t.get("ads")) for t in thin)), cm.MIN_GROUP))
    bases = list(dict.fromkeys(e["payback_basis"] for e in ads if e.get("payback_basis")))
    basis = '<p class="muted"><b>Judged on:</b> %s.</p>' % esc("; ".join(bases)) if bases else ""
    cols = []
    for cls, name in BOARD:
        ordered = sorted(columns[cls], key=lambda e: -_stake(e))
        cards = [ad_card(ctx, e, driver="Spend at stake: %s" % ctx.money(e.get("spend_at_stake"))) for e in ordered[:ctx.top_n]]
        cols.append('<div class="col col-%s"><h3><span class="badge %s">%s</span> <span class="count">%d</span></h3>%s%s</div>'
                    % (cls, cls, esc(name), len(ordered), "".join(cards) or '<p class="muted">No ads in this column.</p>',
                       compact_list(ctx, ordered[ctx.top_n:], "%s ads" % name.lower())))
    lead = '<p class="muted">Each column shows its top %d ads by spend at stake (N=%d, set it with <code>--top-n</code>); the rest are collapsed.</p>' % (ctx.top_n, ctx.top_n)
    return note + basis + lead + '<div class="board">%s</div>' % "".join(cols), "data"


def fatigue(ctx: Ctx) -> Tuple[str, str]:
    ads = (ctx.verdicts or {}).get("ads") or []
    points = [(e["age_days"], e["fatigue"]["ctr_change"], readable_label(_fields_for(ctx, e), e.get("ad_name"), e.get("ad")))
              for e in ads if e.get("age_days") is not None and (e.get("fatigue") or {}).get("ctr_change") is not None]
    top = sorted(ctx.ads, key=lambda a: -(a.get("spend") or 0))[:ctx.top_n]
    if not ctx.rows and not points:
        return empty_state("Neither daily rows nor keep-or-kill fatigue readings were supplied.",
                           "Pass the daily data file, and run keep-or-kill with --json and pass --verdicts.")
    multiples = []
    for ad in top:
        key = str(ad.get("ad_id") or ad.get("ad_name"))
        mine = [r for r in ctx.rows if key in (str(r.get("ad_id")), str(r.get("ad_name")))]
        series = [(d, cm.compute_metrics(t)) for d, t in daily(mine)]
        if len(series) < 2:
            continue
        labels = [d for d, _ in series]
        label = readable_label(ad, ad.get("ad_name"), key)
        ctr = charts.combo_chart(labels, None, [m["ctr"] for _, m in series], "", "CTR (%)", "CTR by day: %s" % label, width=300, height=190)
        freq = charts.combo_chart(labels, None, [m["frequency"] for _, m in series], "", "Frequency (x)", "Frequency by day: %s" % label, width=300, height=190)
        multiples.append('<div class="multiple"><h4>%s</h4>%s%s</div>' % (esc(label), ctr, freq))
    parts = []
    if multiples:
        parts.append('<h3>CTR and frequency by day, top %d ads by spend</h3><div class="multiples">%s</div>' % (len(multiples), "".join(multiples)))
    plot = charts.scatter(points, "Ad age (days)", "CTR change (%)", "Ad age against CTR change, first versus last days of delivery")
    if plot:
        parts.append("<h3>Age against CTR change</h3>" + plot)
    if not parts:
        return empty_state("No ad has two or more delivery days or a fatigue reading.",
                           "Pull daily rows over a longer window, and run keep-or-kill with --json and pass --verdicts.")
    return "".join(parts), "data"


# ---------- interaction: ways to improve, All ads, filter bar, dialog, pool ----------

def default_group(ctx: Ctx) -> str:
    return "verdict" if any(f["key"] == "verdict" for f in ctx.facets) else "none"


def ways_to_improve(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.grade or not ctx.records:
        return empty_state("The creative-grader results were not supplied, so no ad has a diagnosed weak step.",
                           "Run creative-grader with --json and pass the file with --grade.")
    groups = interact.weak_groups(ctx.records)
    total = len(ctx.records)
    diagnosed = sum(g["ads"] for g in groups if g["step"] not in (None, "none"))
    body = []
    for g in groups:
        words = g["words"] if g["step"] is None else g["words"][:1].upper() + g["words"][1:]
        token = "undiagnosed" if g["step"] is None else g["step"]
        share = "n/a" if g["share"] is None else "%.0f%%" % g["share"]
        fix = g["fix"] or ("Nothing to change from the funnel." if g["step"] == "none" else "Add the missing data, then run creative-grader again.")
        body.append('<tr><td>%s</td><td class="num" data-label="Ads">%d</td><td class="num" data-label="Spend">%s (%s of spend)</td><td>%s</td>'
                    '<td><a href="#panel-all-ads" data-weak="%s">Show these ads</a></td></tr>'
                    % (esc(words), g["ads"], esc(ctx.money(g["spend"])), esc(share), esc(fix), esc(token)))
    lead = ('<p class="lead">%d of %d ads have a weak funnel step. Fix the step with the most spend first, then read again.</p>' % (diagnosed, total))
    note = '<p class="muted">Each ad is counted once, under the first weak step in the funnel; an ad can be weak further down too (its card says so).</p>'
    return lead + table([("What is weak", False), ("Ads", True), ("Spend", True), ("What to change", False), ("", False)], body, stack=True) + note, "data"


GROUP_LABELS = dict(interact.FACETS)


def all_ads(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.records:
        return empty_state("There are no ads to list.", "Pass an Ads Manager export or the connector pull as the data file, or the keep-or-kill output.")
    group = default_group(ctx)
    total = sum(r.get("spend") or 0 for r in ctx.records)
    groups = interact.group_records(ctx.records, group) if group != "none" else [{"key": "all", "label": "All ads", "records": ctx.records}]
    sections = []
    for g in groups:
        sub = interact.totals_of(g["records"], total, ctx.money)
        ordered = interact.by_stake(g["records"])
        entries = [entry_for(ctx, r) for r in ordered]
        sections.append(
            '<section class="group" data-group="%s"><header class="group-head"><h4>%s</h4><p class="group-sub">%d ads &middot; %s spend &middot; %s of spend &middot; ROAS %s &middot; CPA %s</p></header>%s%s</section>'
            % (esc(g["key"] if g["key"] is not None else "unknown"), esc(g["label"]), sub["ads"], esc(ctx.money(sub["spend"])),
               "n/a" if sub["share"] is None else "%.0f%%" % sub["share"], esc(sub["roas_text"]), esc(sub["cpa_text"]),
               card_grid([ad_card(ctx, e) for e in entries[:ctx.top_n]]), compact_list(ctx, entries[ctx.top_n:], "ads", cap=None)))
    group_options = '<option value="none"%s>None</option>' % (" selected" if group == "none" else "") + "".join(
        '<option value="%s"%s>%s</option>' % (key, " selected" if key == group else "", esc(GROUP_LABELS[key]))
        for key in interact.GROUPS if any(f["key"] == key for f in ctx.facets))
    sort_options = "".join('<option value="%s"%s>%s</option>' % (key, " selected" if key == "stake" else "", esc(label)) for key, label in interact.SORTS)
    controls = ('<div class="gallery-controls"><label>Group by <select data-action="group">%s</select></label>'
                '<label>Sort by <select data-action="sort">%s</select></label>'
                '<button type="button" class="chip" aria-pressed="false" data-action="previews-only">Previews only</button></div>' % (group_options, sort_options))
    lead = ('<p class="muted">Every ad, shown %s and sorted by spend at stake until you change it. The top %d of each group show as cards (N=%d, set it with <code>--top-n</code>), the rest as rows. '
            'Each group header adds up its own spend, with ROAS and CPA as ratios of sums.</p>'
            % ("grouped by verdict" if group == "verdict" else "in one list", ctx.top_n, ctx.top_n))
    return (lead + controls + '<div id="allads-static">%s</div><div id="allads-live" aria-live="polite"></div>' % "".join(sections)), "data"


def filter_bar(ctx: Ctx) -> str:
    """The sticky filter bar: search, smart views and facet chips with ad counts. Shown only when the page script runs."""
    if not ctx.records:
        return ""
    views = "".join('<button type="button" class="chip" aria-pressed="false" data-preset="%s" title="%s"><span class="chip-label">%s</span> <span class="n"></span></button>'
                    % (p["id"], esc(p["note"]), esc(p["label"] + (" (top %d)" % p["top"] if p.get("top") else ""))) for p in interact.PRESETS)
    groups = []
    for facet in ctx.facets:
        chips = "".join('<button type="button" class="chip" aria-pressed="false" data-facet="%s" data-value="%s"><span class="chip-label">%s</span> <span class="n">%d</span></button>'
                        % (facet["key"], esc(v["value"]), esc(v["label"]), v["count"]) for v in facet["values"])
        groups.append('<fieldset class="facet"><legend>%s</legend><div class="chips-row">%s</div></fieldset>' % (esc(facet["label"]), chips))
    note = '<p class="fb-note">Charts and key numbers stay account-wide. Filters change the ad cards, the rows and the All ads gallery.</p>'
    more = ('<details class="facets"><summary>More filters</summary><div class="facets-body">%s%s</div></details>' % (note, "".join(groups))) if groups else ""
    return ('<div class="filterbar" role="search" aria-label="Filter and group ads"><div class="fb-row">'
            '<label class="fb-search"><span class="fb-label">Search</span><input type="search" class="fb-input" placeholder="Label, name or ad ID" autocomplete="off"></label>'
            '<div class="fb-presets" role="group" aria-label="Smart views">%s</div>%s</div>'
            '<p class="fb-summary" role="status" aria-live="polite"></p>'
            '<p class="fb-empty" role="status">No ads match these filters. <button type="button" class="btn" data-action="clear">Clear filters</button></p>'
            '%s</div>' % (views, more, "" if groups else note))


DIALOG = ('<dialog class="ad-dialog" id="ad-dialog" aria-labelledby="ad-dialog-title"><div class="dlg-head"><h2 id="ad-dialog-title">Ad</h2>'
          '<button type="button" class="btn" data-action="close-dialog">Close</button></div><div class="dlg-body"></div></dialog>')


def pool_html(ctx: Ctx) -> str:
    """Every ad's full card in an inert template, so the page script can show any ad when the gallery is regrouped."""
    if not ctx.records:
        return ""
    return '<template id="ad-pool">%s</template>' % "".join(ad_card(ctx, entry_for(ctx, r)) for r in ctx.records)


def data_block(ctx: Ctx) -> str:
    if not ctx.records:
        return ""
    return '<script type="application/json" id="ad-data">%s</script>' % interact.payload_json(
        interact.payload(ctx.records, ctx.currency, ctx.top_n, default_group(ctx)))


def not_built(heading: str) -> Callable[[Ctx], Tuple[str, str]]:
    def panel(ctx: Ctx) -> Tuple[str, str]:
        return empty_state("The %s panels are not built in this version." % heading, "Not built in this version: they arrive in the next build of this dashboard.")
    return panel


# (tab id, tab title, ((panel id, eyebrow, heading, function), ...)): the order is part of the spec.
TABS = (
    ("overview", "Overview analysis", (
        ("kpis", "Overview", "Key numbers", kpi_strip),
        ("time", "Overview", "Performance over time", over_time),
        ("do-first", "Overview", "Do these first", do_first),
        ("improve", "Overview", "Ways to improve", ways_to_improve),
        ("funnel", "Overview", "Funnel", funnel))),
    ("pareto", "Pareto", (
        ("pareto", "Pareto", "Where the value comes from", pareto),
        ("head-tail", "Pareto", "The head and the long tail", head_tail))),
    ("keep-kill", "Keep / kill", (
        ("board", "Keep / kill", "Verdict board", verdict_board),
        ("fatigue", "Keep / kill", "Fatigue", fatigue),
        ("all-ads", "Keep / kill", "All ads", all_ads))),
    ("format", "Format", (("format", "Format", "Format scorecard, video and ad types", not_built("Format")),)),
    ("white-space", "White space", (("white-space", "White space", "Concept by format gaps", not_built("White space")),)),
    ("briefing", "Briefing", (("briefing", "Briefing", "Ready briefs and prompts", not_built("Briefing")),)),
)
