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
from previews import Previews  # noqa: E402

TOP_N_CARDS = 8  # arbitrary default: how many ad cards each list shows before collapsing the rest
CONCENTRATION_N = 3  # arbitrary default, as in keep-or-kill: how many top-spend ads the concentration gauge counts
PARETO_SHARE = 80.0  # the common Pareto convention, not a rule: set it from your own account
LIST_CAP = 60  # arbitrary display cap on a collapsed list, so a 500-ad account stays readable
LABEL_WORDS = 64  # arbitrary: where a fallback ad name is cut, at a word boundary

LABELS = {"hook_rate": "Hook rate", "hold_rate": "Hold rate", "video_completion_rate": "Video completion rate",
          "ctr": "CTR", "cvr": "CVR", "cpm": "CPM", "cpc": "CPC", "cpa": "CPA", "roas": "ROAS", "mer": "MER",
          "add_to_cart_rate": "Add-to-cart rate", "cost_per_add_to_cart": "Cost per add to cart"}
_LABEL_RE = re.compile(r"\b(%s)\b" % "|".join(sorted(LABELS, key=len, reverse=True)))

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
    return esc(shown)


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
        self.funnel_headers: Dict[str, Optional[str]] = {}
        settings = (verdicts or {}).get("settings") or {}
        self.concentration_n = int(settings.get("top_n") or CONCENTRATION_N)

    def money(self, value: Optional[float], digits: int = 0) -> str:
        if value is None:
            return "n/a"
        text = "{:,.{d}f}".format(value, d=digits)
        return "%s %s" % (self.currency, text) if self.currency else "%s (account currency)" % text


# ---------- ad cards ----------

def _first_segment(name: Optional[str]) -> str:
    return re.split(r"\s*\|\s*|\s_\s|\s-\s", str(name or "").strip())[0].strip()


def _truncate(text: str, limit: int = LABEL_WORDS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" |-_,") + "..."


def readable_label(fields: Dict[str, Any], name: Optional[str], ad_id: Any = None) -> str:
    """concept · creator · format · ad type, skipping what did not parse; never the raw first name segment."""
    parts = [str(fields[k]) for k in ("concept", "creator", "format", "ad_type") if fields.get(k)]
    label = " · ".join(parts)
    if label and label.lower() != _first_segment(name).lower():
        return label
    if name:
        return _truncate(str(name))
    return label or "Ad %s" % (ad_id if ad_id is not None else "(no id)")


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


def _image(ctx: Ctx, ad_id: Any, label: str, fmt: str) -> str:
    alt = "%s (%s)" % (label, fmt or "format not known")
    found = ctx.previews.resolve(ad_id)
    if found["symbol"]:
        return ('<svg class="pv" role="img" aria-label="%s" viewBox="0 0 %d %d" width="%d" height="%d"><use href="#%s" width="%d" height="%d"/></svg>'
                % (esc(alt), found["width"], found["height"], found["width"], found["height"], esc(found["symbol"]), found["width"], found["height"]))
    return ('<svg class="ph" viewBox="0 0 300 300" width="300" height="300" role="img" aria-label="%s">'
            '<rect class="ph-bg" x="0" y="0" width="300" height="300" rx="16"/>'
            '<text class="ph-format" x="150" y="140" text-anchor="middle">%s</text>'
            '<text x="150" y="172" text-anchor="middle">preview unavailable:</text>'
            '<text x="150" y="192" text-anchor="middle">%s</text></svg>'
            % (esc(alt + ", preview unavailable: " + str(found["reason"])), esc((fmt or "format n/a").upper()), esc(found["reason"])))


def ad_card(ctx: Ctx, entry: Dict[str, Any], driver: str = "", next_step: bool = False) -> str:
    """The one ad component: image, label, id, spend, what placed it, verdict, confidence and sentence."""
    base = _fields_for(ctx, entry)
    ad_id = entry.get("ad") or base.get("ad_id")
    name = entry.get("ad_name") or entry.get("name") or base.get("ad_name")
    label = readable_label(base, name, ad_id)
    spend = (ctx.ad_index.get(str(ad_id)) or {}).get("spend", entry.get("spend"))
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
    return ('<article class="ad-card"><div class="ad-img">%s</div><div class="ad-body"><h4>%s</h4><p class="adid">Ad ID %s</p>'
            '<p class="ad-spend"><b>%s</b> spend</p>%s<p class="chips">%s%s</p>%s%s%s</div></article>'
            % (_image(ctx, ad_id, label, str(base.get("format") or "")), esc(label), esc(ad_id if ad_id is not None else "n/a"),
               esc(ctx.money(spend)), drive, chip, conf, sentence, step, check))


