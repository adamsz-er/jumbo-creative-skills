"""The dashboard's panels: one function each, returning (html, state).

state is "data" when the panel was filled from the inputs and "empty" when it
shows a labelled empty state saying why and how to get the data. A panel is
never dropped and an empty state never looks like an answer. Standard library
only; every string that came from the data is escaped.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import benchmarks  # noqa: E402
import briefing  # noqa: E402
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
# field -> how to get it, for the banner that names metrics no ad in the pull can show
HOW_TO_GET = {
    "video_views_3s": "an Ads Manager export with the 3-second video plays column (the connector has no exact per-ad count)",
    "video_thruplay": "ThruPlays in the pull",
    "conversions": "purchases in the pull (Purchases in an export, omni_purchase from the connector)",
    "conversion_value": "purchase value in the pull (Purchases conversion value, or omni_purchase_values)",
    "link_clicks": "link clicks in the pull",
}
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
                 previews: Optional[Previews] = None, breakdowns: Optional[Sequence[Dict[str, Any]]] = None,
                 briefs: Optional[Any] = None, key_map: Optional[Dict[str, str]] = None) -> None:
        self.rows = list(rows or [])
        self.ads = cm.aggregate_by_ad(self.rows, key_map=key_map) if self.rows else []
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
        self.breakdowns = list(breakdowns) if breakdowns else None
        self.briefs = briefing.validate_briefs(briefs) if briefs else None
        self.headers = list(dict.fromkeys(key for row in self.rows for key in row))
        self.rows_by_ad: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.rows:
            self.rows_by_ad.setdefault(str(row.get("ad_id") or row.get("ad_name")), []).append(row)
        self.changes: Optional[Dict[str, Any]] = None
        self.gaps = list((mix or {}).get("gaps") or [])
        self.gap_numbers = {(g["concept"], g["format"]): n for n, g in enumerate(self.gaps, 1)}
        self.retention_headers: Dict[str, Optional[str]] = {}
        self.copy_headers: Dict[str, Optional[str]] = {}
        self.breakdown_dims: Dict[str, str] = {}
        self.benchmarks_used: List[Dict[str, Any]] = []
        self.ad_format = {str(a.get("ad_id") or a.get("ad_name")): a.get("format") or "unknown" for a in self.ads}
        self.format_spend: Dict[str, float] = {}
        for ad in self.ads:
            self.format_spend[ad.get("format") or "unknown"] = self.format_spend.get(ad.get("format") or "unknown", 0.0) + (ad.get("spend") or 0.0)
        self.colours = charts.format_colours({f: v for f, v in self.format_spend.items() if f != "unknown"})

    def prior_label(self) -> str:
        """What the prior period is called: the last review's date when a run compared itself with it, else "prior period"."""
        info = self.changes or {}
        made = str(info.get("previous_at") or "")
        return "last review (%s)" % made[:10] if made and info.get("account") is not None else "prior period"

    def colour(self, fmt: str) -> str:
        """The one colour a format has everywhere on the page; an unknown format is always the muted tone."""
        return self.colours.get(fmt, charts.OTHER_COLOUR)

    def format_name(self, fmt: str) -> str:
        return _group_name(fmt, "Format not known")

    def formats_by_spend(self) -> List[str]:
        return sorted(self.format_spend, key=lambda f: -self.format_spend[f])

    def rows_of_format(self, fmt: str) -> List[Dict[str, Any]]:
        return [r for r in self.rows if self.ad_format.get(str(r.get("ad_id") or r.get("ad_name"))) == fmt]

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
               if bands else '<p class="muted">not graded: no grade data for this ad. Run the creative-grader skill and add its grades when you rebuild this report.</p>')
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
    if entry.get("group_size"):
        conf += '<span class="conf group%s">vs %d similar ads%s</span>' % (
            " thin" if entry.get("thin") else "", entry["group_size"], ": small group" if entry.get("thin") else "")
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


def coverage(ads: Sequence[Dict[str, Any]], fields: Sequence[str]) -> List[str]:
    """One note per field recorded on some ads and not others; fully present or fully missing is not partial."""
    notes = []
    for field in dict.fromkeys(fields):
        have = sum(1 for a in ads if a.get(field) is not None)
        if 0 < have < len(ads):
            notes.append("%s recorded on %d of %d ads; the rest had none in this window" % (interact.FIELD_WORDS.get(field, field), have, len(ads)))
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


NEUTRAL_KPIS = ("spend", "impressions", "reach", "frequency")
LOWER_IS_BETTER = ("cpm", "cpa")
ACCOUNT_KPIS = ("reach", "frequency")


def gone_metrics(ctx: Ctx) -> List[str]:
    """Overview metrics no ad can give, in tile order: video rates when no ad has the plays, reach and frequency without an account-level figure."""
    if not ctx.ads:
        return []
    gone = [key for key in VIDEO_KPIS if not video_ads(ctx.ads, key)]
    return gone + ([] if ctx.account else list(ACCOUNT_KPIS))


INFO_ICON = ('<svg class="ico" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>')
REACH_NOTE = ("Reach and frequency don't add up across ads, so they need an account-level figure for this window; none was supplied. "
              "Pull account-level reach and frequency for the same window and add them when you rebuild this report.")


def missing_everywhere(ctx: Ctx) -> str:
    """One banner at the top of Overview naming the key numbers no ad can show in this pull, why, and how to get them; "" when none.

    Each tile reads a plain n/a (or its own reason); this says it once, up front. Reach and frequency are named here too
    when no account-level figure was supplied.
    """
    if not ctx.ads:
        return ""
    gone: Dict[str, List[str]] = {}
    for key, name, _ in KPI_ORDER:
        if key in ("reach", "frequency") or key not in cm.METRICS or any(a.get(key) is not None for a in ctx.ads):
            continue
        num, den, _ = cm.METRICS[key]
        field = next((f for f in num + den if all(a.get(f) is None for a in ctx.ads)), None)
        if field:
            gone.setdefault(field, []).append(name)
    refused = next((a["video_views_3s_source"] for a in ctx.ads
                    if str(a.get("video_views_3s_source") or "").startswith("not derived")), None)
    items = []
    for field, names in gone.items():
        why = refused if field == "video_views_3s" and refused else "missing %s" % interact.FIELD_WORDS.get(field, field)
        items.append("<li><b>%s</b>: %s. To get it: %s.</li>" % (
            esc(" and ".join(names)), esc(why), esc(HOW_TO_GET.get(field, "add %s to the pull" % interact.FIELD_WORDS.get(field, field)))))
    parts = ['<p><b>Not in this pull</b>, so these read n/a for every ad:</p><ul>%s</ul>' % "".join(items)] if items else []
    if "reach" in gone_metrics(ctx):
        parts.append("<p>%s</p>" % esc(REACH_NOTE))
    if not parts:
        return ""
    return '<div class="banner" role="note">%s<div>%s</div></div>' % (INFO_ICON, "".join(parts))


def _tile_value(text: str) -> Tuple[str, str]:
    """A tile's big value and, for an n/a, the plain reason that goes on its own muted line."""
    found = re.fullmatch(r"n/a \((.*)\)", text)
    return ("n/a", found.group(1)) if found else (text, "")


def _delta_pill(key: str, change: float, against: str = "prior period") -> str:
    good = change < 0 if key in LOWER_IS_BETTER else change > 0
    tone = "flat" if key in NEUTRAL_KPIS or change == 0 else "up" if good else "down"
    return '<span class="pill %s">%+.1f%%</span> vs %s' % (tone, change, against)


