#!/usr/bin/env python3
"""Make ad names to a schema you pick, audit existing names, and write an old -> new rename map.

Usage: python3 namer.py make specs.csv|specs.json --fields concept,format,persona [--sep " | "] [--keyed]
                                [--allow-missing] [--dedupe] [-o names.csv [--force]] [--json]
       python3 namer.py audit ads.csv|rows.json|names.txt [--fields concept,format,persona] [--json]
       python3 namer.py map ads.csv|rows.json --fields concept,format,funnel_stage,version
                                [--fill funnel_stage=prospecting,version=1] -o rename-map.csv [--force] [--json]

Standard library only. `make` builds one name per spec row, `audit` reports how the names in an
account are built and what a target schema would be missing, `map` writes a CSV plan of old and new
names per ad. Nothing here renames anything: the map is a file you check and apply yourself.
Every value goes through one rule (slug): lowercase, spaces and underscores become hyphens, other
characters are dropped. The separator and the field order are your choices. The display cap of 8
listed names is an arbitrary default; the account's own names set what is normal, not a benchmark.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

SCHEMA_FIELDS = ("concept", "format", "creator", "ad_type", "product", "tone", "persona", "hook",
                 "funnel_stage", "offer", "market", "version", "launch_date")
PREFERRED_KEYS = {
    "concept": "CONCEPT", "format": "FMT", "creator": "CREATOR", "ad_type": "TYPE", "product": "PRODUCT",
    "tone": "TONE", "persona": "PERSONA", "hook": "HOOK", "funnel_stage": "STAGE", "offer": "OFFER",
    "market": "MKT", "version": "VER", "launch_date": "DATE",
}
DEFAULT_SEP = " | "
UNKNOWN = "unknown"
SHOWN = cm.UNPARSED_SHOWN
PLAN_NOTE = ("This file is a plan: nothing in your ad account has been renamed. "
             "Apply it yourself in Ads Manager (or bulk edit), after checking it.")
MAP_HEADER = ["ad_id", "old_name", "new_name", "missing_fields", "changed"]
_DATE_YMD = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_DATE_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_WHOLE_NUMBER = re.compile(r"^\d+(\.0+)?$")


def parse_fields(text: Optional[str]) -> List[str]:
    """Read "concept,format" into a field list; an unknown or repeated field raises ValueError."""
    fields = [f.strip().lower().replace("-", "_").replace(" ", "_") for f in (text or "").split(",") if f.strip()]
    unknown = [f for f in fields if f not in SCHEMA_FIELDS]
    if unknown:
        raise ValueError("unknown field%s %s; the fields you can use are: %s"
                         % ("s" if len(unknown) > 1 else "", ", ".join(unknown), ", ".join(SCHEMA_FIELDS)))
    if not fields:
        raise ValueError("--fields needs at least one field; choose from: " + ", ".join(SCHEMA_FIELDS))
    if len(set(fields)) != len(fields):
        raise ValueError("--fields lists a field more than once: " + text)
    return fields


def _iso_date(text: str) -> str:
    match = _DATE_YMD.match(text)
    parts = (match.group(1), match.group(2), match.group(3)) if match else None
    if parts is None:
        match = _DATE_DMY.match(text)
        parts = (match.group(3), match.group(2), match.group(1)) if match else None
    try:
        if parts is None:
            raise ValueError
        return dt.date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
    except ValueError:
        raise ValueError("launch_date %r is not a real date; write it as YYYY-MM-DD" % text)


def _clean(text: str) -> str:
    text = re.sub(r"[\s_]+", "-", text.strip().lower())
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9.-]", "", text)).strip("-")


def slug(field: str, value: Any) -> str:
    """The one rule for a name token; "" when there is no value. Raises ValueError for a bad ad type or date."""
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    if field == "launch_date":
        return _iso_date(text)
    if field == "version" and _WHOLE_NUMBER.match(text):
        return "v%d" % int(float(text))
    token = _clean(text)
    if field == "ad_type" and token:
        token = cm.normalise_ad_type(token)
        if token not in cm.AD_TYPES:
            raise ValueError("ad_type %r is not one of the six types: %s" % (text, ", ".join(cm.AD_TYPES)))
    return token.upper() if field == "market" else token


def build_tokens(values: Mapping[str, Any], fields: Sequence[str]) -> Tuple[Dict[str, str], List[str], List[str]]:
    """(token per field with a value, fields with no value, error messages) for one ad or spec row."""
    tokens: Dict[str, str] = {}
    missing: List[str] = []
    errors: List[str] = []
    for field in fields:
        try:
            token = slug(field, values.get(field))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if token:
            tokens[field] = token
        else:
            missing.append(field)
    return tokens, missing, errors


def render_name(fields: Sequence[str], tokens: Mapping[str, str], sep: str, keyed: bool) -> str:
    """Join the tokens in field order; keyed names write KEY:value with the preferred key."""
    return sep.join("%s:%s" % (PREFERRED_KEYS[f], tokens[f]) if keyed else tokens[f] for f in fields)


def parse_back(name: str, fields: Sequence[str], tokens: Mapping[str, str], keyed: bool,
               key_map: Optional[Dict[str, str]], skip: Sequence[str] = ()) -> List[str]:
    """Problems found by reading a made name back with the package's own parser; [] when it round-trips."""
    read = cm.parse_name(name, key_map=key_map) if keyed else cm.parse_name(name, pattern=fields, key_map=key_map)
    problems = []
    for field in fields:
        if field in skip:
            continue
        if read.get(field) != tokens[field]:
            problems.append("will not parse back: %s read as %s" % (field, read.get(field) or "nothing"))
    return problems


