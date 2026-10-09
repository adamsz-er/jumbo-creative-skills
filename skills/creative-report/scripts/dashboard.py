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
PAGE_FILES = ("index.html", "dashboard.css", "dashboard.js")
DATASET_MAX = 8 * 1024 * 1024  # the dashboard type refuses an attached file over 8 MB
DOC_MAX = 256 * 1024  # and any one store document over 256 KB
ID_PATTERN = re.compile(r"[a-z0-9-]+\Z")
DIGITS = 6  # decimals kept on a computed number; the page formats it for show
THUMBS_LEFT_OUT = "Thumbnails were left out: with them the ad list would pass the 8 MB limit on one data file."
THUMBS_NONE = "No thumbnails were supplied."
REACH_REASON = "n/a (needs an account-level reach and frequency for this window)"
VIDEO_PREVIEWS = "Ad previews, video and the open-ad view are in the HTML version of this report."
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


# ---------- datasets: each a list of flat rows, computed by the same code the HTML uses ----------

def header_rows(ctx: Ctx, images: str) -> List[Dict[str, Any]]:
    tone, words = ctx.completeness
    rows = [{"fact": "Title", "value": ctx.page_title, "tone": None}]
    rows += [{"fact": label, "value": value, "tone": None} for label, value in ctx.header_facts]
    rows += [{"fact": "Completeness", "value": words, "tone": tone}, {"fact": "Generated", "value": ctx.generated, "tone": None},
             {"fact": "Ad images", "value": images, "tone": None}, {"fact": "Previews", "value": VIDEO_PREVIEWS, "tone": None},
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


def daily_rows(ctx: Ctx) -> List[Dict[str, Any]]:
    days, found = panels.time_series(ctx)
    gap = "n/a (fewer than %d days with data in the %d-day window)" % (panels.charts.ROLLING_MIN_VALUES, panels.charts.SPARK_AVERAGE_DAYS)
    return [{"day": day, "metric": s["key"], "name": s["name"], "kind": s["kind"], "unit": s["unit"],
             "value": _num(value), "value_note": None if value is not None else "n/a (no data this day)",
             "average": _num(average), "average_note": None if average is not None else gap}
            for s in found for day, value, average in zip(days, s["values"], s["average"])]


def pareto_rows(ctx: Ctx) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    info = panels.pareto_cut(ctx)
    if not info:
        return [], []
    ranked = info["ranked"]
    rows = [{"rank": i + 1, "ad_id": str(a.get("ad_id") or a.get("ad_name")), "label": ctx.label(a.get("ad_id") or a.get("ad_name")),
             "format": ctx.format_name(a.get("format") or "unknown"), "spend": _num(a["spend"]), "conversion_value": _num(a.get("conversion_value")),
             "conversion_value_note": None if a.get("conversion_value") is not None else "n/a (no purchase value recorded)",
             "cum_spend_pct": _num(info["cum_spend"][i]), "cum_basis_pct": _num(info["cum_basis"][i]), "in_head": i < info["cut"]}
            for i, a in enumerate(ranked)]
    tail = ranked[info["cut"]:]
    unread = sum(1 for a in tail if a.get("conversion_value") is None)
    tail_value_note = ("n/a (no purchase value)" if not info["has_value"] else
                       "n/a (%d of %d long-tail ads have no purchase value recorded)" % (unread, len(tail)) if unread else None)
    share = cm.concentration(ranked, top_n=ctx.concentration_n)
    cut = [{"ads": len(ranked), "cut": info["cut"], "ads_pct": _num(info["cut"] / len(ranked) * 100), "head_share_pct": _num(info["head_basis"]),
            "basis": "purchase value" if info["has_value"] else "spend", "setting_pct": _num(ctx.pareto_share),
            "sentence": panels.pareto_sentence(ctx, info), "coverage": info.get("coverage"),
            "top_n": ctx.concentration_n, "concentration_pct": _num(share),
            "concentration_pct_note": None if share is not None else "n/a (no spend to share out)",
            "tail_ads": len(tail), "tail_spend": _num(sum(a["spend"] for a in tail)),
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
                    "check": "; ".join(checks) or None})
    return out


def verdict_rows(ctx: Ctx, thumbs: Optional[Previews]) -> List[Dict[str, Any]]:
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
        row = {"ad_id": key, "label": rec["label"], "ad_name": rec.get("name"), "format": ctx.format_name(rec.get("format") or "unknown"),
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
                row[metric + "_note"] = interact.plain_ids(row[metric + "_note"])
        if thumbs is not None:
            row["thumb"] = thumbs.embed(key)
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
    return [{"number": g["number"], "label": g["label"], "why": g["why"]} for g in panels.gap_rows(ctx)]


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
        lines.append(("not-in-pull", panels.REACH_NOTE))
    lines += [("method", line) for line in ctx.method_lines]
    lines += [("caveat", _plain(note)) for note in ctx.caveats] or [("caveat", "Nothing was missing from the inputs.")]
    return [{"id": n, "section": section, "text": text} for n, (section, text) in enumerate(lines, 1)]


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
)


def build_datasets(ctx: Ctx) -> Tuple[Dict[str, List[Dict[str, Any]]], str]:
    """Every dataset's rows, and the words for the Ad images header fact."""
    pareto, cut = pareto_rows(ctx)
    thumbs = Previews(None, str(ctx.previews.thumb_dir), ctx.previews.max_kb, DATASET_MAX // 1024) if ctx.previews.thumb_dir else None
    verdicts = verdict_rows(ctx, thumbs)
    images = THUMBS_NONE
    if thumbs is not None:
        shown, total = thumbs.coverage()
        images = "Thumbnails for %d of %d ads." % (shown, total)
        if len(_dump(verdicts)) > DATASET_MAX:
            for row in verdicts:
                row.pop("thumb", None)
            images = THUMBS_LEFT_OUT
    rows = {"header": header_rows(ctx, images), "sections": section_rows(ctx), "kpis": kpi_rows(ctx), "daily": daily_rows(ctx),
            "pareto": pareto, "pareto-cut": cut, "verdict-board": board_rows(ctx), "verdicts": verdicts, "formats": format_rows(ctx),
            "white-space": white_space_rows(ctx), "gaps": gap_rows(ctx), "briefing": briefing_rows(ctx), "notes": note_rows(ctx)}
    return rows, images


def _dump(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _store_name(doc: str) -> str:
    return doc.replace("/", "-") + ".json"


def page_text(name: str, has_thumbs: bool) -> str:
    """A page file as the bundle ships it; the page's thumbnail column is kept only when the ad list carries thumbnails."""
    text = (PAGE / name).read_text(encoding="utf-8")
    if name == "index.html" and not has_thumbs:
        text = re.sub(r"\s*<th[^>]*data-field=\"thumb\"[^>]*>.*?</th>", "", text, flags=re.S)
    return text


def _write_into(root: Path, ctx: Ctx) -> Dict[str, Any]:
    for sub in ("datasets", "files", "store"):
        (root / sub).mkdir(parents=True)
    rows, _ = build_datasets(ctx)
    entries = []
    for dataset_id, title, description in DATASETS:
        path = "datasets/%s.json" % dataset_id
        (root / path).write_bytes(_dump(rows[dataset_id]))
        entries.append({"id": dataset_id, "title": title, "description": description, "file": path, "format": "json"})
    has_thumbs = any("thumb" in row for row in rows["verdicts"])
    store = [{"doc": "dash/meta", "file": "store/" + _store_name("dash/meta")}]
    (root / store[0]["file"]).write_bytes(_dump({"title": ctx.page_title}))
    for name in PAGE_FILES:
        text = page_text(name, has_thumbs)
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

SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)</script>", re.S | re.I)
STYLE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
TAG = re.compile(r"<[^>]*>", re.S)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""")
URL_ATTRS = ("src", "href", "srcset", "poster", "xlink:href", "action", "data")  # attributes that can load or link to something
TEXT_ATTRS = ("title", "alt", "value", "placeholder", "aria-label")  # attributes whose words a reader sees
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MARKUP_NUMBERS_OK: frozenset = frozenset()  # digit runs the page's visible text may carry; every other number comes from a dataset
FORBIDDEN_JS = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|localStorage|sessionStorage|indexedDB|eval)\b"
                          r"|\bFunction\s*\(|\bdocument\s*\.\s*coo[k]ie\b|\[\s*['\"`]coo[k]ie['\"`]\s*\]|\bimport\s*\(|^\s*import\s"
                          r"|\.\s*src\s*=(?!=)|\blocation\s*(?:\.\s*(?:href|assign|replace)\b|=(?!=))"
                          r"|\b(?:setTimeout|setInterval)\s*\(\s*['\"`]", re.M)
_NUMBER = r"-?\d+(?:\.\d+)?"
NUMBER_ARRAY = re.compile(r"\[\s*%s(?:\s*,\s*%s)+\s*,?\s*\]" % (_NUMBER, _NUMBER))
NUMBER_OBJECT = re.compile(r"\{\s*[\w'\"]+\s*:\s*%s(?:\s*,\s*[\w'\"]+\s*:\s*%s)+\s*,?\s*\}" % (_NUMBER, _NUMBER))
CSS_CONTENT = re.compile(r"content\s*:\s*(['\"])(.*?)\1", re.S | re.I)
ROOT_SELECTOR = re.compile(r"\.cr(?:-[\w-]*)?(?![\w-])")
CSS_URL = re.compile(r"url\(\s*([^)]*)\)", re.I)


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


def _style_problems(name: str, css: str) -> List[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for head in re.findall(r"([^{}]+)\{", css):
        head = head.strip()
        if head.startswith("@"):
            if head.lower().startswith("@import"):
                out.append("%s imports a stylesheet: %s" % (name, head[:60]))
            continue
        out += ["%s styles %r, which is not under the page's own .cr classes" % (name, sel.strip())
                for sel in head.split(",") if not ROOT_SELECTOR.match(sel.strip())]
    out += ["%s loads %s from a url(), which must be a data: URL" % (name, url.strip()[:60])
            for url in CSS_URL.findall(css) if not url.strip(" '\"").startswith("data:")]
    out += ["%s has the number %s in a content string; every number must come from a dataset" % (name, found)
            for _, text in CSS_CONTENT.findall(css) for found in sorted(set(NUMBER.findall(text)) - MARKUP_NUMBERS_OK)]
    return out


def _mark_problems(name: str, text: str, files: Sequence[Any], columns: Dict[str, set]) -> List[str]:
    """Problems in one page's tags: loads from outside the bundle, on...= attributes and every data-* mark."""
    out: List[str] = []
    table_source = ""
    for tag in TAG.findall(STYLE.sub("", SCRIPT.sub(r"\1</script>", text))):
        low = tag.lower()
        if low.startswith("</table"):
            table_source = ""
            continue
        attrs = {m.group(1).lower(): next(g for g in m.groups()[1:] if g is not None) for m in ATTR.finditer(tag)}
        if re.search(r"\son[a-z]+\s*=", tag, re.I):
            out.append("%s has an on...= attribute, which the dashboard does not run: %s" % (name, tag[:80]))
        for attr in URL_ATTRS:
            if attr not in attrs:
                continue
            values = ([t.rstrip(",") for t in attrs[attr].split() if not re.fullmatch(r"\d+(?:\.\d+)?[wx],?", t)]
                      if attr == "srcset" else [attrs[attr]])
            for value in values:
                if value in files or value.startswith(("#", "data:")):
                    continue
                action = "loads a script" if low.startswith("<script") else "links to something" if low.startswith("<link") else "loads %s" % attr
                out.append("%s %s that is not a bundle file or a data: URL: %s" % (name, action, value))
        for attr in TEXT_ATTRS:
            out += ["%s has the number %s in its %s attribute; every number must come from a dataset" % (name, found, attr)
                    for found in sorted(set(NUMBER.findall(html.unescape(attrs.get(attr, "")))) - MARKUP_NUMBERS_OK)]
        sources = attrs.get("data-source", "").split()
        if low.startswith("<table"):
            table_source = sources[0] if sources else ""
        out += ["%s marks data-source %r, which is not a dataset in the manifest" % (name, source) for source in sources if source not in columns]
        fields = [attrs["data-field"]] if "data-field" in attrs else []
        fields += [part.split("=", 1)[0] for part in html.unescape(attrs.get("data-where", "")).split("&") if part]
        fields += [part for part in attrs.get("data-row-key", "").split(",") if part]
        owner = sources[0] if sources else table_source if low.startswith("<th") else ""
        for field in fields:
            if not owner:
                out.append("%s marks field %r with no data-source to read it from: %s" % (name, field, tag[:80]))
            elif owner in columns and field not in columns[owner]:
                out.append("%s marks field %r on %s, which has no such column" % (name, field, owner))
    return out


def check_bundle(directory: str) -> List[str]:
    """Problems with a bundle, [] when none: manifest, dataset files, page files, marks and the store documents."""
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
            problems.append("dataset header does not carry %s %s" % (SCHEMA_FACT.lower(), schema["x-version"]))
    for name in manifest["files"]:
        path = root / "files" / str(name)
        if not path.is_file():
            problems.append("page file %s is missing" % name)
            continue
        if path.stat().st_size > DOC_MAX:
            problems.append("page file %s is %d bytes, over the 256 KB limit" % (name, path.stat().st_size))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            problems.append("page file %s cannot be read as UTF-8 text: %s" % (name, error))
            continue
        if name.endswith(".js"):
            problems += _script_problems(name, text)
        elif name.endswith(".css"):
            problems += _style_problems(name, text)
        elif name.endswith(".html"):
            for _, body in SCRIPT.findall(text):
                problems += _script_problems(name, body)
            for body in STYLE.findall(text):
                problems += _style_problems(name, body)
            problems += _mark_problems(name, text, manifest["files"], columns)
            words = TAG.sub(" ", STYLE.sub("", SCRIPT.sub("", text)))
            for found in sorted(set(NUMBER.findall(words)) - MARKUP_NUMBERS_OK):
                problems.append("%s has the number %s in its markup; every number must come from a dataset" % (name, found))
    store = manifest.get("store") or []
    if not isinstance(store, list):
        problems.append("manifest store is not a list of documents: %r" % (store,))
        store = []
    for doc in store:
        if not isinstance(doc, dict):
            problems.append("a store entry is not an object: %r" % (doc,))
            continue
        name = str(doc.get("doc", ""))
        path = root / str(doc.get("file"))
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
        if not isinstance(body, dict):
            problems.append("store document %s is not an object" % name)
        elif name.startswith("files/"):
            source = root / "files" / name[len("files/"):]
            try:
                same = source.is_file() and body.get("text") == source.read_text(encoding="utf-8")
            except (OSError, ValueError):
                same = False
            if not same:
                problems.append("store document %s does not match %s" % (name, source.relative_to(root)))
        elif name == "dash/meta" and body.get("title") != manifest.get("title"):
            problems.append("store document dash/meta does not carry the manifest title")
    return problems
