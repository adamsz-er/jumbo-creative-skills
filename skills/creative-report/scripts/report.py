#!/usr/bin/env python3
"""Turn the analyse skills' outputs into one fixed, branded HTML dashboard.

Usage:
  python3 report.py ads.csv --verdicts verdicts.json [--profile creative-profile.md] \\
      [--source "Meta ads connector"] [--completeness reconciled] [--where market=US] \\
      [--previews DIR] [--thumbs DIR] -o report.html
  python3 report.py --check report.html

Standard library only. The page has the same header, six tabs and panels in the
same order every run. A panel without its data renders a labelled empty state
saying why and how to get the data; it is never dropped. Produce the JSON files
with `--json` on keep-or-kill (and creative-grader, creative-mix). Everything is
graded against the account's own ads, never a benchmark. The page is one file
with inline CSS and SVG; its only external request is the font stylesheet.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402
import interact  # noqa: E402
import panels  # noqa: E402
from panels import Ctx, esc  # noqa: E402
from previews import DEFAULT_BUDGET_KB, DEFAULT_MAX_KB, Previews  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TEMPLATE = ASSETS / "report-template.html"
MISSING = re.compile(r"n/a \(missing [^)]*\)")
CLIP_ID = "clip0_1738_1159"
GRADIENT_ID = "paint0_linear_4_2"


def logo(filename: str, suffix: str) -> str:
    """The brand SVG inlined, without its namespace URL (HTML needs none); its clip and gradient ids get a suffix so no two logos share an id."""
    text = (ASSETS / filename).read_text(encoding="utf-8")
    return text.replace(CLIP_ID, CLIP_ID + suffix).replace(GRADIENT_ID, GRADIENT_ID + suffix).replace(' xmlns="http://www.w3.org/2000/svg"', "")


def lockup(tag: str) -> str:
    """Jumbo, a thin divider, "by" and Elephant Room; the light drawings show on light, the dark ones in dark mode."""
    def pair(name: str, light: str, dark: str, n: int) -> str:
        return ('<span class="logo-light" role="img" aria-label="%s">%s</span><span class="logo-dark" role="img" aria-label="%s">%s</span>'
                % (name, logo(light, "-%s%da" % (tag, n)), name, logo(dark, "-%s%db" % (tag, n))))
    return ('<div class="lockup">%s<span class="brand-div" aria-hidden="true"></span><span class="brand-by">by</span>%s</div>'
            % (pair("Jumbo", "jumbo-logo.svg", "jumbo-logo-dark.svg", 1), pair("Elephant Room", "er-logo-dark.svg", "er-logo.svg", 2)))


def completeness_badge(value: Optional[str]) -> str:
    """The reconcile result as a badge: green Reconciled, red Incomplete <pct>%, amber Not reconciled."""
    if value is None:
        return '<span class="status warn">Not reconciled</span>'
    if value.strip().lower() == "reconciled":
        return '<span class="status ok">Reconciled</span>'
    found = re.fullmatch(r"incomplete:\s*(\d+(?:\.\d+)?)\s*%?", value.strip(), re.I)
    if not found:
        raise ValueError('--completeness must be "reconciled" or "incomplete:<percent>", got %r' % value)
    return '<span class="status bad">Incomplete %s%%</span>' % esc(found.group(1))


def collect_notes(grade, verdicts, mix) -> List[str]:
    notes: List[str] = []
    seen: Counter = Counter()
    for source in (grade, verdicts, mix):
        if not source:
            continue
        for entry in source.get("ads") or []:
            for note in set(MISSING.findall(json.dumps(entry))):
                seen[note] += 1
        for note in set(MISSING.findall(json.dumps({k: v for k, v in source.items() if k != "ads"}))):
            seen.setdefault(note, 0)
    for note, count in sorted(seen.items()):
        where = "%d ad%s" % (count, "" if count == 1 else "s") if count else "the summary"
        notes.append("<code>%s</code> in %s. The metrics that need it are skipped, never counted as 0." % (esc(interact.plain_ids(note)), esc(where)))
    if grade:
        low = sum(1 for a in grade.get("ads", []) if a["diagnosis"]["step"] == "not graded")
        if low:
            notes.append("%d ad%s not graded for low volume." % (low, "" if low == 1 else "s"))
    if verdicts:
        young = (verdicts.get("summary") or {}).get("too_young") or []
        if young:
            notes.append("%d ad%s too young to judge." % (len(young), "" if len(young) == 1 else "s"))
        blind = [a for a in verdicts.get("ads", []) if (a.get("fatigue") or {}).get("status") == "insufficient data"]
        if blind:
            notes.append("Fatigue could not be read for %d ad%s (fewer than two windows of delivery days); those are held, not scaled."
                         % (len(blind), "" if len(blind) == 1 else "s"))
    else:
        notes.append("Verdicts are not in this report: run keep-or-kill with <code>--json</code> and pass the file with <code>--verdicts</code>.")
    if mix and (mix.get("unclassified") or {}).get("count"):
        notes.append("%s ads did not match the naming convention, so the mix describes only part of the account." % esc(mix["unclassified"]["count"]))
    return notes


def brand_from_profile(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"^- Name:\s*(.+)$", text, re.M) or re.search(r"^#\s*Creative profile:\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else None


def heading_for(label: Optional[str]) -> str:
    """"<account label> creative review", the last word in the gradient; a label already ending in review is kept."""
    text = (label or "").strip()
    if not text:
        text = "Creative review"
    elif not text.lower().endswith("review"):
        text += " creative review"
    words = text.split()
    return (esc(" ".join(words[:-1])) + " " if len(words) > 1 else "") + '<span class="grad">%s</span>' % esc(words[-1]), text


def nav_html() -> str:
    links = "".join('<a href="#tab-%s">%s</a>' % (tab_id, esc(title)) for tab_id, title, _ in panels.TABS)
    return '<nav class="tabs" aria-label="Dashboard sections">%s</nav>' % links


def tabs_html(ctx: Ctx) -> str:
    out = []
    for tab_id, title, tab_panels in panels.TABS:
        inner = []
        for panel_id, eyebrow, heading, fn in tab_panels:
            content, state = fn(ctx)
            inner.append('<section class="card panel" id="panel-%s" data-state="%s"><p class="eyebrow">%s</p><h3>%s</h3>%s</section>'
                         % (panel_id, state, esc(eyebrow), esc(heading), content))
        out.append('<section class="tab" id="tab-%s" aria-labelledby="h-%s"><h2 class="tab-title" id="h-%s">%s</h2>%s</section>'
                   % (tab_id, tab_id, tab_id, esc(title), "".join(inner)))
    return "".join(out)


def footer_html(ctx: Ctx, grade, verdicts, mix, brand: Optional[str], completeness: Optional[str], attribution: str,
                source: str, window: str, generated: str, caps: Dict[str, Any], scope: Optional[str] = None) -> str:
    lines = ["Graded against this account's own ads, never benchmarks.",
             "Metric ids and formulas are defined in creative-context/references/metrics.md."]
    if brand:
        lines.append("Account: %s." % brand.rstrip("."))
    if scope:
        lines.append("Scope: %s only; the verdicts and grades should come from the same scope." % scope)
    lines.append("Data source: %s. Window: %s. Attribution: %s. Money is shown in %s."
                 % (source, window, attribution, ctx.currency or "the account's own currency (the export did not name one)"))
    lines.append("Completeness: %s." % ("not reconciled" if completeness is None else completeness))
    if grade:
        lines += [interact.plain_ids(l) for l in str(grade.get("basis", "")).splitlines() if l.strip()]
    if verdicts:
        s = verdicts.get("settings") or {}
        lines.append("Verdict settings used (arbitrary defaults, set them from your own account): young-days=%s, window=%s, "
                     "min-impressions=%s, min-change=%s%%, top-n=%s, grouped by %s."
                     % (s.get("young_days", "n/a"), s.get("window", "n/a"), s.get("min_impressions", "n/a"),
                        s.get("min_change", "n/a"), s.get("top_n", "n/a"), interact.plain_ids(s.get("group_by", "n/a"))))
    lines.append("Dashboard settings used: cards per list (--top-n) %d, Pareto cut (--pareto-share) %.0f%% (a common convention, not a rule), "
                 "concentration counts the top %d ads, previews capped at %d KB each and %d KB in total."
                 % (ctx.top_n, ctx.pareto_share, ctx.concentration_n, caps["max_kb"], caps["budget_kb"]))
    if ctx.funnel_headers:
        read = ["%s read from column %r" % (k.replace("_", " "), v) if v else "%s: no matching column" % k.replace("_", " ")
                for k, v in sorted(ctx.funnel_headers.items())]
        lines.append("Funnel columns beyond the standard fields: %s (matched by normalised header)." % interact.plain_ids("; ".join(read)))
    lines.append("Reach and frequency: %s." % ("from the account-level file" if ctx.account else "not shown, they need an account-level pull"))
    lines.append("Prior period: %s." % ("supplied" if ctx.prior else "not supplied"))
    lines.append(ctx.previews.summary())
    notes = collect_notes(grade, verdicts, mix)
    notes_html = '<ul class="note-list">%s</ul>' % "".join("<li>%s</li>" % n for n in notes) if notes else "<p>Nothing was missing from the inputs.</p>"
    return ('<footer><details class="method" open><summary>Data and method</summary><div class="basis"><pre>%s</pre></div>'
            '<h3>Missing data and caveats</h3>%s</details>'
            '<div class="by">%s<p>A Jumbo creative review <b>by Elephant Room</b> &middot; Generated %s</p></div>'
            '<p class="privacy">Numbers come from your own data. The only outside request this page makes is the font stylesheet, and it falls back to system fonts if blocked.</p></footer>'
            % (esc("\n".join(lines)), notes_html, lockup("f"), esc(generated)))


def build_html(rows: Optional[Sequence[Dict[str, Any]]] = None, grade: Optional[Dict[str, Any]] = None,
               verdicts: Optional[Dict[str, Any]] = None, mix: Optional[Dict[str, Any]] = None,
               profile: Optional[str] = None, title: Optional[str] = None, generated: Optional[str] = None,
               currency: Optional[str] = None, source: str = "Ads Manager export", attribution: Optional[str] = None,
               completeness: Optional[str] = None, account: Optional[Dict[str, float]] = None,
               prior: Optional[Sequence[Dict[str, Any]]] = None, previews: Optional[Previews] = None,
               top_n: int = panels.TOP_N_CARDS, pareto_share: float = panels.PARETO_SHARE,
               scope: Optional[str] = None, key_map: Optional[Dict[str, str]] = None) -> str:
    """Render the dashboard. `rows` are normalised ad rows (creative_metrics.load_rows).

    The title is `title` when given, else the brand from the profile; `scope`
    (for example "market US") is added to it and to the header and footer.
    """
    ctx = Ctx(rows=rows, verdicts=verdicts, grade=grade, mix=mix, currency=currency, top_n=top_n,
              pareto_share=pareto_share, account=account, prior=prior, previews=previews, key_map=key_map)
    brand = brand_from_profile(profile)
    label = title or brand
    if scope:
        label = "%s, %s" % (label, scope) if label else scope
    heading, page_title = heading_for(label)
    start, end = cm.data_window(ctx.rows)
    window = "%s to %s" % (start, end) if start else "n/a (no dates)"
    generated = generated or dt.date.today().isoformat()
    badge = completeness_badge(completeness)
    attribution = attribution or "not stated"
    body = tabs_html(ctx)
    pool, data, bar = panels.pool_html(ctx), panels.data_block(ctx), panels.filter_bar(ctx)
    caps = {"max_kb": ctx.previews.max_kb, "budget_kb": ctx.previews.budget_kb}
    meta = "".join('<li><span>%s</span> %s</li>' % (esc(k), esc(v)) for k, v in (
        ("Window", window), ("Scope", scope or "all ads in the data"), ("Data source", source),
        ("Currency", currency or "account currency (not stated)"), ("Attribution", attribution)))
    fills = {"title": esc(page_title), "heading": heading, "sprite": ctx.previews.sprite(), "brand": lockup("h"),
             "filterbar": bar, "dialog": panels.DIALOG, "data": data, "pool": pool, "meta": meta, "badge": badge, "nav": nav_html(), "body": body,
             "footer": footer_html(ctx, grade, verdicts, mix, brand, completeness, attribution, source, window, generated, caps, scope)}
    return re.sub(r"\{\{(\w+)\}\}", lambda m: fills[m.group(1)], TEMPLATE.read_text(encoding="utf-8"))


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


def load_account(path: Optional[str]) -> Optional[Dict[str, float]]:
    """The account-level reach and frequency file: a JSON object with numeric "reach" and "frequency"."""
    data = _load_json(path)
    if data is None:
        return None
    try:
        return {"reach": float(data["reach"]), "frequency": float(data["frequency"])}
    except (KeyError, TypeError, ValueError):
        raise ValueError('--account must be a JSON object with numeric "reach" and "frequency"')


CHECK_MAX_KB = 16 * 1024  # a page past this is too heavy to share as one file (arbitrary)
ALLOWED_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


def check_html(text: str) -> List[str]:
    """Structural problems in a built dashboard, [] when none. A floor for when no browser is available, not a visual check.

    Checks that every tab and panel is present in order, each panel has a known
    state, the completeness badge and the Scope line are present, the only outside
    requests are the font stylesheet, no script tag carries a src, no "n/a"
    reads as a number, and the file is under CHECK_MAX_KB.
    """
    problems = []
    last = -1
    for tab_id, title, tab_panels in panels.TABS:
        at = text.find('id="tab-%s"' % tab_id)
        if at < 0:
            problems.append("tab %s (%s) is missing" % (tab_id, title))
            continue
        if at < last:
            problems.append("tab %s is out of order" % tab_id)
        last = at
        for panel_id, _, heading, _ in tab_panels:
            found = re.search(r'id="panel-%s" data-state="(\w+)"' % re.escape(panel_id), text)
            if not found:
                problems.append("panel %s (%s) is missing" % (panel_id, heading))
            elif found.group(1) not in ("data", "empty", "partial"):
                problems.append("panel %s has an unknown state %s" % (panel_id, found.group(1)))
    if not re.search(r'class="status (ok|bad|warn)"', text):
        problems.append("the completeness badge is missing")
    if "<span>Scope</span>" not in text:
        problems.append("the Scope line is missing from the header")
    hosts = sorted({h for h in re.findall(r'(?:src|href)\s*=\s*"https?://([^/"]+)', text) if h not in ALLOWED_HOSTS})
    if hosts:
        problems.append("outside requests besides the font stylesheet: %s" % ", ".join(hosts))
    if re.search(r"<script[^>]+\bsrc\s*=", text):
        problems.append("a script is loaded from a file or URL; everything must be inline")
    if re.search(r"n/a\s*\(missing[^)]*\)\s*0\b|>0 \(missing", text):
        problems.append("a missing value is shown as 0")
    size_kb = len(text.encode("utf-8")) / 1024
    if size_kb > CHECK_MAX_KB:
        problems.append("the file is %.0f KB, over %d KB" % (size_kb, CHECK_MAX_KB))
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the branded creative dashboard as one self-contained HTML file.")
    parser.add_argument("data", nargs="?", help="Ads Manager CSV (or JSON rows): the daily ad-level data behind every number")
    parser.add_argument("--grade", help="creative-grader --json output")
    parser.add_argument("--verdicts", help="keep-or-kill --json output")
    parser.add_argument("--mix", help="creative-mix --json output")
    parser.add_argument("--profile", help="creative-profile.md: the account name, and its Script settings block fills any flag left unset")
    parser.add_argument("--csv", help="the Ads Manager CSV behind the JSON files, only to read the currency code from its spend header")
    parser.add_argument("--currency", help="three-letter currency code to show; default: read from the export's spend header")
    parser.add_argument("--title", help="account label for the title, over the profile's brand; 'Acme' reads 'Acme creative review'")
    parser.add_argument("--scope", help='what the data covers, shown in the title and header, e.g. "market US"; '
                                        "default: read from --where")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--check", metavar="HTML", help="check a built dashboard's structure and exit (no browser needed)")
    cm.add_run_arguments(parser, profile=False)
    parser.add_argument("--source", default="Ads Manager export", help='data source shown in the header (pass "Meta ads connector" for a connector pull)')
    parser.add_argument("--attribution", help="attribution setting shown in the header (default: not stated)")
    parser.add_argument("--completeness", help='what from_mcp printed: "reconciled" or "incomplete:<percent>"; absent reads Not reconciled')
    parser.add_argument("--account", help='JSON file with account-level "reach" and "frequency" for the window')
    parser.add_argument("--prior", help="CSV or JSON of the previous equal window, for change against prior period")
    parser.add_argument("--previews", help="folder of rendered ad previews named <ad_id>.<ext>")
    parser.add_argument("--thumbs", help="folder of small thumbnails or video stills named <ad_id>.<ext>")
    parser.add_argument("--preview-max-kb", type=int, default=DEFAULT_MAX_KB, help="skip an image larger than this (default %(default)s)")
    parser.add_argument("--preview-budget-kb", type=int, default=DEFAULT_BUDGET_KB, help="stop embedding images past this total (default %(default)s)")
    parser.add_argument("--top-n", type=int, default=panels.TOP_N_CARDS, help="ad cards shown per list before the rest collapse (default %(default)s)")
    parser.add_argument("--pareto-share", type=float, default=panels.PARETO_SHARE,
                        help="percent of purchase value the Pareto cut must reach; a common convention, not a rule (default %(default)s)")
    parser.add_argument("-o", "--output", default="report.html", help="where to write the HTML (default report.html)")
    args = parser.parse_args(argv)
    if args.check:
        problems = check_html(Path(args.check).read_text(encoding="utf-8"))
        print("\n".join(["problem: " + p for p in problems] or ["OK: structure checks passed (this is not a visual check)"]))
        return 1 if problems else 0
    if not any((args.data, args.grade, args.verdicts, args.mix)):
        parser.error("give a CSV of ad rows, or at least one of --grade, --verdicts, --mix")
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.data) if args.data else [])
        where = cm.parse_where(args.where)
        prior = cm.filter_rows(cm.load_rows(args.prior), where, key_map) if args.prior else None
        profile = Path(args.profile).read_text(encoding="utf-8") if args.profile else None
        page = build_html(rows=rows, grade=_load_json(args.grade), verdicts=_load_json(args.verdicts), mix=_load_json(args.mix),
                          profile=profile, title=args.title, currency=args.currency or detect_currency(args.data) or detect_currency(args.csv),
                          source=args.source, attribution=args.attribution, completeness=args.completeness,
                          account=load_account(args.account), prior=prior,
                          previews=Previews(args.previews, args.thumbs, args.preview_max_kb, args.preview_budget_kb),
                          top_n=args.top_n, pareto_share=args.pareto_share,
                          scope=args.scope or cm.describe_where(where), key_map=key_map)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    Path(args.output).write_text(page, encoding="utf-8")
    print("\n".join(run_notes + ["wrote %s" % args.output]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