def _heading(key: Any) -> str:
    return re.sub(r"[\s-]+", "_", str(key).strip().lower())


def read_specs(path: str) -> List[Dict[str, Any]]:
    """Spec rows from a CSV or JSON file, headings lower-cased with spaces and hyphens as underscores."""
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8-sig") as handle:
            raw = cm.rows_from_response(json.load(handle))
    else:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            raw = list(csv.DictReader(handle))
    return [{_heading(k): v for k, v in row.items() if k is not None} for row in raw]


def make_names(specs: Sequence[Mapping[str, Any]], fields: Sequence[str], sep: str, keyed: bool,
               allow_missing: bool, dedupe: bool, key_map: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Build and check a name per spec row. Raises ValueError listing every row that cannot be named."""
    problems: List[str] = []
    gaps = False
    built = []
    for number, spec in enumerate(specs, start=1):
        tokens, missing, errors = build_tokens(spec, fields)
        problems += ["row %d: %s" % (number, e) for e in errors]
        if missing and not allow_missing:
            gaps = True
            problems.append("row %d is missing: %s" % (number, ", ".join(missing)))
        built.append((number, spec, tokens, missing))
    if problems:
        if gaps:
            problems.append("Fill the gaps, or use --allow-missing to write 'unknown' for them.")
        raise ValueError("\n".join(problems))
    names, warnings = [], []
    used: Dict[str, int] = {}
    for number, spec, tokens, missing in built:
        tokens = dict(tokens, **{f: UNKNOWN for f in missing})
        name = render_name(fields, tokens, sep, keyed)
        if dedupe and name in used:
            target = "version" if "version" in fields else fields[-1]
            count = used[name]
            while True:
                count += 1
                candidate = dict(tokens, **{target: "%s-v%d" % (tokens[target], count)})
                if render_name(fields, candidate, sep, keyed) not in used:
                    break
            used[name] = count
            tokens, name = candidate, render_name(fields, candidate, sep, keyed)
        used.setdefault(name, 1)
        found = parse_back(name, fields, tokens, keyed, key_map, skip=missing)
        warnings += ["row %d: unknown written for %s" % (number, ", ".join(missing))] if missing else []
        warnings += ["row %d: %s" % (number, p) for p in found]
        names.append({"row": number, "ad_id": str(spec.get("ad_id") or "") or None, "name": name,
                      "fields": tokens, "parses_back": not found, "problems": found})
    by_name: Dict[str, List[int]] = {}
    for item in names:
        by_name.setdefault(item["name"], []).append(item["row"])
    for name, rows in by_name.items():
        if len(rows) > 1:
            warnings.append("rows %s share the name %s (add --dedupe to number them)"
                            % (", ".join(map(str, rows)), name))
    return {"names": names, "warnings": warnings}


def write_csv(path: str, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def run_make(args: argparse.Namespace) -> Dict[str, Any]:
    fields = parse_fields(args.fields)
    key_map = cm.parse_key_map(args.key_map) if args.key_map else None
    specs = read_specs(args.path)
    if not specs:
        raise ValueError("no rows found in %s" % args.path)
    if args.output and os.path.exists(args.output) and not args.force:
        raise ValueError("%s already exists; choose another -o or add --force to overwrite it" % args.output)
    result = make_names(specs, fields, args.sep, args.keyed, args.allow_missing, args.dedupe, key_map)
    result["settings"] = {"fields": fields, "sep": args.sep, "keyed": args.keyed,
                          "allow_missing": args.allow_missing, "dedupe": args.dedupe, "key_map": key_map}
    if args.output:
        write_csv(args.output, ["ad_id", "name"], [(n["ad_id"] or "", n["name"]) for n in result["names"]])
    return result


def render_make(result: Mapping[str, Any], output: Optional[str]) -> str:
    out = ["Wrote %d names to %s." % (len(result["names"]), output)] if output else [n["name"] for n in result["names"]]
    if result["warnings"]:
        out += ["", "Check these:"] + ["  " + w for w in result["warnings"]]
    return "\n".join(out)


def _plural(count: int, word: str) -> str:
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def read_rows(path: str) -> List[Dict[str, Any]]:
    """Rows from a CSV or JSON export, or {"ad_name": line} per line of a text file."""
    if path.lower().endswith((".csv", ".json")):
        return cm.load_rows(path, level="ad")
    with open(path, encoding="utf-8-sig") as handle:
        return [{"ad_name": line.strip()} for line in handle if line.strip()]


def audit_names(rows: Sequence[Mapping[str, Any]], fields: Sequence[str],
                key_map: Optional[Dict[str, str]]) -> Dict[str, Any]:
    names = list(dict.fromkeys(r["ad_name"] for r in rows if r.get("ad_name")))
    if not names:
        raise ValueError("no ad names found")
    found = cm.detect_convention(names, key_map=key_map)
    learned = cm.learn_names(names, key_map)
    read = {n: cm.parse_name(n, key_map=key_map, learned=learned) for n in names}
    total = len(names)
    target = {}
    for field in fields:
        lacking = [n for n in names if not read[n].get(field)]
        target[field] = {"count": total - len(lacking), "share": 100.0 * (total - len(lacking)) / total,
                         "missing_count": len(lacking), "missing_names": lacking[:SHOWN]}
    scarce = [f for f, t in target.items() if t["count"] * 2 < total]
    ids: Dict[str, set] = {}
    for row in rows:
        if row.get("ad_name") and row.get("ad_id"):
            ids.setdefault(row["ad_name"], set()).add(row["ad_id"])
    duplicates = [{"name": n, "ad_ids": sorted(v)} for n, v in ids.items() if len(v) > 1]
    folded: Dict[str, List[str]] = {}
    for name in names:
        folded.setdefault(re.sub(r"\s+", "", name.lower()), []).append(name)
    variants = [v for v in folded.values() if len(v) > 1]
    verdict = "%.0f%% of %d names follow one convention" % (found["match_rate"], total)
    if fields:
        verdict += ("; %s %s missing from most names." % (_plural(len(scarce), "target field"),
                                                           "is" if len(scarce) == 1 else "are")
                    if scarce else "; every target field is on most names.")
    else:
        verdict += "."
    style = found["conventions"][0]["style"] if found["conventions"] else None
    return {"verdict": verdict, "names": total, "match_rate": found["match_rate"], "separator": found["separator"],
            "style": style, "coexisting": found["coexisting"], "fields_read": found["fields"], "target": target,
            "duplicate_names": duplicates, "case_or_spacing_variants": variants}


def render_audit(result: Mapping[str, Any]) -> str:
    out = [result["verdict"], ""]
    out.append("Separator: %s%s. Names read: %.0f%% of %d."
               % (repr(result["separator"]) if result["separator"] else "none found",
                  " (%s)" % result["style"] if result["style"] else "", result["match_rate"], result["names"]))
    if result["coexisting"]:
        out.append("A second naming style is also in use.")
    if result["fields_read"]:
        out += ["", "Fields read from the names:"]
        out += ["  %s: %d of %d names (%.0f%%)" % (f, v["count"], result["names"], v["coverage"])
                for f, v in result["fields_read"].items()]
    if result["target"]:
        out += ["", "Target fields:"]
        for field, info in result["target"].items():
            line = "  %s: on %d of %d names (%.0f%%)" % (field, info["count"], result["names"], info["share"])
            out.append(line)
            if info["missing_count"]:
                out += ["      lacks it: " + n for n in info["missing_names"]]
                extra = info["missing_count"] - len(info["missing_names"])
                out += ["      ... %d more" % extra] if extra > 0 else []
    if result["duplicate_names"]:
        out += ["", "Names used by more than one ad id:"]
        out += ["  %s (ads %s)" % (d["name"], ", ".join(d["ad_ids"])) for d in result["duplicate_names"][:SHOWN]]
        if len(result["duplicate_names"]) > SHOWN:
            out.append("  ... %d more" % (len(result["duplicate_names"]) - SHOWN))
    if result["case_or_spacing_variants"]:
        out += ["", "Names that differ only by case or spacing (likely the same ad named twice):"]
        out += ["  " + "  /  ".join(v) for v in result["case_or_spacing_variants"][:SHOWN]]
        if len(result["case_or_spacing_variants"]) > SHOWN:
            out.append("  ... %d more" % (len(result["case_or_spacing_variants"]) - SHOWN))
    return "\n".join(out)


def parse_fill(text: Optional[str], fields: Sequence[str]) -> Dict[str, str]:
    """Read "funnel_stage=prospecting,version=1" into checked tokens for fields in the schema."""
    fill = {}
    for pair in (text or "").split(","):
        if not pair.strip():
            continue
        field, sep, value = pair.partition("=")
        field = field.strip().lower()
        if not sep or not value.strip():
            raise ValueError("bad --fill entry %r: write field=value, for example funnel_stage=prospecting" % pair)
        if field not in fields:
            raise ValueError("--fill names %s, which is not in --fields (%s)" % (field, ", ".join(fields)))
        fill[field] = slug(field, value) or UNKNOWN
    return fill


def map_names(ads: Sequence[Mapping[str, Any]], fields: Sequence[str], sep: str, keyed: bool,
              fill: Mapping[str, str], key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    rows, problems = [], []
    for ad in ads:
        tokens, missing, errors = build_tokens(ad, fields)
        problems += ["ad %s: %s" % (ad["ad_id"], e) for e in errors]
        for field in [f for f in missing if f in fill]:
            tokens[field] = fill[field]
        missing = [f for f in missing if f not in fill]
        tokens.update({f: UNKNOWN for f in missing})
        new = render_name(fields, tokens, sep, keyed)
        old = ad.get("ad_name") or ""
        rows.append({"ad_id": ad["ad_id"], "old_name": old, "new_name": new, "missing_fields": missing,
                     "changed": new != old, "problems": parse_back(new, fields, tokens, keyed, key_map, skip=missing)})
    if problems:
        raise ValueError("\n".join(problems))
    return rows


def summarise_map(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_new: Dict[str, int] = {}
    for row in rows:
        by_new[row["new_name"]] = by_new.get(row["new_name"], 0) + 1
    shared = {n: c for n, c in by_new.items() if c > 1}
    missing: Dict[str, int] = {}
    for row in rows:
        for field in row["missing_fields"]:
            missing[field] = missing.get(field, 0) + 1
    return {"ads": len(rows), "changed": sum(1 for r in rows if r["changed"]),
            "ads_with_missing_fields": sum(1 for r in rows if r["missing_fields"]), "missing_by_field": missing,
            "colliding_names": len(shared), "colliding_ads": sum(shared.values()),
            "unparseable": sum(1 for r in rows if r["problems"]),
            "first_problem": next(("%s: %s" % (r["new_name"], r["problems"][0]) for r in rows if r["problems"]), None)}


def render_map(summary: Mapping[str, Any], output: str, notes: Sequence[str]) -> str:
    out = list(notes)
    out.append("%s read; %d of their names change." % (_plural(summary["ads"], "ad"), summary["changed"]))
    if summary["missing_by_field"]:
        out.append("%s have fields no name carries, written as 'unknown': %s. Use --fill to give them a value."
                   % (_plural(summary["ads_with_missing_fields"], "ad"),
                      ", ".join("%s (%d)" % kv for kv in summary["missing_by_field"].items())))
    else:
        out.append("Every field has a value for every ad.")
    out.append("New names that collide: %d (%s share a name)."
               % (summary["colliding_names"], _plural(summary["colliding_ads"], "ad")))
    if summary["unparseable"]:
        out.append("%s will not parse back with this separator (%s): pick a separator no field value contains."
                   % (_plural(summary["unparseable"], "new name"), summary["first_problem"]))
    out += ["Wrote " + output + ".", PLAN_NOTE]
    return "\n".join(out)


def run_map(args: argparse.Namespace) -> Dict[str, Any]:
    fields = parse_fields(args.fields)
    fill = parse_fill(args.fill, fields)
    if os.path.exists(args.output) and not args.force:
        raise ValueError("%s already exists; choose another -o or add --force to overwrite it" % args.output)
    rows, key_map, notes = cm.prepare_run(args, read_rows(args.path))
    ads = cm.aggregate_by_ad(rows, key_map)
    if not ads or any(not ad["ad_id"] for ad in ads):
        raise ValueError("map needs an ad id for every ad: export with the Ad ID column")
    result_rows = map_names(ads, fields, args.sep, args.keyed, fill, key_map)
    write_csv(args.output, MAP_HEADER, [(r["ad_id"], r["old_name"], r["new_name"], ";".join(r["missing_fields"]),
                                         "yes" if r["changed"] else "no") for r in result_rows])
    return {"rows": result_rows, "summary": summarise_map(result_rows), "output": args.output, "notes": notes,
            "settings": {"fields": fields, "sep": args.sep, "keyed": args.keyed, "fill": fill,
                         "key_map": key_map, "where": args.where}}


def run_audit(args: argparse.Namespace) -> Dict[str, Any]:
    fields = parse_fields(args.fields) if args.fields else []
    rows, key_map, notes = cm.prepare_run(args, read_rows(args.path))
    result = audit_names(rows, fields, key_map)
    result["notes"] = notes
    result["settings"] = {"fields": fields, "key_map": key_map, "where": args.where}
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Make ad names to a schema, audit existing names, write a rename map.")
    sub = parser.add_subparsers(dest="command", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    shared.add_argument("--json", action="store_true", help="print JSON instead of text")
    fields_help = "comma-separated schema fields in name order, from: " + ", ".join(SCHEMA_FIELDS)

    def schema(p: argparse.ArgumentParser, required: bool) -> None:
        p.add_argument("--fields", required=required, help=fields_help)

    def style(p: argparse.ArgumentParser) -> None:
        p.add_argument("--sep", help='separator between segments (default: " | ", the package convention)')
        p.add_argument("--keyed", action="store_true", help="write KEY:value segments, e.g. CONCEPT:durability-test")

    make = sub.add_parser("make", parents=[shared], help="build names from a CSV or JSON of specs")
    make.add_argument("path", help="specs CSV or JSON: one row per ad, columns are field names, optional ad_id")
    schema(make, True)
    style(make)
    make.add_argument("--allow-missing", action="store_true", help="write 'unknown' for a missing value and warn")
    make.add_argument("--dedupe", action="store_true",
                      help="number duplicate names: -v2, -v3 ... on the version, else on the last field")
    make.add_argument("-o", "--output", help="write a CSV of ad_id,name instead of printing the names")
    make.add_argument("--force", action="store_true", help="overwrite the output file if it exists")

    audit = sub.add_parser("audit", parents=[shared], help="report how existing names are built")
    audit.add_argument("path", help="Ads Manager CSV, .json rows, or a .txt with one name per line")
    schema(audit, False)
    cm.add_run_arguments(audit)

    plan = sub.add_parser("map", parents=[shared], help="write an old -> new rename map as a CSV")
    plan.add_argument("path", help="Ads Manager CSV or .json rows with an ad id")
    schema(plan, True)
    style(plan)
    plan.add_argument("--fill", help="value for a field no name carries, e.g. funnel_stage=prospecting,version=1")
    plan.add_argument("-o", "--output", required=True, help="rename map CSV to write, e.g. rename-map.csv")
    plan.add_argument("--force", action="store_true", help="overwrite the output file if it exists")
    cm.add_run_arguments(plan)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "sep", None) is None:
        args.sep = DEFAULT_SEP
    try:
        if args.command == "make":
            result = run_make(args)
            text = render_make(result, args.output)
        elif args.command == "audit":
            result = run_audit(args)
            text = "\n".join(list(result["notes"]) + [render_audit(result)])
        else:
            result = run_map(args)
            text = render_map(result["summary"], args.output, result["notes"])
    except (OSError, ValueError, csv.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
