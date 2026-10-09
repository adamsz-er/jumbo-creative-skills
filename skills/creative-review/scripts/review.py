#!/usr/bin/env python3
"""One command from ad data to the whole review.

Usage:
  python3 review.py pull RESPONSES... --expect-spend X --expect-impressions Y -o ads.csv
  python3 review.py run DATA [--profile P] [--where K=V] [--target cpa=40] ...
  python3 review.py run --demo

`pull` merges saved Meta ads connector responses into a CSV and reconciles it.
`run` grades the ads, gives each a verdict, maps the creative mix, builds the
six-tab dashboard and writes a three-bullet summary, all into one run folder
`<cache-dir>/<account>/<window-end>_<HHMMSS>/`, then says what changed since the
last run of the same account. Standard library only; the sibling skills'
scripts are called by path with `python3 -I`. A known failure prints a plain
message and its fix and exits with its own code (see errors.py); `--debug` shows
tracebacks.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import changes as changes_mod  # noqa: E402
import creative_metrics as cm  # noqa: E402
import errors  # noqa: E402
import profile_draft  # noqa: E402
from errors import ReviewError  # noqa: E402

SKILLS = HERE.parent.parent
DEMO_CSV = HERE.parent / "assets" / "demo" / "ads_daily.csv"
DEMO_NAME = "Acme Outdoor Co. (sample data)"
DEMO_SOURCE = "Sample data (Acme Outdoor Co.)"
DEFAULT_CACHE = "creative-review-runs"
DEFAULT_PROFILE = "creative-profile.md"
FALLBACK_SLUG = "account"
SLUG_HASH_LENGTH = 8  # characters of the account-id hash used as a name; arbitrary

SIBLINGS = {
    "grade": ("creative-grader", "grade.py"),
    "verdicts": ("keep-or-kill", "verdicts.py"),
    "mix": ("creative-mix", "mix.py"),
    "report": ("creative-report", "report.py"),
}
REQUIRED = (("date", "date"), ("ad_name", "ad name"), ("spend", "spend"), ("impressions", "impressions"))


# ---------- helpers ----------

def sibling(step: str) -> Path:
    skill, script = SIBLINGS[step]
    path = SKILLS / skill / "scripts" / script
    if not path.exists():
        raise ReviewError("E-SKILL", skill=skill)
    return path


def run_script(path: Path, args: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run([sys.executable, "-I", str(path)] + list(args), capture_output=True, text=True)


def last_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1] if lines else "no message"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or FALLBACK_SLUG


def read_profile(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ReviewError("E-PROFILE", path=path, reason=error.strerror or str(error))


def brand_of(profile: Optional[str]) -> Optional[str]:
    if not profile:
        return None
    found = re.search(r"^- Name:\s*(.+)$", profile, re.M) or re.search(r"^#\s*Creative profile:\s*(.+)$", profile, re.M)
    name = found.group(1).strip() if found else ""
    return name if name and name.lower() not in ("unknown", profile_draft.NOT_STATED) else None


def account_ids(rows: Sequence[Dict[str, Any]]) -> List[str]:
    found = set()
    for row in rows:
        for key, value in row.items():
            if re.sub(r"[^a-z]", "", str(key).lower()) == "accountid" and str(value or "").strip():
                found.add(str(value).strip())
    return sorted(found)


def account_slug(brand: Optional[str], rows: Sequence[Dict[str, Any]], account_file: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The folder name for this account and whether it is only the bare fallback.

    Order: the profile brand, the account name in the data or the --account file, a short hash of the
    account ids in the data, else the bare name "account".
    """
    name = brand or profile_draft.account_name(rows) or (str((account_file or {}).get("name") or "").strip() or None)
    if name:
        return {"slug": slugify(name), "name": name, "fallback": False}
    ids = account_ids(rows)
    if ids:
        return {"slug": "acct-" + hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:SLUG_HASH_LENGTH], "name": None, "fallback": False}
    return {"slug": FALLBACK_SLUG, "name": None, "fallback": True}