def card_grid(cards: Sequence[str]) -> str:
    return '<div class="ad-grid">%s</div>' % "".join(cards)


def compact_list(ctx: Ctx, entries: Sequence[Dict[str, Any]], what: str) -> str:
    """A closed <details> holding a compact table of the ads not shown as cards, capped at LIST_CAP."""
    if not entries:
        return ""
    shown = entries[:LIST_CAP]
    body = []
    for e in shown:
        base = _fields_for(ctx, e)
        ad_id = e.get("ad") or base.get("ad_id")
        spend = (ctx.ad_index.get(str(ad_id)) or {}).get("spend", e.get("spend"))
        cls = entry_class(e) if "verdict_id" in e else None
        body.append('<tr><td class="adname">%s<small>Ad ID %s</small></td><td class="num" data-label="Spend">%s</td><td>%s</td></tr>'
                    % (esc(readable_label(base, e.get("ad_name") or e.get("name") or base.get("ad_name"), ad_id)),
                       esc(ad_id), esc(ctx.money(spend)), esc(VERDICT_LABEL[cls]) if cls else ""))
    more = "" if len(entries) <= LIST_CAP else '<p class="muted">Showing the %d largest of %d; %d more are not listed.</p>' % (
        LIST_CAP, len(entries), len(entries) - LIST_CAP)
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
            notes.append("%s missing on %d of %d rows" % (field, missing, len(rows)))
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
            return cm.format_value(total, key)
        return "n/a (missing %s)" % key
    if kind.startswith("money"):
        return ctx.money(value, int(kind[-1]))
    if kind == "int":
        return "{:,.0f}".format(value)
    if kind == "pct":
        return "%.2f%%" % value
    return "%.2fx" % value


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
        if key == "reach":
            text = "{:,.0f}".format(ctx.account["reach"]) if ctx.account else NEEDS_ACCOUNT
        elif key == "frequency":
            text = "%.2f" % ctx.account["frequency"] if ctx.account else NEEDS_ACCOUNT
        else:
            text = _kpi_text(ctx, total, key, kind)
        label = name
        if key == "ctr" and ctr_basis == "clicks":
            label = "CTR (all clicks)"
        if key == "hook_rate" and derived:
            label += " (derived)"
        if key in ("reach", "frequency") or prior_total is None:
            delta = "no prior period" if prior_total is None else "n/a (reach is account-level only)"
        else:
            change = _pct_change(_kpi_value(total, key), _kpi_value(prior_total, key))
            delta = "n/a (prior value missing or zero)" if change is None else "%+.1f%% vs prior period" % change
        spark = ""
        if key not in ("reach", "frequency"):
            spark = charts.sparkline([_kpi_value(day_total, key) for _, day_total in series], "%s by day" % name)
        spark_note = spark or ('<span class="muted">%s</span>' % ("one day of data" if len(series) == 1 else
                                                                   "no sparkline for reach or frequency" if key in ("reach", "frequency") else "no dated rows"))
        unit = " (%s)" % (ctx.currency or "account currency") if kind.startswith("money") else ""
        partial = coverage(ctx.rows, needs.get(key, ()))
        unknown = " unknown" if text.startswith("n/a") else ""
        note_html = '<p class="kpi-note">%s</p>' % esc("; ".join(partial)) if partial else ""
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
                             '<td class="num" data-label="From the step before">n/a</td></tr>' % (esc(name), esc(field)))
            gap = gap or name
            continue
        share = "n/a" if not base else "%.2f%%" % (value / base * 100)
        if previous is None and name != "Impressions":
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
            'clicks. Read the share of impressions for a like-for-like view.</p>')
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
        ("funnel", "Overview", "Funnel", funnel))),
    ("pareto", "Pareto", (
        ("pareto", "Pareto", "Where the value comes from", pareto),
        ("head-tail", "Pareto", "The head and the long tail", head_tail))),
    ("keep-kill", "Keep / kill", (
        ("board", "Keep / kill", "Verdict board", verdict_board),
        ("fatigue", "Keep / kill", "Fatigue", fatigue))),
    ("format", "Format", (("format", "Format", "Format scorecard, video and ad types", not_built("Format")),)),
    ("white-space", "White space", (("white-space", "White space", "Concept by format gaps", not_built("White space")),)),
    ("briefing", "Briefing", (("briefing", "Briefing", "Ready briefs and prompts", not_built("Briefing")),)),
)
