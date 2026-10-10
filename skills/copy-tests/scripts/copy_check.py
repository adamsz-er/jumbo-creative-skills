#!/usr/bin/env python3
"""Check a copy test's variants: length, one variable at a time, and a persona and hook on every row.

Usage: python3 copy_check.py variants.csv [--limits primary_text=150,headline=27] [--json]

Standard library only. The CSV has the columns test, variant, persona, hook, field, text, changed: one row
per field (primary_text, headline or description) of a variant, and each test has one variant named
"control". Checks, each reported per row with the rule's name: length-limit, one-variable, persona-and-hook,
and control. The default limits are Meta's published text recommendations for Facebook Feed image and video
ads (the top of Meta's primary-text range and its headline length; checked 2026-10-10 at
https://www.facebook.com/business/ads-guide/update/image/facebook-feed and
https://www.facebook.com/business/ads-guide/update/video/facebook-feed). Meta changes these: check the
current spec. They are Meta's guidance, not a rule of this package; the spec gives no description limit, so a
description is checked only if you pass one with --limits. Characters are counted as the length of the text
after stripping spaces. Exit 0 when every check passes, 1 when any fails, 2 on unreadable input.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

COLUMNS = ("test", "variant", "persona", "hook", "field", "text", "changed")
FIELDS = ("primary_text", "headline", "description")
ONE_VARIABLE = ("persona", "hook") + FIELDS
DEFAULT_LIMITS = "primary_text=150,headline=27"
CONTROL = "control"
NO_GUIDANCE = "no published guidance: check your placement preview"


def parse_limits(text: str) -> Dict[str, int]:
    """Read "primary_text=150,headline=27" into {"primary_text": 150, "headline": 27}."""
    limits = {}
    for part in (p.strip() for p in text.split(",") if p.strip()):
        field, sep, value = part.partition("=")
        if not sep or field.strip() not in FIELDS or not value.strip().isdigit():
            raise ValueError("bad --limits %r: write field=characters for field in %s, e.g. headline=27"
                             % (part, ", ".join(FIELDS)))
        limits[field.strip()] = int(value)
    return limits


def read_variants(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("variants CSV is missing column(s): %s" % ", ".join(missing))
        rows = []
        for record in reader:
            if None in record:
                raise ValueError("line %d has more fields than the header (%d): quote any text that contains a comma"
                                 % (reader.line_num, len(COLUMNS)))
            row = {c: (record.get(c) or "").strip() for c in COLUMNS}
            if row["changed"] and row["changed"] not in ONE_VARIABLE:
                raise ValueError("line %d: changed must be empty or one of %s, not %r"
                                 % (reader.line_num, ", ".join(ONE_VARIABLE), row["changed"]))
            rows.append(row)
    if not rows:
        raise ValueError("variants CSV has no rows")
    for row in rows:
        if row["field"] not in FIELDS:
            raise ValueError("field must be one of %s, not %r (test %s, variant %s)"
                             % (", ".join(FIELDS), row["field"], row["test"], row["variant"]))
    return rows


def _finding(rule: str, row: Dict[str, str], status: str, message: str) -> Dict[str, str]:
    return {"rule": rule, "test": row["test"], "variant": row["variant"], "field": row["field"],
            "status": status, "message": message}


def check_length(row: Dict[str, str], limits: Dict[str, int]) -> Dict[str, str]:
    length, field = len(row["text"]), row["field"]
    limit = limits.get(field)
    if limit is None:
        return _finding("length-limit", row, "note", NO_GUIDANCE)
    if length > limit:
        return _finding("length-limit", row, "fail",
                        "over by %d characters (Meta's guidance, not a rule of this package)" % (length - limit))
    return _finding("length-limit", row, "pass", "%d of %d characters" % (length, limit))


def check_persona_hook(row: Dict[str, str]) -> Dict[str, str]:
    empty = [c for c in ("persona", "hook") if not row[c]]
    if empty:
        return _finding("persona-and-hook", row, "fail", "%s is empty: tie the variant to a persona and a hook"
                        % " and ".join(empty))
    return _finding("persona-and-hook", row, "pass", "persona and hook filled")


def _fields_of(rows: Sequence[Dict[str, str]]) -> Dict[str, str]:
    """persona, hook and the three text fields of one variant (a field it has no row for reads as empty)."""
    values = {f: "" for f in ONE_VARIABLE}
    for row in rows:
        values["persona"] = values["persona"] or row["persona"]
        values["hook"] = values["hook"] or row["hook"]
        values[row["field"]] = row["text"]
    return values


def check_one_variable(test: str, variant: str, rows: Sequence[Dict[str, str]],
                       control: Dict[str, str]) -> Dict[str, str]:
    values = _fields_of(rows)
    differs = [f for f in ONE_VARIABLE if values[f] != control[f]]
    anchor = {"test": test, "variant": variant, "field": "all"}
    if not differs:
        return _finding("one-variable", anchor, "fail", "same as control: tests nothing")
    if len(differs) > 1:
        return _finding("one-variable", anchor, "fail", "changes %d things (%s): a result could not say which one "
                        "mattered" % (len(differs), ", ".join(differs)))
    claimed = next((r["changed"] for r in rows if r["changed"]), "")
    if claimed != differs[0]:
        return _finding("one-variable", anchor, "fail", "changed column says %s but %s differs"
                        % (claimed or "nothing", differs[0]))
    return _finding("one-variable", anchor, "pass", "changes only %s" % differs[0])


def check_variants(rows: Sequence[Dict[str, str]], limits: Dict[str, int]) -> List[Dict[str, str]]:
    """Every finding, one per rule per row (or per variant for one-variable) and per test for control."""
    findings: List[Dict[str, str]] = []
    tests: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
    for row in rows:
        tests.setdefault(row["test"], {}).setdefault(row["variant"], []).append(row)
        findings.append(check_length(row, limits))
        findings.append(check_persona_hook(row))
    for test, variants in tests.items():
        anchor = {"test": test, "variant": CONTROL, "field": "all"}
        if CONTROL not in variants:
            findings.append(_finding("control", anchor, "fail", "no control variant: name one variant \"control\""))
            continue
        others = [v for v in variants if v != CONTROL]
        if not others:
            findings.append(_finding("control", anchor, "fail", "no variant to test"))
            continue
        control = _fields_of(variants[CONTROL])
        for variant in others:
            findings.append(check_one_variable(test, variant, variants[variant], control))
    return findings


def render(findings: Sequence[Dict[str, str]]) -> str:
    failed = [f for f in findings if f["status"] == "fail"]
    notes = [f for f in findings if f["status"] == "note"]
    head = ("%d check(s) failed." % len(failed)) if failed else "Every check passed."

    def line(f: Dict[str, str]) -> str:
        return "- [%s] test %s, variant %s, %s: %s" % (f["rule"], f["test"], f["variant"], f["field"], f["message"])

    lines = [head]
    if failed:
        lines += ["", "Failures:"] + [line(f) for f in failed]
    if notes:
        lines += ["", "Notes:"] + [line(f) for f in notes]
    lines += ["", "Checked %d things. Length limits are Meta's guidance (check the current spec), not a rule of "
              "this package." % len(findings)]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check a copy test's variants.")
    parser.add_argument("path", help="variants CSV: test, variant, persona, hook, field, text, changed")
    parser.add_argument("--limits", default=DEFAULT_LIMITS,
                        help="field=characters pairs (default %s: Meta's published text guidance for Facebook Feed, "
                             "checked 2026-10-10; Meta changes these, check the current spec)" % DEFAULT_LIMITS)
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    try:
        limits = parse_limits(args.limits)
        findings = check_variants(read_variants(args.path), limits)
    except (OSError, ValueError, csv.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    failed = any(f["status"] == "fail" for f in findings)
    if args.json:
        print(json.dumps({"settings": {"limits": limits}, "passed": not failed, "findings": findings}, indent=2))
    else:
        print(render(findings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