def kpi_strip(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state("There are no ads, so no totals can be added up.",
                           "Pass an Ads Manager export or the connector pull as the data file.")
    total = totals(ctx.rows)
    prior_total = totals(ctx.prior) if ctx.prior else None
    series = daily(ctx.rows)
    ctr_basis = cm.metric_basis(total, "ctr")["numerator"]
    derived = total.get("video_views_3s_source") == "derived"
    gone = gone_metrics(ctx)
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
            video_note = "" if key in gone else "video ads \u00b7 %d of %d" % (video_ads(ctx.ads, key), len(ctx.ads))
        if key == "reach":
            text = "{:,.0f}".format(ctx.account["reach"]) if ctx.account else "n/a"
        elif key == "frequency":
            text = "%.2f" % ctx.account["frequency"] if ctx.account else "n/a"
        else:
            text = _kpi_text(ctx, tot, key, kind)
        label = name
        if key == "ctr" and ctr_basis == "clicks":
            label = "CTR (all clicks)"
        if key == "hook_rate" and derived:
            label += " (derived)"
        value, reason = ("n/a", "") if key in gone else _tile_value(text)
        if prior_total is None:
            delta = ""
        elif key in ACCOUNT_KPIS:
            delta = '<span class="muted">n/a (reach is account-level only)</span>'
        else:
            change = _pct_change(_kpi_value(tot, key), _kpi_value(ptot, key)) if ptot is not None else None
            delta = '<span class="muted">n/a (prior value missing or zero)</span>' if change is None else _delta_pill(key, change, ctx.prior_label())
        spark = ""
        if key not in ACCOUNT_KPIS:
            cal = calendar(vrows if key in VIDEO_KPIS else ctx.rows)
            values = day_values(cal, key)
            tips = ["%s: %s" % (charts.day_label(d), _kpi_text(ctx, totals(_measure_rows(rs, key)), key, kind)) if v is not None else ""
                    for (d, rs), v in zip(cal, values)]
            spark = charts.sparkline(values, "%s by day" % name, tips=tips, average=rolling_values(cal, key))
        spark_note = spark or ("" if key in ACCOUNT_KPIS or key in gone else
                               '<span class="muted">%s</span>' % ("one day of data" if len(sser) == 1 else "no dates in the data"))
        unit = " (%s)" % (ctx.currency or "account currency") if kind.startswith("money") else ""
        partial = [] if video_note or key in gone else coverage(ctx.ads, needs.get(key, ()))
        notes = ([reason] if reason else []) + ([video_note] if video_note else []) + partial
        note_html = '<p class="kpi-note">%s</p>' % esc("; ".join(notes)) if notes else ""
        tiles.append('<div class="kpi%s%s"><p class="kpi-name">%s%s</p><p class="kpi-value">%s</p>%s%s<div class="kpi-spark">%s</div></div>'
                     % (" unknown" if value == "n/a" else "", " partial" if partial else "", esc(label), esc(unit), esc(value), note_html, '<p class="kpi-delta">%s</p>' % delta if delta else "", spark_note))
    caption = "" if prior_total is not None else '<p class="muted kpi-caption">No prior period supplied: deltas appear when you pass one.</p>'
    return '<div class="kpis">%s</div>%s' % ("".join(tiles), caption), "data"


TIME_METRICS = (("spend", "Spend", "money"), ("roas", "ROAS", "x"), ("cpa", "CPA", "money"), ("ctr", "CTR", "pct"),
                ("cpm", "CPM", "money"), ("hook_rate", "Hook rate", "pct"))
NO_DATES = ("The data carries no dates, so there is no daily series.",
            "Export or pull the data by day (a day column), not as one summary line per ad.")


def _kind_formats(ctx: Ctx, kind: str) -> Tuple[Callable[[float], str], Callable[[float], str]]:
    """(axis formatter, hover formatter) for a money, percent or ratio measure."""
    axis = charts.axis_format(kind, ctx.currency)
    if kind == "money":
        return axis, lambda v: ctx.money(v, 2)
    return axis, (lambda v: "%.2f%%" % v) if kind == "pct" else (lambda v: "%.2fx" % v)


def _unit_of(ctx: Ctx, name: str, kind: str) -> str:
    return "%s (%s)" % (name, {"money": ctx.currency or "account currency", "pct": "%", "x": "x"}[kind])


def calendar(rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Every calendar day from the first to the last in the data with that day's rows; a day with none stays in as an empty list (a gap)."""
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        day = _day(row)
        if day:
            by_day.setdefault(day, []).append(row)
    if not by_day:
        return []
    first, last = dt.date.fromisoformat(min(by_day)), dt.date.fromisoformat(max(by_day))
    return [((first + dt.timedelta(days=n)).isoformat(), by_day.get((first + dt.timedelta(days=n)).isoformat(), []))
            for n in range((last - first).days + 1)]


def _measure_rows(rows: Sequence[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Rows that carry every operand the measure needs. A missing operand (None) drops the row; a zero is a real value and stays in the sum."""
    if key in cm.NUMERIC_FIELDS:
        return [r for r in rows if r.get(key) is not None]
    num, den, _ = cm.METRICS[cm.resolve_metric(key)]
    return [r for r in rows if any(r.get(f) is not None for f in num) and any(r.get(f) is not None for f in den)]


def day_values(cal: Sequence[Tuple[str, List[Dict[str, Any]]]], key: str) -> List[Optional[float]]:
    """A measure per calendar day as a ratio of that day's sums; a day with no usable rows is None, never 0."""
    out: List[Optional[float]] = []
    for _, rows in cal:
        used = _measure_rows(rows, key)
        out.append(_kpi_value(totals(used), key) if used else None)
    return out


def rolling_values(cal: Sequence[Tuple[str, List[Dict[str, Any]]]], key: str, window: int = charts.SPARK_AVERAGE_DAYS,
                   need: int = charts.ROLLING_MIN_VALUES) -> List[Optional[float]]:
    """A rolling average over `window` days: a count (spend, impressions, ...) is its mean per day, a ratio is the ratio of the window's sums.

    Only days with rows that carry the measure count, and only those rows are summed; fewer than `need` such days is a gap.
    """
    out: List[Optional[float]] = []
    for i in range(len(cal)):
        days = [_measure_rows(rows, key) for _, rows in cal[max(0, i - window + 1):i + 1]]
        days = [d for d in days if d]
        if len(days) < need:
            out.append(None)
        elif key in cm.NUMERIC_FIELDS:
            out.append(sum(totals(d)[key] or 0 for d in days) / len(days))
        else:
            out.append(_kpi_value(totals([r for d in days for r in d]), key))
    return out


def _time_view(ctx: Ctx, cal, key: str, name: str, kind: str, spend_bars: Sequence[Optional[float]]) -> str:
    values = day_values(cal, key)
    if not any(v is not None for v in values):
        return ""
    axis, hover = _kind_formats(ctx, kind)
    labels = [d for d, _ in cal]
    lines = [{"name": "Daily", "values": values, "colour": charts.SERIES_VARS[0], "kind": "daily"},
             {"name": "7-day average", "values": rolling_values(cal, key), "colour": charts.SERIES_VARS[0], "kind": "avg"}]
    bars = None if key == "spend" else spend_bars
    return charts.line_chart(labels, lines, "%s by day with a 7-day average" % name, axis, _unit_of(ctx, name, kind), bars=bars,
                             bar_fmt=charts.axis_format("money", ctx.currency), bar_name="Spend", bar_unit=_unit_of(ctx, "Spend", "money"),
                             tip_fmt=hover, bar_tip_fmt=lambda v: ctx.money(v, 2),
                             caption="%s by day%s. A day with no data is a gap, not a zero." % (name, "; the faint bars are spend" if bars else ""))


def over_time(ctx: Ctx) -> Tuple[str, str]:
    cal = calendar(ctx.rows)
    if not cal:
        return empty_state(*NO_DATES)
    spend_bars = day_values(cal, "spend")
    views, skipped = [], []
    for key, name, kind in TIME_METRICS:
        chart = _time_view(ctx, cal, key, name, kind, spend_bars)
        if chart:
            views.append((key, name, chart))
        else:
            skipped.append(name)
    if not views:
        return empty_state("Neither spend nor any rate could be read from the data.", "Include the spend and purchase columns in the export.")
    notes = []
    if len(cal) == 1:
        notes.append("One day of data: there is no trend to read yet.")
    if skipped:
        notes.append("Not shown, no data for it: %s." % ", ".join(skipped))
    note = '<p class="muted">%s</p>' % esc(" ".join(notes)) if notes else ""
    return charts.switcher("time", views) + note, "data"


def spend_by_format(ctx: Ctx) -> Tuple[str, str]:
    cal = calendar(ctx.rows)
    if not cal:
        return empty_state(*NO_DATES)
    named = [f for f in ctx.formats_by_spend() if f != "unknown"]
    if len(named) < 2:
        return empty_state("Fewer than two formats could be read from the ad names, so there is no split to show.",
                           "Name ads with the convention in creative-context, or tell the creative-mix skill the naming pattern your ads use.")
    days = [(d, rows) for d, rows in cal if sum(r.get("spend") or 0 for r in rows) > 0]
    if len(days) < 2:
        return empty_state("Fewer than two days have spend, so there is no change over time to show.", "Pull the data by day over a longer window.")
    groups = named + (["unknown"] if "unknown" in ctx.format_spend else [])
    shares: Dict[str, List[float]] = {f: [] for f in groups}
    for _, rows in days:
        total = sum(r.get("spend") or 0 for r in rows)
        for f in groups:
            shares[f].append(sum(r.get("spend") or 0 for r in rows if ctx.ad_format.get(str(r.get("ad_id") or r.get("ad_name"))) == f) / total * 100)
    series = [(ctx.format_name(f), shares[f], ctx.colour(f)) for f in groups]
    chart = charts.stacked_area([d for d, _ in days], series, "Share of daily spend by format",
                                "Each band is a format's share of that day's spend. Days with no spend are left out.")
    return chart, "data"


def do_first(ctx: Ctx) -> Tuple[str, str]:
    items = [e for e in (((ctx.verdicts or {}).get("summary") or {}).get("do_first") or []) if entry_class(e) != "cant"]
    if not items:
        return empty_state("The keep-or-kill verdicts were not supplied, or no ad needs an action.",
                           "Run the keep-or-kill skill and add its verdicts when you rebuild this report.")
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
        return empty_state("There are no ads to count funnel steps from.", "Pass an Ads Manager export or the connector pull as the data file.")
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
    partial = coverage(ctx.ads, [f for _, f in FUNNEL_STEPS if f in cm.NUMERIC_FIELDS])
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
    partial = has_value and ads_with < len(ranked)
    return {"ranked": ranked, "has_value": has_value, "cum_spend": cum_spend, "cum_basis": cum_basis, "cut": cut or len(ranked),
            "head_basis": cum_basis[(cut or len(ranked)) - 1],
            "coverage": ("Purchase value was recorded on %d of %d ads; the rest had none in this window and count as no value."
                         % (ads_with, len(ranked))) if partial else None}


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
            'you can change it when you rebuild the report, to suit your account.</p>' % ("purchase value" if info["has_value"] else "spend", ctx.pareto_share))
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
                           "Run the keep-or-kill skill and add its verdicts when you rebuild this report.")
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
    lead = '<p class="muted">Each column shows its top %d ads by spend at stake (N=%d, a default you can change when you rebuild the report); the rest are collapsed.</p>' % (ctx.top_n, ctx.top_n)
    return note + basis + lead + '<div class="board">%s</div>' % "".join(cols), "data"


def fatigue(ctx: Ctx) -> Tuple[str, str]:
    ads = (ctx.verdicts or {}).get("ads") or []
    points = [(e["age_days"], e["fatigue"]["ctr_change"], readable_label(_fields_for(ctx, e), e.get("ad_name"), e.get("ad")))
              for e in ads if e.get("age_days") is not None and (e.get("fatigue") or {}).get("ctr_change") is not None]
    top = sorted(ctx.ads, key=lambda a: -(a.get("spend") or 0))[:ctx.top_n]
    if not ctx.rows and not points:
        return empty_state("Neither daily data nor keep-or-kill fatigue readings were supplied.",
                           "Pass the daily data file, and run the keep-or-kill skill and add its verdicts when you rebuild this report.")
    multiples = []
    for ad in top:
        key = str(ad.get("ad_id") or ad.get("ad_name"))
        mine = [r for r in ctx.rows if key in (str(r.get("ad_id")), str(r.get("ad_name")))]
        series = [(d, cm.compute_metrics(t)) for d, t in daily(mine)]
        if len(series) < 2:
            continue
        labels = [d for d, _ in series]
        label = readable_label(ad, ad.get("ad_name"), key)
        ctr = charts.combo_chart(labels, None, [m["ctr"] for _, m in series], "", "CTR (%)", "CTR by day: %s" % label, width=300, height=190,
                                  line_fmt=charts.axis_format("pct"))
        freq = charts.combo_chart(labels, None, [m["frequency"] for _, m in series], "", "Frequency (x)", "Frequency by day: %s" % label, width=300, height=190,
                                   line_fmt=charts.axis_format("x"))
        multiples.append('<div class="multiple"><h4>%s</h4>%s%s</div>' % (esc(label), ctr, freq))
    parts = []
    if multiples:
        parts.append('<h3>CTR and frequency by day, top %d ads by spend</h3><div class="multiples">%s</div>' % (len(multiples), "".join(multiples)))
    plot = charts.scatter(points, "Ad age (days)", "CTR change (%)", "Ad age against CTR change, first versus last days of delivery")
    if plot:
        parts.append("<h3>Age against CTR change</h3>" + plot)
    if not parts:
        return empty_state("No ad has two or more delivery days or a fatigue reading.",
                           "Pull daily data over a longer window, and run the keep-or-kill skill and add its verdicts when you rebuild this report.")
    return "".join(parts), "data"


# ---------- interaction: ways to improve, All ads, filter bar, dialog, pool ----------

def default_group(ctx: Ctx) -> str:
    return "verdict" if any(f["key"] == "verdict" for f in ctx.facets) else "none"


def ways_to_improve(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.grade or not ctx.records:
        return empty_state("The creative-grader results were not supplied, so no ad has a diagnosed weak step.",
                           "Run the creative-grader skill and add its grades when you rebuild this report.")
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
            '<section class="group" data-group="%s"><header class="group-head"><h4>%s</h4><p class="group-sub">%d ads &middot; %s spend &middot; %s of spend &middot; ROAS %s &middot; CPA %s%s</p></header>%s%s</section>'
            % (esc(g["key"] if g["key"] is not None else "unknown"), esc(g["label"]), sub["ads"], esc(ctx.money(sub["spend"])),
               "n/a" if sub["share"] is None else "%.0f%%" % sub["share"], esc(sub["roas_text"]), esc(sub["cpa_text"]),
               "".join(" &middot; %s" % esc(n) for n in (sub["roas_note"], sub["cpa_note"]) if n),
               card_grid([ad_card(ctx, e) for e in entries[:ctx.top_n]]), compact_list(ctx, entries[ctx.top_n:], "ads", cap=None)))
    lead = ('<p class="muted">Every ad, shown %s and sorted by spend at stake until you change it. The top %d of each group show as cards (N=%d, a default you can change when you rebuild the report), the rest as a compact list. '
            'Each group header adds up its own spend, with ROAS and CPA as ratios of sums.</p>'
            % ("grouped by verdict" if group == "verdict" else "in one list", ctx.top_n, ctx.top_n))
    return (lead + '<div id="allads-static">%s</div><div id="allads-live" aria-live="polite"></div>' % "".join(sections)), "data"


SEARCH_ICON = ('<svg class="ico" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>')


def view_controls(ctx: Ctx, kind: str) -> str:
    """Group, sort and previews-only: they shape the All ads gallery, so they sit with the filters and need the page script."""
    group = default_group(ctx)
    group_options = '<option value="none"%s>None</option>' % (" selected" if group == "none" else "") + "".join(
        '<option value="%s"%s>%s</option>' % (key, " selected" if key == group else "", esc(GROUP_LABELS[key]))
        for key in interact.GROUPS if any(f["key"] == key for f in ctx.facets))
    sort_options = "".join('<option value="%s"%s>%s</option>' % (key, " selected" if key == "stake" else "", esc(label)) for key, label in interact.SORTS)
    return ('<div class="fb-view %s"><label>Group by <select data-action="group">%s</select></label>'
            '<label>Sort by <select data-action="sort">%s</select></label>'
            '<button type="button" class="chip" aria-pressed="false" data-action="previews-only">Previews only</button></div>' % (kind, group_options, sort_options))


def filter_bar(ctx: Ctx) -> str:
    """One sticky row (search, Filters popover, Clear, count, view controls) and, below it and not sticky, the summary line. Shown only when the page script runs."""
    if not ctx.records:
        return ""
    views = "".join('<button type="button" class="chip" aria-pressed="false" data-preset="%s" title="%s"><span class="chip-label">%s</span> <span class="n"></span></button>'
                    % (p["id"], esc(p["note"]), esc(p["label"] + (" (top %d)" % p["top"] if p.get("top") else ""))) for p in interact.PRESETS)
    groups = []
    for facet in ctx.facets:
        chips = "".join('<button type="button" class="chip" aria-pressed="false" data-facet="%s" data-value="%s"><span class="chip-label">%s</span> <span class="n">%d</span></button>'
                        % (facet["key"], esc(v["value"]), esc(v["label"]), v["count"]) for v in facet["values"])
        groups.append('<fieldset class="facet"><legend>%s</legend><div class="chips-row">%s</div></fieldset>' % (esc(facet["label"]), chips))
    note = '<p class="fb-note">Charts and key numbers stay account-wide. Filters change the ad cards, the lists and the All ads gallery.</p>'
    popover = ('<details class="facets"><summary class="fb-filters">Filters<span class="fb-k"></span></summary><div class="facets-body">%s%s'
               '<fieldset class="facet"><legend>Smart views</legend><div class="chips-row" role="group" aria-label="Smart views">%s</div></fieldset>%s</div></details>'
               % (note, view_controls(ctx, "fb-view-pop"), views, "".join(groups)))
    return ('<div class="filterbar" role="search" aria-label="Filter and group ads">'
            '<label class="fb-search">%s<input type="search" class="fb-input" aria-label="Search ads" placeholder="Search label, name or ad ID" autocomplete="off"></label>'
            '%s<button type="button" class="btn ghost fb-clear" data-action="clear">Clear</button><span class="fb-spacer"></span>'
            '<span class="fb-count" role="status" aria-live="polite"></span>%s</div>'
            '<div class="fb-status"><p class="fb-summary" role="status" aria-live="polite"></p>'
            '<p class="fb-empty" role="status">No ads match these filters. <button type="button" class="btn" data-action="clear">Clear filters</button></p></div>'
            % (SEARCH_ICON, popover, view_controls(ctx, "fb-view-row")))


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


# ---------- tabs 4-6: Format, White space, Briefing ----------

MIN_FORMATS = 3  # arbitrary default: formats are graded against each other only with this many
HEATMAP_CONCEPTS = 18  # arbitrary display cap on the rows of a heatmap
RETENTION_ADS = 3  # arbitrary default: how many top-spend video ads get a retention line
STRIP_ADS = 3  # arbitrary default: example ads shown per format
COPY_ADS = 8  # arbitrary default: how many top-spend ads show their opening line
OPENING_CHARS = 90  # arbitrary: where an opening line is cut, at a word boundary
NOT_GRADED = "not graded: fewer than %d formats" % MIN_FORMATS
NO_MIX = ("The creative-mix results were not supplied, so there is no format, concept or ad-type breakdown.",
          "Run the creative-mix skill and add its results when you rebuild this report.")
NO_ROWS = ("There are no ads to read this from.", "Pass an Ads Manager export or the connector pull as the data file.")
FORMAT_COLUMNS = (("ctr", "CTR"), ("cpm", "CPM"), ("cpa", "CPA"), ("roas", "ROAS"), ("hook_rate", "Hook rate"), ("hold_rate", "Hold rate"))
LOWER_BETTER = ("cpm", "cpa")
QUADRANTS = ("Keeps the few it stops", "Stops people and keeps them", "Neither yet", "Stops people, loses them")
RETENTION_STEPS = (
    ("p25", "25% watched", "Video plays at 25%", ("videoplaysat25", "videowatchesat25", "videop25watchedactions")),
    ("p50", "50% watched", "Video plays at 50%", ("videoplaysat50", "videowatchesat50", "videop50watchedactions")),
    ("p75", "75% watched", "Video plays at 75%", ("videoplaysat75", "videowatchesat75", "videop75watchedactions")),
    ("p95", "95% watched", "Video plays at 95%", ("videoplaysat95", "videowatchesat95", "videop95watchedactions")),
    ("p100", "100% watched", "Video plays at 100%", ("videoplaysat100", "videowatchesat100", "videop100watchedactions")),
)
AVERAGE_TIME = ("videoaverageplaytime", "videoavgtimewatchedactions", "averagevideoplaytime")
COPY_COLUMNS = (
    ("primary text", ("primarytext", "body", "adbody", "bodytext")),
    ("headline", ("headline", "title", "adtitle")),
    ("call to action", ("calltoaction", "calltoactiontype", "cta")),
)
BREAKDOWN_DIMENSIONS = (
    ("age", "Age"), ("gender", "Gender"), ("placement", "Placement"), ("platform", "Platform"),
    ("publisherplatform", "Platform"), ("region", "Region"), ("country", "Country"),
)
TYPE_NOTES = {
    "bau": "Always-on creative that works without an offer: your baseline.",
    "promo": "Sale or offer creative with dates; retire it when the offer ends.",
    "launch": "Introduces a new product or a drop.",
    "hype": "Builds anticipation ahead of a launch or sale.",
    "partnership": "Creator-fronted or partner-handle ads.",
    "retention": "Speaks to people who already bought, so judge it apart.",
}


def _plain(value: Any) -> str:
    return interact.humanise(value, True)


def _group_name(value: Any, unknown: str) -> str:
    return unknown if value in (None, "", "unknown") else _plain(value)


def _ad_key(ad: Dict[str, Any]) -> str:
    return str(ad.get("ad_id") or ad.get("ad_name"))


def _by_spend(ads: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted((a for a in ads if a.get("spend")), key=lambda a: -a["spend"])


def _find_header(ctx: Ctx, aliases: Sequence[str]) -> Optional[str]:
    return next((str(h) for h in ctx.headers if re.sub(r"[^a-z0-9]", "", str(h).lower()) in aliases), None)


def _na(text: str) -> str:
    return "n/a (%s)" % text


def preview_tile(ctx: Ctx, ad_id: Any) -> str:
    """A small preview with the readable label and verdict chip; carries data-ad so the filters apply and opens the full ad view."""
    key = str(ad_id)
    rec = ctx.record_index.get(key)
    if rec is None:
        return ""
    fmt = str(rec.get("format") or "")
    verdict = ctx.verdict_index.get(key)
    cls = entry_class(verdict) if verdict and "verdict_id" in verdict else None
    chip = '<span class="badge %s">%s</span>' % (cls, esc(VERDICT_LABEL[cls])) if cls else ""
    return ('<figure class="pv-tile" data-ad="%s"><div class="pv-btn" data-open="%s">%s</div>'
            '<figcaption>%s%s</figcaption></figure>'
            % (esc(key), esc(key), _image(ctx, key, rec["label"], fmt), esc(rec["label"]), chip))


def preview_strip(ctx: Ctx, ads: Sequence[Dict[str, Any]], limit: int = STRIP_ADS) -> str:
    return '<div class="pv-grid strip">%s</div>' % "".join(preview_tile(ctx, _ad_key(a)) for a in _by_spend(ads)[:limit])


# ----- Format -----

DERIVED_NOTE = "3-second plays (derived): spend divided by cost per 3-second view, not reported."
UNKNOWN_FORMAT = "unknown"


def _is_derived(rows: Sequence[Dict[str, Any]]) -> bool:
    return any(str(r.get("video_views_3s_source") or "").startswith("derived") for r in rows)


def _ad_rows(ctx: Ctx, ads: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for a in ads for r in ctx.rows_by_ad.get(_ad_key(a), [])]


def _grade_across(values: Dict[str, float], lower_better: bool) -> Dict[str, str]:
    """Plain-word band per format by rank among the formats; equal values share a band and a tie is marked."""
    if len(values) < MIN_FORMATS:
        return {name: NOT_GRADED for name in values}
    scores = {name: round(v, 6) for name, v in values.items()}
    best = min(scores.values()) if lower_better else max(scores.values())
    worst = max(scores.values()) if lower_better else min(scores.values())
    if best == worst:
        return {name: "middle (all tied)" for name in scores}
    out = {}
    for name, score in scores.items():
        if score == best:
            out[name] = "best of your formats" + (" (tied)" if list(scores.values()).count(best) > 1 else "")
        elif score == worst:
            out[name] = "weakest" + (" (tied)" if list(scores.values()).count(worst) > 1 else "")
        else:
            out[name] = "middle"
    return out


def _format_value(ctx: Ctx, key: str, value: Optional[float]) -> str:
    if key == "roas":
        return "%.2fx" % value
    if key in ("cpa", "cpm"):
        return ctx.money(value, 2)
    return "%.2f%%" % value


def _why_missing(total: Dict[str, Optional[float]], metric: str) -> str:
    return interact.plain_ids(_na(cm.describe_missing(total, metric) or "no value"))


def format_scorecard(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    formats = ctx.mix.get("by_format") or []
    if not formats:
        return empty_state("creative-mix read no format from the ad names, so there is nothing to compare.",
                           "Name ads with the convention in creative-context, or tell the creative-mix skill the naming pattern your ads use.")
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ad in ctx.ads:
        groups.setdefault(ad.get("format") or "unknown", []).append(ad)
    cells: Dict[str, Dict[str, Tuple[Optional[float], str]]] = {}
    derived_seen: set = set()
    derived_formats: set = set()
    for row in formats:
        ads, line = groups.get(row["format"], []), {}
        for key, _ in FORMAT_COLUMNS:
            if key in ("roas", "cpa"):
                value = row.get(key)
                reason = _na("no purchase value or purchases") if key == "roas" else _na("no purchases")
            elif not ads:
                value, reason = None, _na("the data file is needed")
            elif key in VIDEO_KPIS:
                used = video_rows(_ad_rows(ctx, ads), key)
                if not used:
                    value, reason = None, _na("not video")
                else:
                    total = totals(used)
                    value = cm.compute_metrics(total)[key]
                    reason = _why_missing(total, key)
                    if value is not None and key == "hook_rate" and _is_derived(used):
                        derived_seen.add(key)
                        derived_formats.add(row["format"])
            else:
                total = totals(ads)
                value = cm.compute_metrics(total)[key]
                reason = _why_missing(total, key)
            line[key] = (value, reason)
        cells[row["format"]] = line
    bands = {}
    for key, _ in FORMAT_COLUMNS:
        values = {name: line[key][0] for name, line in cells.items() if line[key][0] is not None and name != UNKNOWN_FORMAT}
        bands[key] = _grade_across(values, key in LOWER_BETTER)
        if UNKNOWN_FORMAT in cells and cells[UNKNOWN_FORMAT][key][0] is not None:
            bands[key][UNKNOWN_FORMAT] = "not graded: format not known"
    body = []
    for row in formats:
        name, line, ads = row["format"], cells[row["format"]], groups.get(row["format"], [])
        share = "n/a" if row.get("share") is None else "%.1f%%" % row["share"]
        tds = ""
        for key, head in FORMAT_COLUMNS:
            value, reason = line[key]
            grade = ' <span class="grade">%s</span>' % esc(bands[key][name]) if value is not None and name in bands[key] else ""
            if value is not None and key == "hook_rate" and name in derived_formats:
                grade = ' <span class="grade">(derived)</span>' + grade
            tds += '<td class="num" data-label="%s">%s%s</td>' % (esc(head), esc(reason if value is None else _format_value(ctx, key, value)), grade)
        body.append('<tr><td class="fmt-name">%s</td><td class="num" data-label="Ads">%d</td><td class="num" data-label="Spend share">%s</td>%s</tr>'
                    % (esc(_group_name(name, "Format not known")), row["ads"], esc(share), tds))
        body.append('<tr class="strip-row"><td colspan="9">%s</td></tr>' % preview_strip(ctx, ads))
    header = [("Format", False), ("Ads", True), ("Spend share", True)] + [(head, True) for _, head in FORMAT_COLUMNS]
    note = ('<p class="muted">Each format is graded only against your other formats, by rank: equal values share a band and a tie is marked (tied). '
            'It needs %d or more formats with a value, else it reads "not graded". CPM and CPA grade the other way round (lowest is best). '
            'Hook and hold rate count video ads only. ROAS and CPA come from creative-mix; the other rates are ratios of summed counts. '
            'Hook and hold rate use only the days that carry 3-second plays. The strips show each format\'s top %d ads by spend (N=%d). An ad with no format in its name is '
            'listed but never graded.</p>' % (MIN_FORMATS, STRIP_ADS, STRIP_ADS))
    if derived_seen:
        note += '<p class="muted">%s</p>' % esc(DERIVED_NOTE)
    return table(header, body, stack=True) + note, "data"


BENCH_METRICS = (("ctr", "CTR", "pct"), ("cpm", "CPM", "money"), ("roas", "ROAS", "x"), ("cvr", "CR", "pct"), ("hook_rate", "Hook rate", "pct"))
WEEK_TIME_METRICS = (("ctr", "CTR", "pct"), ("cpm", "CPM", "money"), ("roas", "ROAS", "x"), ("hook_rate", "Hook rate", "pct"))
ALL_FORMATS = "All formats"
ALL_FORMATS_COLOUR = "var(--heading)"
NO_FORMATS = ("No format could be read from the ad names, so there is nothing to compare.",
              "Name ads with the convention in creative-context, or tell the creative-mix skill the naming pattern your ads use.")


def _named_formats(ctx: Ctx) -> List[str]:
    return [f for f in ctx.formats_by_spend() if f != UNKNOWN_FORMAT]


def format_benchmarks(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state(*NO_ROWS)
    named = _named_formats(ctx)
    if not named:
        return empty_state(*NO_FORMATS)
    views, skipped = [], []
    for key, name, kind in BENCH_METRICS:
        axis, hover = _kind_formats(ctx, kind)
        rows, reasons, bands = [], {}, []
        for fmt in named:
            used = _measure_rows(ctx.rows_of_format(fmt), key)
            value = _kpi_value(totals(used), key) if used else None
            band, why = benchmarks.lookup(key, fmt, ctx.currency)
            if band:
                bands.append(band)
            else:
                reasons.setdefault(why, []).append(ctx.format_name(fmt))
            rows.append({"name": ctx.format_name(fmt), "value": value, "colour": ctx.colour(fmt), "band": band})
        values = [r["value"] for r in rows if r["value"] is not None]
        chart = charts.benchmark_rows(rows, statistics.median(values) if len(values) > 1 else None, axis,
                                      "%s by format: your value against a public industry figure" % name, _unit_of(ctx, name, kind), tip_fmt=hover)
        if not chart:
            skipped.append(name)
            continue
        ctx.benchmarks_used.extend(bands)
        lines = ["<p class=\"sources\">%s</p>" % esc(benchmarks.citation(b)) for b in {b["url"]: b for b in bands}.values()]
        for why, who in reasons.items():
            lines.append('<p class="sources muted">No industry band for %s: %s.</p>' % (esc(", ".join(who)), esc(why)))
        views.append((key, name, chart + "".join(lines)))
    if not views:
        return empty_state("None of the benchmark measures could be worked out from the data.", "Include impressions, clicks, spend and purchase columns in the export.")
    lead = ('<p class="muted">The dot is your value for each format. The shaded band or tick is a public industry figure, drawn only where a cited source '
            'gives one for that format. Where the source does not state exactly how it measures (for example link clicks or all clicks) the band is drawn '
            'with that caveat printed under it; where its measure differs from ours there is no band. It is context, never a grade: your verdicts compare '
            'your ads with your own ads. %s</p>' % esc(benchmarks.NO_BAND_METRICS["hold_rate"]))
    skip = '<p class="muted">Not shown, no data for it: %s.</p>' % esc(", ".join(skipped)) if skipped else ""
    return lead + charts.switcher("format-benchmarks", views) + skip, "data"


def week_axis(first: dt.date, last: dt.date) -> List[Tuple[dt.date, str]]:
    """Calendar weeks (ISO, so each begins on weekday 0) from the one holding `first` to the one holding `last`: (week start, label); a part week is marked."""
    start = first - dt.timedelta(days=first.weekday())
    out = []
    while start <= last:
        part = (start < first) or (start + dt.timedelta(days=6) > last)
        out.append((start, charts.day_label(max(start, first).isoformat()) + (" (part)" if part else "")))
        start += dt.timedelta(days=7)
    return out


def _week_of(day: str, first: dt.date) -> int:
    d = dt.date.fromisoformat(day)
    return ((d - dt.timedelta(days=d.weekday())) - (first - dt.timedelta(days=first.weekday()))).days // 7


def formats_over_time(ctx: Ctx) -> Tuple[str, str]:
    cal = calendar(ctx.rows)
    if not cal:
        return empty_state(*NO_DATES)
    named = _named_formats(ctx)
    if not named:
        return empty_state(*NO_FORMATS)
    first, last = dt.date.fromisoformat(cal[0][0]), dt.date.fromisoformat(cal[-1][0])
    weeks = week_axis(first, last)
    if len(weeks) < 2:
        return empty_state("The data covers less than two calendar weeks, so there is no weekly trend.", "Pull the data by day over a longer window.")
    labels = [text for _, text in weeks]

    def weekly(rows: Sequence[Dict[str, Any]], key: str) -> List[Optional[float]]:
        buckets: List[List[Dict[str, Any]]] = [[] for _ in weeks]
        for row in rows:
            day = _day(row)
            if day:
                buckets[_week_of(day, first)].append(row)
        out: List[Optional[float]] = []
        for bucket in buckets:
            used = _measure_rows(bucket, key)
            total = totals(used)
            out.append(_kpi_value(total, key) if used and (total.get("impressions") or 0) >= charts.MIN_WEEK_IMPRESSIONS else None)
        return out

    cells = []
    for key, name, kind in WEEK_TIME_METRICS:
        axis, hover = _kind_formats(ctx, kind)
        lines = []
        for fmt in named:
            values = weekly(ctx.rows_of_format(fmt), key)
            if any(v is not None for v in values):
                lines.append({"name": ctx.format_name(fmt), "values": values, "colour": ctx.colour(fmt), "kind": "line"})
        everything = weekly(ctx.rows, key)
        if not lines and not any(v is not None for v in everything):
            continue
        lines.append({"name": ALL_FORMATS, "values": everything, "colour": ALL_FORMATS_COLOUR, "kind": "dashed"})
        chart = charts.line_chart(labels, lines, "%s by week and format" % name, axis, _unit_of(ctx, name, kind), x_text=lambda t: t, width=380, height=240,
                                  legend=False, caption="%s by week" % name, tip_fmt=hover)
        cells.append('<div class="multiple"><h4>%s</h4>%s</div>' % (esc(name), chart))
    if not cells:
        return empty_state("No format has enough impressions in any week to draw a line.", "Pull the data over a longer window or for more spend.")
    key_chips = charts.chips([(ctx.format_name(f), ctx.colour(f)) for f in named] + [(ALL_FORMATS, ALL_FORMATS_COLOUR)])
    note = ('<p class="muted">Weeks are ISO calendar weeks; a part week is marked. A format-week with fewer than {:,} impressions is left off its line '
            '(an arbitrary floor, set it from your own account). The dashed line is every format together. Hook rate counts video ads only.</p>'.format(charts.MIN_WEEK_IMPRESSIONS))
    return '<div class="multiples-wrap" data-scope="1">%s<div class="multiples">%s</div></div>%s' % (key_chips, "".join(cells), note), "data"


def spend_vs_return(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state(*NO_ROWS)
    named = _named_formats(ctx)
    total_spend = sum(ctx.format_spend.values())
    points, colours = [], {}
    for fmt in named:
        total = totals(ctx.rows_of_format(fmt))
        roas, conversions = cm.compute_metrics(total)["roas"], total.get("conversions")
        if roas is None or conversions is None or not total_spend:
            continue
        name = ctx.format_name(fmt)
        points.append(((total["spend"] or 0) / total_spend * 100, roas, conversions, name, True))
        colours[name] = ctx.colour(fmt)
    account = cm.compute_metrics(totals(ctx.rows))["roas"]
    if len(points) < 2 or account is None:
        return empty_state("Fewer than two formats have both spend and purchase value, so there is nothing to set against each other.",
                           "Include the spend, purchases and purchase value columns, and name ads with a format.")
    chart = charts.bubble_chart(points, "Share of spend (%)", "ROAS (x)", "Spend share against return, by format", None, account, (), colours=colours,
                                size_words="purchases",
                                note="Each bubble is a format. Further right takes more of your spend, higher earns more per unit spent. "
                                     "Bubble area is purchases; the dashed line is your account ROAS (%.2fx)." % account)
    return chart, "data"


# ---------- Keep / kill: ad age and launch pace ----------

AGE_EDGES = (7, 16, 33, 66)  # arbitrary default: the age in days at which each new bucket starts; set it from your own account


def age_starts_text() -> str:
    return "%s and %d days" % (", ".join(str(e) for e in AGE_EDGES[:-1]), AGE_EDGES[-1])


def age_labels() -> List[str]:
    edges = (0,) + AGE_EDGES
    return ["%d-%d days" % (edges[i], edges[i + 1] - 1) for i in range(len(AGE_EDGES))] + ["%d+ days" % AGE_EDGES[-1]]


def ad_age(ctx: Ctx) -> Tuple[str, str]:
    ads = [a for a in ctx.ads if a.get("age_days") is not None]
    if not ads:
        return empty_state("No ad has a date, so its age cannot be worked out.", "Pull the data by day (a day column), ideally with each ad's creation time.")
    labels = age_labels()
    groups: List[List[Dict[str, Any]]] = [[] for _ in labels]
    for ad in ads:
        groups[sum(1 for edge in AGE_EDGES if ad["age_days"] >= edge)].append(ad)
    total = sum(a.get("spend") or 0 for a in ads)
    shares = [sum(a.get("spend") or 0 for a in g) / total * 100 if total and g else 0.0 for g in groups]
    counts = [len(g) for g in groups]
    metrics = [(key, name, kind, [cm.compute_metrics(totals(_ad_rows(ctx, g)))[key] if g else None for g in groups])
               for key, name, kind in (("roas", "ROAS", "x"), ("ctr", "CTR", "pct"))]
    views = []
    for key, name, kind, values in metrics:
        if any(v is not None for v in values):
            views.append((key, name, charts.bars_with_dots(labels, shares, counts, values, _kind_formats(ctx, kind)[0], name,
                                                          "Spend share and %s by ad age" % name, dot_tip_fmt=_kind_formats(ctx, kind)[1])))
    if not views:
        views = [("roas", "ROAS", charts.bars_with_dots(labels, shares, counts, [None] * len(labels), charts.axis_format("x"), "ROAS", "Spend share by ad age"))]
    bases = {a.get("age_basis") for a in ads}
    basis = ("from each ad's creation date" if bases == {cm.AGE_FROM_CREATED} else
             "from each ad's first day of delivery in this window, so an ad that started before the window reads younger than it is" if bases == {cm.AGE_FROM_DELIVERY} else
             "from the creation date where the export has one, otherwise from the first day of delivery in this window")
    note = ('<p class="muted">Age is counted to the last day of the data, %s. Arbitrary defaults: new buckets start at %s. '
            'ROAS and CTR are ratios of summed counts for the ads in a bucket; a bucket with fewer than %d ads is dimmed.</p>' % (basis, age_starts_text(), charts.MIN_BUCKET_ADS))
    return charts.switcher("ad-age", views) + note, "data"


def launches(ctx: Ctx) -> Tuple[str, str]:
    dated = [a for a in ctx.ads if a.get("first_date")]
    if not dated:
        return empty_state("No ad has a date, so there is no launch week to count.", "Pull the data by day (a day column).")
    first, last = dt.date.fromisoformat(min(a["first_date"] for a in dated)), dt.date.fromisoformat(max(a["last_date"] for a in dated))
    weeks = week_axis(first, last)
    series = []
    for fmt in ctx.formats_by_spend():
        counts = [0] * len(weeks)
        for ad in dated:
            if (ad.get("format") or UNKNOWN_FORMAT) == fmt:
                counts[_week_of(ad["first_date"], first)] += 1
        if any(counts):
            series.append((ctx.format_name(fmt), counts, ctx.colour(fmt)))
    average = len(dated) / len(weeks)
    chart = charts.stacked_bars([text for _, text in weeks], series, "New ads launched per week, by format", "New ads",
                                "On average %.1f new ads a week over %d week%s. An ad counts in the week it first delivered; ads already running at the start of the data fall in its first week."
                                % (average, len(weeks), "" if len(weeks) == 1 else "s"))
    return chart, "data"


def _video_rates(ctx: Ctx, ad: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], bool]:
    """Hook and hold rate of one ad from its days that carry the plays, and whether those plays were derived."""
    rows = ctx.rows_by_ad.get(_ad_key(ad), [])
    hook_rows, hold_rows = video_rows(rows, "hook_rate"), video_rows(rows, "hold_rate")
    hook = cm.compute_metrics(totals(hook_rows))["hook_rate"] if hook_rows else None
    hold = cm.compute_metrics(totals(hold_rows))["hold_rate"] if hold_rows else None
    return hook, hold, _is_derived(hook_rows)


def video_hook_hold(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.ads:
        return empty_state(*NO_ROWS)
    points, derived = [], 0
    for ad in ctx.ads:
        if not ad.get("spend"):
            continue
        hook, hold, was_derived = _video_rates(ctx, ad)
        if hook is not None and hold is not None:
            points.append((hook, hold, ad["spend"], readable_label(ad, ad.get("ad_name"), ad.get("ad_id")), ad))
            derived += was_derived
    if len(points) < 2:
        return empty_state("Fewer than two video ads have both a hook rate and a hold rate, so there is nothing to compare.",
                           "Include the 3-second video plays and ThruPlays columns in the export or connector pull.")
    hook_med, hold_med = charts._median([p[0] for p in points]), charts._median([p[1] for p in points])
    labelled = {id(p[4]) for p in sorted(points, key=lambda p: -p[2])[:ctx.top_n]}
    chart = charts.bubble_chart([(h, d, s, n, id(ad) in labelled) for h, d, s, n, ad in points], "Hook rate (%)", "Hold rate (%)",
                                "Video ads: hook rate against hold rate", hook_med, hold_med, QUADRANTS)
    counts = {name: 0 for name in QUADRANTS}
    for hook, hold, _, _, _ in points:
        high_hook, high_hold = hook >= hook_med, hold >= hold_med
        counts[QUADRANTS[1] if high_hook and high_hold else QUADRANTS[3] if high_hook else QUADRANTS[0] if high_hold else QUADRANTS[2]] += 1
    legend = '<ul class="quadrant-list">%s</ul>' % "".join("<li><b>%s</b>: %d ad%s</li>" % (esc(n), c, "" if c == 1 else "s") for n, c in counts.items())
    note = ('<p class="muted">The dashed lines are your own median hook rate (%.2f%%) and hold rate (%.2f%%) across these %d video ads; '
            'an ad on a line counts as high. The %d biggest spenders are named where there is room (N=%d, a default you can change when you rebuild the report); hover any bubble for its name.</p>'
            % (hook_med, hold_med, len(points), min(ctx.top_n, len(points)), ctx.top_n))
    if derived:
        note += '<p class="muted">%s It applies to %d of these ads.</p>' % (esc(DERIVED_NOTE), derived)
    return chart + legend + note, "data"


def _clock_or_na(seconds: Optional[float]) -> str:
    return "n/a (no length column in the data)" if seconds is None else clock(seconds)


def video_retention(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.rows:
        return empty_state(*NO_ROWS)
    headers = {step: _find_header(ctx, aliases) for step, _, _, aliases in RETENTION_STEPS}
    ctx.retention_headers = dict(headers, average=_find_header(ctx, AVERAGE_TIME))
    missing = [shown for step, _, shown, _ in RETENTION_STEPS if not headers[step]]
    if missing:
        return empty_state("No column was found for: %s." % ", ".join(missing),
                           "In Ads Manager add the video quartile columns (plays at 25, 50, 75, 95 and 100 percent), and Video average play time if you can, then export again.")
    chosen: List[Tuple[Dict[str, Any], List[float]]] = []
    left_out = 0
    for ad in _by_spend(ctx.ads):
        full = [r for r in ctx.rows_by_ad.get(_ad_key(ad), [])
                if r.get("video_views_3s") is not None and all(cm._list_value(r.get(headers[step])) is not None for step, _, _, _ in RETENTION_STEPS)]
        if not full:
            continue
        if _is_derived(full):
            left_out += 1
            continue
        counts = [sum(r["video_views_3s"] for r in full)] + [sum(cm._list_value(r.get(headers[step])) for r in full) for step, _, _, _ in RETENTION_STEPS]
        chosen.append((ad, counts))
        if len(chosen) == RETENTION_ADS:
            break
    if not chosen:
        if left_out:
            return empty_state("Every video ad with quartile counts has derived 3-second plays (spend divided by cost per 3-second view), and this chart shows raw counts only.",
                               "Pull 3-second video plays as a reported column (Ads Manager export) instead of deriving them.")
        return empty_state("The quartile columns are in the data, but no video ad has a count in all five.",
                           "Check that the export has values in the Video plays at 25% to 100% columns for video ads.")
    labels = [readable_label(ad, ad.get("ad_name"), ad.get("ad_id")) for ad, _ in chosen]
    labels = [l if labels.count(l) == 1 else "%s (%s)" % (l, _ad_key(ad)) for l, (ad, _) in zip(labels, chosen)]
    chart = charts.retention_chart(list(zip(labels, [c for _, c in chosen])), ["3-second plays"] + [s for _, s, _, _ in RETENTION_STEPS],
                                   "People still watching (count)", "Video retention: people still watching, top video ads by spend")
    avg_header = ctx.retention_headers["average"]
    rows_html = []
    for (ad, _), label in zip(chosen, labels):
        if avg_header is None:
            watch = _na("no average play time column in the data")
        else:
            pairs = [(cm._list_value(r.get(avg_header)), r.get("video_views_3s")) for r in ctx.rows_by_ad.get(_ad_key(ad), [])]
            weighted = [(t, w) for t, w in pairs if t is not None and w]
            watch = ("%.1f s" % (sum(t * w for t, w in weighted) / sum(w for _, w in weighted))) if weighted else _na("no values")
        rows_html.append((label, watch, _clock_or_na(ctx.video_lengths.get(_ad_key(ad)))))
    rises = any(later > earlier for _, c in chosen for earlier, later in zip(c, c[1:]))
    note = ('<p class="muted">The lines are raw counts of people (plays at each point), summed over the days that carry all five counts. Average watch '
            'time is weighted by 3-second plays across days. The top %d video ads by spend with all five counts are shown (N=%d).%s%s</p>'
            % (RETENTION_ADS, RETENTION_ADS,
               " On short videos the 25% point comes before the 3-second mark, so the line can rise." if rises else "",
               " %d ad%s with derived 3-second plays left out." % (left_out, "" if left_out == 1 else "s") if left_out else ""))
    return chart + _table_of(rows_html, [("Ad", False), ("Average watch time", True), ("Video length", True)]) + note, "data"


def ad_type_split(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    types = ctx.mix.get("by_type") or []
    if not types:
        return empty_state("creative-mix read no ad type from the ad names, so there is nothing to split.",
                           "Name each ad with one of the six ad types (see creative-context, ad-types) and run creative-mix again.")
    blocks = []
    for row in types:
        name = row["ad_type"]
        roas = _na("no purchase value") if row.get("roas") is None else "%.2fx" % row["roas"]
        cpa = _na("no purchases") if row.get("cpa") is None else ctx.money(row["cpa"], 2)
        stats = '<p class="type-stats">%d ads &middot; %s spend &middot; %s of spend &middot; ROAS %s &middot; CPA %s</p>' % (
            row["ads"], esc(ctx.money(row["spend"])), "n/a" if row.get("share") is None else "%.1f%%" % row["share"], esc(roas), esc(cpa))
        mine = [a for a in ctx.ads if (a.get("ad_type") or "unknown") == name]
        inside = ""
        if mine:
            spend = sum(a.get("spend") or 0 for a in mine)
            by_format: Dict[str, List[Dict[str, Any]]] = {}
            for ad in mine:
                by_format.setdefault(ad.get("format") or "unknown", []).append(ad)
            lines = []
            for fmt, group in sorted(by_format.items(), key=lambda kv: -sum(a.get("spend") or 0 for a in kv[1])):
                part = sum(a.get("spend") or 0 for a in group)
                lines.append((_group_name(fmt, "Format not known"), str(len(group)), ctx.money(part), "n/a" if not spend else "%.1f%%" % (part / spend * 100)))
            inside = _table_of(lines, [("Format inside this type", False), ("Ads", True), ("Spend", True), ("Share of this type's spend", True)])
        else:
            inside = '<p class="muted">The format mix needs the daily data file.</p>'
        blocks.append('<section class="type-block"><h4>%s</h4>%s%s</section>' % (esc(_group_name(name, "Type not known")), stats, inside))
    note = ""
    if ctx.mix.get("unknown_types"):
        note = ('<p class="muted">Ad types not in the standard list (%s): %s. They are kept as written and counted. Name each one as one of %s '
                '(creative-context, ad-types) and run creative-mix again.</p>'
                % (esc(", ".join(cm.AD_TYPES)), esc(", ".join(ctx.mix["unknown_types"])), esc(", ".join(cm.AD_TYPES))))
    lead = '<p class="muted">Each ad type has its own block: promo and always-on ads do different jobs, so they are never added together.</p>'
    return lead + "".join(blocks) + note, "data"


# ----- White space -----

def _gap_cells(ctx: Ctx, rows: Sequence[str]) -> Dict[Tuple[int, int], int]:
    grid = ctx.mix["grid"]
    out = {}
    for (concept, fmt), number in ctx.gap_numbers.items():
        if concept in rows and fmt in grid["formats"]:
            out[(rows.index(concept), grid["formats"].index(fmt))] = number
    return out


def concept_heatmap(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    grid = ctx.mix.get("grid") or {}
    families, formats = grid.get("families") or [], grid.get("formats") or []
    if not families or not formats:
        return empty_state("creative-mix read no concept and format from the ad names, so there is no grid.",
                           "Name ads with the convention in creative-context, or tell the creative-mix skill the naming pattern your ads use.")
    shown = families[:HEATMAP_CONCEPTS]
    cells = [[(grid["cells"][i][f]["ads"], grid["cells"][i][f]["spend"]) for f in formats] for i in range(len(shown))]
    chart = charts.heatmap([_plain(c) for c in shown], [_group_name(f, "Format not known") for f in formats], cells,
                           _gap_cells(ctx, shown), "Concept by format: ads and spend", "cf", ctx.currency or "account currency")
    hidden = len(families) - len(shown)
    lines = ["Showing the top %d of %d concepts by spend (an arbitrary display cap)%s." % (
        len(shown), len(families), "; %d hidden" % hidden if hidden else "")]
    off = sum(1 for g in ctx.gaps if g["concept"] not in shown)
    if off:
        lines.append("%d gap%s involve%s concepts that are not shown here; they are in the gap list below." % (off, "" if off == 1 else "s", "s" if off == 1 else ""))
    return chart + '<p class="muted">%s</p>' % esc(" ".join(lines)), "data"


def stage_heatmap(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    stages = [s["stage"] for s in ctx.mix.get("by_stage") or []]
    if not stages:
        return empty_state("Your ad names do not carry a funnel stage: add one (see the naming guide in creative-context).",
                           "Add a funnel stage to each ad name (for example STAGE:tof), then run creative-mix again.")
    if not ctx.ads:
        return empty_state(*NO_ROWS)
    family_of = {}
    for row in ctx.mix.get("by_concept") or []:
        for ad_id in row.get("ad_ids") or []:
            family_of[str(ad_id)] = row["concept"]
    found: Dict[Tuple[str, str], List[float]] = {}
    for ad in ctx.ads:
        family, stage = family_of.get(_ad_key(ad)), ad.get("funnel_stage")
        if family and stage in stages:
            cell = found.setdefault((family, stage), [0, 0.0])
            cell[0] += 1
            cell[1] += ad.get("spend") or 0
    concepts = sorted({f for f, _ in found}, key=lambda f: -sum(v[1] for (c, _), v in found.items() if c == f))
    if not concepts:
        return empty_state("No ad has both a concept and a funnel stage that creative-mix recognised.", "Name ads with the convention in creative-context and run creative-mix again.")
    shown = concepts[:HEATMAP_CONCEPTS]
    cells = [[tuple(found.get((c, s), (0, 0.0))) for s in stages] for c in shown]
    chart = charts.heatmap([_plain(c) for c in shown], stages, cells, {}, "Concept by funnel stage: ads and spend", "fs", ctx.currency or "account currency")
    hidden = len(concepts) - len(shown)
    note = "Showing the top %d of %d concepts by spend (an arbitrary display cap)%s. Stages are shown as written in the ad names." % (
        len(shown), len(concepts), "; %d hidden" % hidden if hidden else "")
    return chart + '<p class="muted">%s</p>' % esc(note), "data"


def no_creative_types(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    if not ctx.mix.get("by_type"):
        return empty_state("creative-mix read no ad type from the ad names, so it cannot say which types have no creative.",
                           "Name each ad with one of the six ad types (see creative-context, ad-types) and run creative-mix again.")
    present = {t["ad_type"] for t in ctx.mix["by_type"]}
    missing = [t for t in cm.AD_TYPES if t not in present]
    if not missing:
        return '<p class="lead">Every ad type has at least one ad in this window.</p>', "data"
    chips = "".join('<li class="tag" data-type="%s"><b>%s</b> %s</li>' % (esc(t), esc(_plain(t)), esc(TYPE_NOTES[t])) for t in missing)
    return ('<p class="lead">%d of the six ad types have no ad in this window.</p><ul class="tags">%s</ul>'
            '<p class="muted">An empty type is not always a problem: it is only a prompt to ask whether you meant to leave it.</p>' % (len(missing), chips)), "data"


def _sum_field(rows: Sequence[Dict[str, Any]], field: str) -> Optional[float]:
    seen = [r[field] for r in rows if r.get(field) is not None]
    return sum(seen) if seen else None


def _segment_line(ctx: Ctx, name: str, spend: Optional[float], conv: Optional[float], value: Optional[float], total: Optional[float]) -> List[str]:
    roas = interact.ratio_text(value, spend, "purchase value", "spend")
    cpa = interact.ratio_text(spend, conv, "spend", "purchases")
    return [name, ctx.money(spend), "n/a" if not total or spend is None else "%.1f%%" % (spend / total * 100),
            roas or "%.2fx" % (value / spend), cpa or ctx.money(spend / conv, 2)]


def segments(ctx: Ctx) -> Tuple[str, str]:
    parts = []
    markets = [m for m in interact.group_subtotals(ctx.records, "market", None, ctx.money) if m["key"] is not None]
    if markets:
        body = []
        for m in markets:
            thin = ' <span class="grade">thin coverage (fewer than %d ads)</span>' % cm.MIN_GROUP if m["ads"] < cm.MIN_GROUP else ""
            body.append('<tr><td><span class="seg-name">%s</span>%s</td><td class="num" data-label="Ads">%d</td><td class="num" data-label="Spend share">%s</td>'
                        '<td class="num" data-label="ROAS">%s</td></tr>'
                        % (esc(m["label"]), thin, m["ads"], "n/a" if m["share"] is None else "%.1f%%" % m["share"], esc(m["roas_text"])))
        parts.append("<h4>Markets</h4>" + table([("Market", False), ("Ads", True), ("Spend share", True), ("ROAS", True)], body, stack=True)
                     + '<p class="muted">Markets come from the ad names. Spend share is of all spend in the data.</p>')
    ctx.breakdown_dims = {}
    if ctx.breakdowns:
        for alias, name in BREAKDOWN_DIMENSIONS:
            header = next((str(k) for r in ctx.breakdowns for k in r if re.sub(r"[^a-z0-9]", "", str(k).lower()) == alias), None)
            if header is None or name in ctx.breakdown_dims:
                continue
            ctx.breakdown_dims[name] = header
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in ctx.breakdowns:
                groups.setdefault(str(r.get(header) or "not stated"), []).append(r)
            total = _sum_field(ctx.breakdowns, "spend")
            lines = [_segment_line(ctx, value, _sum_field(rs, "spend"), _sum_field(rs, "conversions"), _sum_field(rs, "conversion_value"), total)
                     for value, rs in sorted(groups.items(), key=lambda kv: -(_sum_field(kv[1], "spend") or 0))]
            parts.append("<h4>%s</h4>%s" % (esc(name), _table_of(lines, [(name, False), ("Spend", True), ("Spend share", True), ("ROAS", True), ("CPA", True)])))
        if ctx.breakdown_dims:
            parts.append('<p class="muted">Each segment adds its own spend, purchases and purchase value, then divides: ROAS and CPA are ratios of sums, never an average of ratios.</p>')
        else:
            parts.append('<p class="muted">The breakdown file has no age, gender, placement, platform, region or country column.</p>')
    elif markets:
        parts.append('<p class="muted">Meta\'s connector returns no age, gender or placement breakdowns: export one from Ads Manager '
                     '(recipe in creative-context) and add it when you rebuild this report.</p>')
    if not markets and not ctx.breakdown_dims:
        return empty_state("The ad names carry no market and no breakdown file was given, so there are no segments to show.",
                           "Meta's connector returns no age, gender or placement breakdowns: export one from Ads Manager (recipe in creative-context) and add it when you rebuild this report.")
    return "".join(parts), "data"


def gap_reason(ctx: Ctx, gap: Dict[str, Any]) -> str:
    """Why test this, in plain words: which neighbour is strong (with its spend and ROAS) and what the cell lacks."""
    fmt = next((r for r in ctx.mix["by_format"] if r["format"] == gap["format"]), None)
    con = next((r for r in ctx.mix["by_concept"] if r["concept"] == gap["concept"]), None)

    def strong(kind: str, name: str, row: Optional[Dict[str, Any]]) -> str:
        roas = "ROAS n/a" if not row or row.get("roas") is None else "ROAS %.2fx" % row["roas"]
        spend = ctx.money(row["spend"]) + " spend" if row else "spend n/a"
        return "%s is in the top quarter of your %ss on ROAS (%s, %s)" % (_plain(name), kind, spend, roas)

    said = []
    if "top format" in gap["why"]:
        said.append(strong("format", gap["format"], fmt))
    if "top concept" in gap["why"]:
        said.append(strong("concept", gap["concept"], con))
    lack = "has no ad in it yet" if gap["ads"] == 0 else "has one ad in it"
    return "%s, and %s in %s %s." % (" and ".join(said), _plain(gap["concept"]), _plain(gap["format"]), lack)


def gap_list(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    if not ctx.gaps:
        return empty_state("creative-mix found no gap worth testing: no empty or single-ad cell sits beside a proven top-quarter concept or format.",
                           "Widen the window, lower the minimum proven spend in creative-mix, or add more concepts and formats to compare.")

    def item(number: int, gap: Dict[str, Any]) -> str:
        return ('<li class="gap" data-gap="%d"><b>#%d %s</b><p>%s</p></li>'
                % (number, number, esc(briefing.gap_label(_plain(gap["concept"]), _plain(gap["format"]))), esc(gap_reason(ctx, gap))))
    items = [item(n, g) for n, g in enumerate(ctx.gaps, 1)]
    rest = ""
    if len(items) > ctx.top_n:
        rest = '<details class="rest"><summary>%d more gaps</summary><ol class="gaps" start="%d">%s</ol></details>' % (
            len(items) - ctx.top_n, ctx.top_n + 1, "".join(items[ctx.top_n:]))
    lead = ('<p class="lead">%d gap%s worth testing, strongest first. A hypothesis to test, not a result.</p>' % (len(items), "" if len(items) == 1 else "s"))
    floor = ctx.mix.get("min_proven_spend")
    note = ('<p class="muted">A gap is an empty or single-ad cell beside a concept or format in the top quarter of your own ROAS, with at least %s of always-on '
            'spend behind it (an arbitrary default, set in creative-mix). The top %d show here (N=%d); the numbers match the outlines on the heatmap.</p>'
            % (esc(ctx.money(floor)) if floor is not None else "the proven spend", ctx.top_n, ctx.top_n))
    return lead + '<ol class="gaps">%s</ol>%s%s' % ("".join(items[:ctx.top_n]), rest, note), "data"


# ----- Briefing -----

def _neighbour_ads(ctx: Ctx, gap: Dict[str, Any]) -> List[Dict[str, Any]]:
    pools = []
    con = next((r for r in ctx.mix["by_concept"] if r["concept"] == gap["concept"]), None)
    if "top concept" in gap["why"] and con:
        ids = set(str(i) for i in con.get("ad_ids") or [])
        pools.append([a for a in ctx.ads if _ad_key(a) in ids])
    if "top format" in gap["why"]:
        pools.append([a for a in ctx.ads if (a.get("format") or "unknown") == gap["format"]])
    chosen: List[Dict[str, Any]] = []
    for pool in pools:
        for ad in _by_spend(pool)[:2]:
            if ad not in chosen:
                chosen.append(ad)
    return chosen[:STRIP_ADS]


def _judged_on(ctx: Ctx, entry: Optional[Dict[str, Any]] = None) -> str:
    bases = [entry["payback_basis"]] if entry and entry.get("payback_basis") else list(dict.fromkeys(
        e["payback_basis"] for e in (ctx.verdicts or {}).get("ads") or [] if e.get("payback_basis")))
    if not bases:
        return "n/a (no keep-or-kill verdicts were supplied): judge it on the objective you set in the brief, against your own similar ads."
    return "%s, against your own similar ads." % "; ".join(bases)


def _starters(ctx: Ctx) -> List[Dict[str, Any]]:
    out = []
    if ctx.mix:
        for gap in ctx.gaps[:briefing.STARTER_GAPS]:
            beside = " and ".join("one of the account's best %ss (%s)" % (kind, _plain(gap[kind]))
                                  for kind in ("format", "concept") if "top %s" % kind in gap["why"])
            plain = "it sits beside %s with %s of its own" % (beside, "no ad" if gap["ads"] == 0 else "only one ad")
            reason = gap_reason(ctx, gap)
            subject = briefing.gap_label(_plain(gap["concept"]), _plain(gap["format"]))
            out.append({"title": "Test " + subject, "make": subject, "why": reason, "refs": [_ad_key(a) for a in _neighbour_ads(ctx, gap)],
                        "judged": _judged_on(ctx), "prompt": briefing.starter_prompt(subject, plain + ".")})
    iterate = sorted((e for e in (ctx.verdicts or {}).get("ads") or [] if e.get("verdict_id") == "iterate"), key=lambda e: -_stake(e))
    for entry in iterate[:briefing.STARTER_ITERATE]:
        key = str(entry.get("ad"))
        rec = ctx.record_index.get(key)
        label = rec["label"] if rec else str(entry.get("ad_name") or key)
        fix = interact.improvement(ctx.grade_index.get(key), entry)
        why = " ".join(t for t in (fix["lead"], fix["fix"]) if t) or "Marked Iterate by keep-or-kill."
        out.append({"title": "A new version of " + label, "make": "A new version of %s, keeping the concept." % label, "why": why, "refs": [key],
                    "judged": _judged_on(ctx, entry), "prompt": briefing.starter_prompt("a new version of %s, keeping the concept" % label, why)})
    return out


def _refs_html(ctx: Ctx, ids: Sequence[str]) -> str:
    tiles = [preview_tile(ctx, i) for i in ids if str(i) in ctx.record_index]
    unknown = ['<li>%s (ad not in this data)</li>' % esc(i) for i in ids if str(i) not in ctx.record_index]
    return ('<div class="pv-grid strip">%s</div>' % "".join(tiles) if tiles else "") + ('<ul class="plain">%s</ul>' % "".join(unknown) if unknown else "")


def _dl(pairs: Sequence[Tuple[str, str]]) -> str:
    return '<dl class="brief-dl">%s</dl>' % "".join("<dt>%s</dt><dd>%s</dd>" % (esc(k), v) for k, v in pairs)


def _starter_card(ctx: Ctx, number: int, s: Dict[str, Any]) -> str:
    return ('<article class="brief-card"><p class="eyebrow">Brief starter %d</p><h4>%s</h4>%s'
            '<p class="hooks-note">%s. The prompt below asks for them.</p>'
            '<div class="prompt-scope"><details><summary>Show the prompt</summary><pre class="prompt">%s</pre></details>'
            '<button type="button" class="btn" data-action="copy-prompt">Write the full brief</button></div></article>'
            % (number, esc(s["title"]), _dl([("What to make", esc(s["make"])), ("Why", esc(s["why"])),
                                              ("Reference ads", _refs_html(ctx, s["refs"]) or "n/a (no neighbouring ad found)"),
                                              ("How it will be judged", esc(s["judged"]))]),
               esc(briefing.HOOKS_PLACEHOLDER), esc(s["prompt"])))


def _brief_card(ctx: Ctx, number: int, b: Dict[str, Any]) -> str:
    hooks = '<ul class="plain">%s</ul>' % "".join("<li>%s</li>" % esc(h) for h in b["hooks"]) if b["hooks"] else esc(briefing.NOT_STATED)
    judged = ('<ul class="plain">%s</ul>' % "".join("<li>%s</li>" % (esc(interact.metric_label(m["id"])) if m["defined"] else esc("%s (not a defined metric)" % m["id"]))
                                                     for m in b["judged_by"])) if b["judged_by"] else esc(briefing.NOT_STATED)
    refs = _refs_html(ctx, b["reference_ads"]) or esc(briefing.NOT_STATED)
    return ('<article class="brief-card"><p class="eyebrow">Brief %d</p><h4>%s</h4>%s</article>'
            % (number, esc(b["title"]), _dl([("Objective", esc(b["objective"])), ("Persona", esc(b["persona"])), ("Stage", esc(b["stage"])),
                                              ("Message", esc(b["message"])), ("Hook options", hooks), ("Format", esc(b["format"])),
                                              ("Specs", esc(b["specs"])), ("Reference ads", refs), ("How it will be judged", judged)])))


def ready_briefs(ctx: Ctx) -> Tuple[str, str]:
    if ctx.briefs:
        cards = "".join(_brief_card(ctx, n, b) for n, b in enumerate(ctx.briefs, 1))
        return ('<p class="muted">%d brief%s from the briefs file. Anything the file left out reads "not stated".</p><div class="brief-grid">%s</div>'
                % (len(ctx.briefs), "" if len(ctx.briefs) == 1 else "s", cards)), "data"
    starters = _starters(ctx)
    if not starters:
        return empty_state("No briefs file was given, and there are no coverage gaps or Iterate ads to build starters from.",
                           "Write briefs with the creative-brief and hook-writer skills and add them when you rebuild this report, or run the creative-mix and keep-or-kill skills and add their results.")
    note = ('<p class="muted">Brief starters, not finished briefs: the top %d gaps and the top %d Iterate ads by spend at stake (arbitrary defaults). '
            'A starter never invents a hook or a message; the button copies a prompt for the creative-brief and hook-writer skills. '
            'To show finished briefs here, write them with those skills and add them when you rebuild this report.</p>' % (briefing.STARTER_GAPS, briefing.STARTER_ITERATE))
    return note + '<div class="brief-grid">%s</div>' % "".join(_starter_card(ctx, n, s) for n, s in enumerate(starters, 1)), "data"


def _opening_line(text: str) -> str:
    line = next((l.strip() for l in str(text).splitlines() if l.strip()), "")
    if len(line) <= OPENING_CHARS:
        return line
    return (line[:OPENING_CHARS].rsplit(" ", 1)[0] or line[:OPENING_CHARS]).rstrip(" ,.;:-") + "..."


def copy_cta(ctx: Ctx) -> Tuple[str, str]:
    empty = ("Copy comes back only for classic creatives; flexible and dynamic creatives return none. "
             "Pass a CSV export with the Primary text and Headline columns to fill this.")
    ctx.copy_headers = {name: _find_header(ctx, aliases) for name, aliases in COPY_COLUMNS}
    values = {name: {_ad_key(a): a.get(cm._snake(h)) for a in ctx.ads} for name, h in ctx.copy_headers.items() if h}
    if not any(any(v for v in per.values()) for per in values.values()):
        return empty_state("The data carries no ad copy: no primary text, headline or call-to-action column has a value.", empty)
    parts = []
    cta = values.get("call to action") or {}
    if any(cta.values()):
        total = sum(r.get("spend") or 0 for r in ctx.records)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for key, value in cta.items():
            if value and key in ctx.record_index:
                groups.setdefault(value, []).append(ctx.record_index[key])
        lines = []
        for value, recs in sorted(groups.items(), key=lambda kv: -sum(r.get("spend") or 0 for r in kv[1])):
            t = interact.totals_of(recs, total, ctx.money)
            lines.append([_plain(value), str(t["ads"]), "n/a" if t["share"] is None else "%.1f%%" % t["share"], t["roas_text"]])
        parts.append("<h4>Calls to action</h4>" + _table_of(lines, [("Call to action", False), ("Ads", True), ("Spend share", True), ("ROAS", True)]))
    else:
        parts.append('<p class="muted">%s</p>' % esc(_na("no call-to-action column in the data")))
    body = values.get("primary text") or {}
    if any(body.values()):
        rows_html = []
        for ad in _by_spend([a for a in ctx.ads if body.get(_ad_key(a))])[:COPY_ADS]:
            key = _ad_key(ad)
            rec = ctx.record_index[key]
            verdict = ctx.verdict_index.get(key)
            cls = entry_class(verdict) if verdict and "verdict_id" in verdict else None
            chip = '<span class="badge %s">%s</span>' % (cls, esc(VERDICT_LABEL[cls])) if cls else ""
            rows_html.append('<tr data-ad="%s"><td class="adname">%s<small>Ad ID %s</small></td><td data-label="Opening line">%s</td><td>%s</td></tr>'
                             % (esc(key), esc(rec["label"]), esc(key), esc(_opening_line(body[key])), chip))
        parts.append("<h4>Opening line of the top ads</h4>" + table([("Ad", False), ("Opening line", False), ("Verdict", False)], rows_html, stack=True)
                     + '<p class="muted">The first line of each ad\'s primary text, for the top %d ads by spend (N=%d, an arbitrary default).</p>' % (COPY_ADS, COPY_ADS))
    else:
        parts.append('<p class="muted">%s</p>' % esc(_na("no primary text column in the data")))
    return "".join(parts), "data"


def prompts_panel(ctx: Ctx) -> Tuple[str, str]:
    if not ctx.mix:
        return empty_state(*NO_MIX)
    concepts, formats = list(ctx.mix.get("top_concepts") or []), list(ctx.mix.get("top_formats") or [])
    gaps = [briefing.gap_label(g["concept"], g["format"]) for g in ctx.gaps[:briefing.STARTER_GAPS]]
    blocks = (("creative-ideation", "New concepts that fit the gaps", briefing.ideation_prompt(concepts, formats, gaps)),
              ("hook-writer", "Hook options for the gaps", briefing.hook_prompt(concepts, gaps)),
              ("creative-brief", "A full brief for the first gap", briefing.brief_prompt(gaps, formats)))
    cards = "".join('<div class="prompt-scope"><h4>%s</h4><p class="muted">%s. Copy it into your agent.</p>'
                    '<details><summary>Show the prompt</summary><pre class="prompt">%s</pre></details>'
                    '<button type="button" class="btn" data-action="copy-prompt">Copy prompt</button></div>' % (esc(skill), esc(what), esc(text))
                    for skill, what, text in blocks)
    note = '<p class="muted">The prompts carry the names of your top concepts, top formats and first gaps, and no figures from your data.</p>'
    return note + '<div class="prompt-grid">%s</div>' % cards, "data"


# (tab id, tab title, ((panel id, eyebrow, heading, function), ...)): the order is part of the spec.
CHANGES_SHOWN = 9  # moves listed before the rest collapse; arbitrary display cap


def _run_label(changes: Dict[str, Any]) -> str:
    """"on 2026-03-30 at 09:30" from the previous run's ISO time; the folder name when it has none."""
    made = str(changes.get("previous_at") or "")
    return "on %s at %s" % (made[:10], made[11:16]) if len(made) >= 16 else str(changes.get("previous_run", ""))


def changes_panel(changes: Optional[Dict[str, Any]]) -> str:
    """"What changed since last time", the card at the top of Overview; empty when no --changes file was given."""
    if changes is None:
        return ""
    if changes.get("first_run"):
        inner = '<div class="empty"><p>%s</p></div>' % esc("First review of this account: next time this shows what changed.")
        state = "empty"
    elif changes.get("not_compared"):
        inner = '<div class="empty"><p>%s</p></div>' % esc(changes["not_compared"])
        state = "empty"
    else:
        state = "data"
        account = "".join("<li>%s</li>" % say(m.get("sentence")) for m in changes.get("account") or [])
        moves = changes.get("ads") or []
        ad_items = ["<li>%s</li>" % say(m.get("sentence")) for m in moves]
        shown = "".join(ad_items[:CHANGES_SHOWN])
        more = ""
        if len(ad_items) > CHANGES_SHOWN:
            more = "<details><summary>%d more</summary><ul>%s</ul></details>" % (len(ad_items) - CHANGES_SHOWN, "".join(ad_items[CHANGES_SHOWN:]))
        ads = ("<ul>%s</ul>%s" % (shown, more)) if moves else "<p>No ad changed its verdict, and no ad came or went.</p>"
        inner = '<p class="note">Compared with the review run %s.</p><ul>%s</ul>%s' % (esc(_run_label(changes)), account, ads)
    return ('<section class="card panel" id="panel-changes" data-state="%s"><p class="eyebrow">Overview</p>'
            '<h3>What changed since last time</h3>%s</section>' % (state, inner))


TABS = (
    ("overview", "Overview analysis", (
        ("kpis", "Overview", "Key numbers", kpi_strip),
        ("time", "Overview", "Performance over time", over_time),
        ("money-by-format", "Overview", "Where the money went, by format", spend_by_format),
        ("do-first", "Overview", "Do these first", do_first),
        ("improve", "Overview", "Ways to improve", ways_to_improve),
        ("funnel", "Overview", "Funnel", funnel))),
    ("pareto", "Pareto", (
        ("pareto", "Pareto", "Where the value comes from", pareto),
        ("head-tail", "Pareto", "The head and the long tail", head_tail))),
    ("keep-kill", "Keep / kill", (
        ("board", "Keep / kill", "Verdict board", verdict_board),
        ("fatigue", "Keep / kill", "Fatigue", fatigue),
        ("ad-age", "Keep / kill", "Performance by ad age", ad_age),
        ("launches", "Keep / kill", "New ads launched per week", launches),
        ("all-ads", "Keep / kill", "All ads", all_ads))),
    ("format", "Format", (
        ("format-scorecard", "Format", "Format scorecard", format_scorecard),
        ("format-benchmarks", "Format", "Format benchmarks", format_benchmarks),
        ("formats-over-time", "Format", "Formats over time", formats_over_time),
        ("spend-return", "Format", "Spend share against return", spend_vs_return),
        ("hook-hold", "Format", "Video: hook against hold", video_hook_hold),
        ("retention", "Format", "Video: where people drop off", video_retention),
        ("ad-types", "Format", "Ad types, never blended", ad_type_split))),
    ("white-space", "White space", (
        ("heatmap", "White space", "Concept by format", concept_heatmap),
        ("stage-heatmap", "White space", "Concept by funnel stage", stage_heatmap),
        ("no-creative", "White space", "Ad types with no creative", no_creative_types),
        ("segments", "White space", "Markets and segments", segments),
        ("gaps", "White space", "Gaps worth testing", gap_list))),
    ("briefing", "Briefing", (
        ("briefs", "Briefing", "Ready briefs", ready_briefs),
        ("copy", "Briefing", "Copy and call to action", copy_cta),
        ("prompts", "Briefing", "Prompts to copy", prompts_panel))),
)