def check_columns(rows: Sequence[Dict[str, Any]], path: str) -> None:
    present = {key for row in rows for key in row}
    missing = [label for key, label in REQUIRED if key not in present]
    if missing:
        raise errors.columns_error(path, missing)


def header_gaps(path: str) -> List[str]:
    """Which required columns a CSV header lacks, for a file the loader could not read a row from."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        names = next(csv.reader(handle), [])
    probe = cm.load_rows([dict.fromkeys(names, "1")], level="ad") if names else []
    keys = {key for row in probe for key in row}
    return [label for key, label in REQUIRED if key not in keys]


def load_data(path: str) -> List[Dict[str, Any]]:
    if not Path(path).exists():
        raise errors.nodata_error(path)
    try:
        return cm.load_rows(path)
    except ValueError:
        raise errors.columns_error(path, header_gaps(path) or ["ad name"])


def in_window(rows: Sequence[Dict[str, Any]], first: Optional[str], last: Optional[str]) -> List[Dict[str, Any]]:
    if not first and not last:
        return list(rows)
    return [r for r in rows if r.get("date") and (not first or str(r["date"]) >= first) and (not last or str(r["date"]) <= last)]


def money(value: Optional[float], currency: Optional[str]) -> str:
    return "n/a" if value is None else changes_mod.money(value, currency)


# ---------- summary ----------

def headline(rows: Sequence[Dict[str, Any]], currency: Optional[str], moves: Optional[List[Dict[str, Any]]], basis: str) -> str:
    t = changes_mod.totals(rows)
    roas = changes_mod.roas(t)
    purchases = "%s purchases" % "{:,.0f}".format(t["conversions"]) if t["conversions"] is not None else "purchases n/a (missing purchases)"
    roas_text = "ROAS %.2f" % roas if roas is not None else "ROAS n/a (missing purchase value or spend)"
    first = "%s spent, %s, %s" % (money(t["spend"], currency), purchases, roas_text)
    if moves is None:
        return "%s (%s)." % (first, basis)
    pieces = [m["short"] for m in moves[:2] if m.get("change_pct") is not None]
    return "%s (%s: %s)." % (first, basis, ", ".join(pieces) if pieces else "no change figure to show, n/a")


def biggest_action(verdicts: Dict[str, Any], currency: Optional[str]) -> str:
    first = ((verdicts.get("summary") or {}).get("do_first") or [None])[0]
    if not first:
        return "Nothing needs doing first: no ad stands out to pause, fix or scale."
    return "%s (%s at stake): %s" % (first.get("ad_name") or first.get("ad"), money(first.get("spend_at_stake"), currency), first.get("sentence"))


def biggest_opportunity(mix: Dict[str, Any]) -> str:
    if mix.get("concepts_unread"):
        return mix["concepts_unread_message"]
    gaps = mix.get("gaps") or []
    if not gaps:
        return "No clear gap yet in the creative mix."
    gap = gaps[0]
    why = ", ".join(gap.get("why") or []) or "not stated"
    return "Try the %s idea as a %s (no ads like it yet): %s." % (gap.get("concept"), gap.get("format"), why)


def summary_text(title: str, bullets: Sequence[str], report: Path) -> str:
    lines = ["Creative review: %s" % title, ""] + ["- %s" % b for b in bullets] + ["", "Full dashboard: %s" % report]
    return "\n".join(lines) + "\n"


# ---------- pull ----------

def cmd_pull(args: argparse.Namespace) -> int:
    script = HERE / "from_mcp.py"
    flags: List[str] = list(args.responses) + ["-o", args.output]
    for flag, value in (("--expect-spend", args.expect_spend), ("--expect-impressions", args.expect_impressions),
                        ("--expect-ads", args.expect_ads), ("--tolerance", args.tolerance), ("--level", args.level)):
        if value is not None:
            flags += [flag, str(value)]
    done = run_script(script, flags)
    print(done.stdout.rstrip())
    if done.returncode == 3:
        warning = next((l for l in done.stdout.splitlines() if l.startswith("WARNING")), "")
        raise ReviewError("E-RECONCILE", problems=warning.split("yet: ", 1)[-1] or "the totals do not match")
    if done.returncode == 4:
        units = next((l.split("mixed currency: ", 1)[1] for l in done.stdout.splitlines() if "mixed currency: " in l), "more than one")
        raise ReviewError("E-MIXED-CURRENCY", units=units)
    if done.returncode != 0:
        raise ReviewError("E-ANALYSIS", step="pull", detail=last_line(done.stdout + done.stderr), folder=str(Path(args.output).parent.resolve()))
    reconciled = any("reconciled against the expected totals" in l for l in done.stdout.splitlines())
    print("completeness: %s" % ("reconciled" if reconciled else "not checked (leave --completeness out)"))
    return 0


# ---------- run ----------

def run_folder(cache: Path, slug: str, end: Optional[str], moment: dt.datetime) -> Path:
    """A fresh folder `<window end>_<YYYYMMDD-HHMMSS>`, with -2, -3 ... added on a collision (the clock is never bumped)."""
    base = "%s_%s" % (end or moment.date().isoformat(), moment.strftime("%Y%m%d-%H%M%S"))
    parent = cache / slug
    parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 10000):
        folder = parent / (base if attempt == 1 else "%s-%d" % (base, attempt))
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            continue
    raise ReviewError("E-ANALYSIS", step="setup", detail="could not make a run folder under %s" % parent, folder=str(parent))


def window_days(start: Optional[str], end: Optional[str]) -> Optional[int]:
    if not start or not end:
        return None
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1


def write_run_info(folder: Path, info: Dict[str, Any], complete: bool) -> None:
    (folder / changes_mod.RUN_FILE).write_text(json.dumps(dict(info, complete=complete), indent=1), encoding="utf-8")


def shared_flags(args: argparse.Namespace, profile: Optional[str], extra: Sequence[str] = ()) -> List[str]:
    flags: List[str] = []
    if profile:
        flags += ["--profile", profile]
    for clause in args.where or []:
        flags += ["--where", clause]
    if args.type_map:
        flags += ["--type-map", args.type_map]
    if args.key_map:
        flags += ["--key-map", args.key_map]
    return flags + list(extra)


def analyse(step: str, data: str, flags: Sequence[str], folder: Path, profile: Optional[str]) -> Dict[str, Any]:
    done = run_script(sibling(step), [data] + list(flags) + ["--json"])
    text = done.stdout + done.stderr
    if done.returncode != 0:
        detail = last_line(done.stderr if done.stderr.strip() else done.stdout)
        if "--target" in text:
            raise ReviewError("E-TARGET", detail=detail, metrics=", ".join(cm.METRICS))
        if "--profile" in text:
            raise ReviewError("E-PROFILE", path=profile or "the profile", reason=detail)
        raise ReviewError("E-ANALYSIS", step=step, detail=detail, folder=str(folder))
    (folder / ("%s.json" % ("grade" if step == "grade" else step))).write_text(done.stdout, encoding="utf-8")
    return json.loads(done.stdout)


def cmd_run(args: argparse.Namespace) -> int:
    for step in SIBLINGS:
        sibling(step)
    if args.demo:
        data, source, brand_override = str(DEMO_CSV), DEMO_SOURCE, DEMO_NAME
    elif args.data:
        data, source, brand_override = args.data, args.source, None
    else:
        raise errors.nodata_error()
    if not Path(data).exists():
        raise errors.nodata_error(data)
    profile_path = args.profile or (DEFAULT_PROFILE if not args.demo and Path(DEFAULT_PROFILE).exists() else None)
    profile = read_profile(profile_path)
    all_rows = load_data(data)
    check_columns(all_rows, data)
    rows = in_window(all_rows, args.date_from, args.date_to)
    if not rows:
        start, end = cm.data_window(all_rows)
        window = " to ".join(x for x in (args.date_from or "the start", args.date_to or "the end"))
        raise errors.empty_window_error(window, "%s to %s" % (start, end) if start else "no dated rows")
    currency = args.currency or cm.detect_currency(data) or (cm.read_settings(profile_path).get("currency") if profile_path else None)
    if not currency:
        raise ReviewError("E-CURRENCY")
    currency = currency.upper()
    account_file = json.loads(Path(args.account).read_text(encoding="utf-8")) if args.account else None
    brand = brand_override or brand_of(profile)
    who = account_slug(brand, rows, account_file)
    start, end = cm.data_window(rows)
    setup = argparse.Namespace(profile=profile_path, type_map=args.type_map, key_map=args.key_map, where=args.where, currency=None, target=None)
    try:
        scoped, _, _ = cm.prepare_run(setup, rows)
    except ValueError as error:
        raise ReviewError("E-PROFILE", path=profile_path, reason=str(error)) if "--profile" in str(error) else \
            ReviewError("E-ANALYSIS", step="setup", detail=str(error), folder=args.cache_dir)
    where = sorted(c.strip().lower() for c in (setup.where or [])) or None
    if not scoped:
        raise errors.empty_filter_error(where)

    moment = dt.datetime.now().astimezone()
    folder = run_folder(Path(args.cache_dir), who["slug"], end, moment)
    info = {"created_at": moment.isoformat(), "window_from": start, "window_to": end, "window_days": window_days(start, end),
            "where": where, "account_slug": who["slug"], "account_name": who["name"] or brand, "source": source}
    write_run_info(folder, info, complete=False)
    windowed = bool(args.date_from or args.date_to)
    if windowed:
        working = folder / "ads.json"
        working.write_text(json.dumps(rows), encoding="utf-8")
    else:
        working = folder / ("ads.json" if data.lower().endswith(".json") else "ads.csv")
        shutil.copyfile(data, working)
    path = str(working)

    verdict_extra = ["--currency", currency] + (["--target", args.target] if args.target else [])
    flags = shared_flags(args, profile_path)
    verdicts = analyse("verdicts", path, shared_flags(args, profile_path, verdict_extra), folder, profile_path)
    grade = analyse("grade", path, flags, folder, profile_path)
    mix = analyse("mix", path, flags, folder, profile_path)

    previous = changes_mod.latest_earlier_run(Path(args.cache_dir) / who["slug"], info["created_at"])
    keep = lambda before: cm.filter_rows(before, cm.parse_where(setup.where), cm.parse_key_map(setup.key_map) if setup.key_map else None)  # noqa: E731
    diff = changes_mod.compare(previous, {"rows": scoped, "verdicts": verdicts, "currency": currency, "window_days": info["window_days"],
                                          "where": where, "scope": keep})
    own_prior = not args.prior and diff.get("account") is not None
    if not diff.get("first_run"):
        diff["prior_is_previous_run"] = own_prior
    if mix.get("concepts_unread"):
        diff["concepts_unread"] = info["concepts_unread"] = True
    (folder / "changes.json").write_text(json.dumps(diff, indent=1), encoding="utf-8")

    title = who["name"] or brand
    report = folder / "report.html"
    report_flags = ["--grade", str(folder / "grade.json"), "--verdicts", str(folder / "verdicts.json"), "--mix", str(folder / "mix.json"),
                    "--changes", str(folder / "changes.json"), "--currency", currency, "--source", source, "-o", str(report)]
    report_flags += shared_flags(args, profile_path)
    for flag, value in (("--title", title if brand_override or not profile else None), ("--completeness", args.completeness),
                        ("--account", args.account), ("--prior", args.prior), ("--previews", args.previews), ("--thumbs", args.thumbs),
                        ("--attribution", args.attribution)):
        if value:
            report_flags += [flag, str(value)]
    if own_prior:
        report_flags += ["--prior", str(changes_mod.ads_file(previous))]
    done = run_script(sibling("report"), [path] + report_flags)
    if done.returncode != 0:
        raise ReviewError("E-ANALYSIS", step="report", detail=last_line(done.stderr or done.stdout), folder=str(folder))
    checked = run_script(sibling("report"), ["--check", str(report)])
    if checked.returncode != 0:
        problem = next((l for l in checked.stdout.splitlines() if l.startswith("problem")), last_line(checked.stdout))
        raise ReviewError("E-REPORT", problem=problem)

    if args.prior:
        prior_rows = cm.load_rows(args.prior)
        moves, basis = changes_mod.account_moves(prior_rows, scoped, currency), "against the prior-period file"
    elif diff.get("account") is not None and not diff.get("first_run") and not diff.get("not_compared"):
        moves, basis = diff["account"], "since the last review"
    elif diff.get("not_compared"):
        moves, basis = None, ("not compared with the last review: different window or filter" if diff["not_compared"] == changes_mod.DIFFERENT_SCOPE
                              else "not compared with the last review: it looks like a different account")
    else:
        moves, basis = None, "first run: nothing to compare yet"
    bullets = [headline(scoped, currency, moves, basis), biggest_action(verdicts, currency), biggest_opportunity(mix)]
    text = summary_text(title or "your ads", bullets, report.resolve())
    (folder / "summary.md").write_text(text, encoding="utf-8")
    write_run_info(folder, info, complete=True)
    print(text, end="")
    return 0


# ---------- cli ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One command from ad data to the whole creative review.")
    parser.add_argument("--debug", action="store_true", help="show the full traceback when something unexpected goes wrong")
    sub = parser.add_subparsers(dest="command", required=True)

    pull = sub.add_parser("pull", help="merge saved Meta ads connector responses into a reconciled CSV")
    pull.add_argument("responses", nargs="+", help="saved connector responses (JSON)")
    pull.add_argument("-o", "--output", required=True, help="CSV to write")
    pull.add_argument("--expect-spend", type=float, help="account-level spend for the same window")
    pull.add_argument("--expect-impressions", type=float, help="account-level impressions for the same window")
    pull.add_argument("--expect-ads", help="text file with one expected ad id per line")
    pull.add_argument("--tolerance", type=float, help="percent a pull may fall short before it counts as incomplete")
    pull.add_argument("--level", help="level of the rows (default: ad)")

    run = sub.add_parser("run", help="analyse, build the dashboard and summarise, in one run folder")
    run.add_argument("data", nargs="?", help="Ads Manager CSV, or a .json file of rows (not needed with --demo)")
    run.add_argument("--demo", action="store_true", help="review the built-in sample account; needs no data or connection")
    run.add_argument("--prior", help="CSV or JSON of the previous equal window, for change against the prior period")
    run.add_argument("--account", help='JSON file with account-level "reach" and "frequency" for the window (and optionally "name")')
    run.add_argument("--previews", help="folder of rendered ad previews named <ad_id>.<ext>")
    run.add_argument("--thumbs", help="folder of small thumbnails named <ad_id>.<ext>")
    run.add_argument("--profile", help="creative-profile.md (default: ./creative-profile.md when it exists)")
    run.add_argument("--currency", help="three-letter currency code; default: read from the export's spend header or the profile")
    run.add_argument("--source", default="Ads Manager export", help='data source shown in the header ("Meta ads connector" for a pull)')
    run.add_argument("--attribution", help="attribution setting shown in the header")
    run.add_argument("--completeness", help='what `pull` printed: "reconciled" or "incomplete:<percent>"')
    run.add_argument("--where", action="append", help="keep only rows where a column or name field matches, e.g. market=US (repeatable)")
    run.add_argument("--type-map", help="the account's own ad-type words, e.g. core=bau")
    run.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names")
    run.add_argument("--target", help="your own payback targets, e.g. cpa=40,roas=3 (read by the verdicts only)")
    run.add_argument("--from", dest="date_from", help="first day of the window to review (YYYY-MM-DD); default: the first day in the data")
    run.add_argument("--to", dest="date_to", help="last day of the window to review (YYYY-MM-DD); default: the last day in the data")
    run.add_argument("--cache-dir", default=DEFAULT_CACHE, help="where run folders are kept (default ./%s)" % DEFAULT_CACHE)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_pull(args) if args.command == "pull" else cmd_run(args)
    except ReviewError as error:
        print(error.render(), file=sys.stderr)
        return error.exit_status
    except Exception as error:  # noqa: BLE001 - the last line of defence: never a traceback unless asked
        if args.debug:
            raise
        print(errors.unexpected_text(error), file=sys.stderr)
        return errors.UNEXPECTED_EXIT


if __name__ == "__main__":
    sys.exit(main())
