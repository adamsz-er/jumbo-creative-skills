#!/usr/bin/env python3
"""Test how ad names are structured, against every name, and report the match rate.

Usage: python3 detect_naming.py names.txt|ads.csv|rows.json [--key-map PX=concept,...]
                                [--min-match-rate 85] [--json]

Standard library only. Reads one name per line from a text file, or the ad names
from an Ads Manager CSV or a .json file of rows. Prints plain English first, then
a table of fields and their coverage, then the names that could not be read. The
85 percent line below which the user is asked, and the 5 percent share at which a
second convention counts as coexisting, are arbitrary defaults: set them from how
tidy your account's names are.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402


def read_names(path: str) -> List[str]:
    """Ad names from a .csv or .json export (unique, in order), else one per line."""
    if path.lower().endswith((".csv", ".json")):
        rows = cm.load_rows(path, level="ad")
        seen = {}
        for row in rows:
            if row.get("ad_name"):
                seen.setdefault(row["ad_name"], None)
        return list(seen)
    with open(path, encoding="utf-8-sig") as handle:
        return [line.strip() for line in handle if line.strip()]


def render(found: dict) -> str:
    out = [found["description"], ""]
    if found["ask"]:
        out.append("Ask the user to confirm before tagging ads from names: " + "; ".join(found["ask_reasons"]) + ".")
    else:
        out.append("No need to ask the user: %.0f%% of names read is at or above the %g%% line "
                   "(an arbitrary, user-settable default), and no second convention is in wide use."
                   % (found["match_rate"], found["min_match_rate"]))
    if found["coexisting"] and not found["ask"]:
        out.append("A second style appears in a few names (listed under unparsed or counted above): carry on.")
    out.append("")
    if found["fields"]:
        header = ["field", "names", "coverage%", "read from"]
        lines = [[f, str(v["count"]), "%.0f" % v["coverage"], v["source"]] for f, v in found["fields"].items()]
        widths = [max(len(header[i]), *(len(r[i]) for r in lines)) for i in range(4)]
        out.append("  ".join(h.ljust(w) for h, w in zip(header, widths)))
        out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in lines]
        out.append("")
    if found["keys"]:
        out.append("KEY:value keys seen: " + ", ".join("%s -> %s (%d)" % (k, v["field"], v["count"])
                                                       for k, v in sorted(found["keys"].items())))
    for key, info in sorted(found["inferred_keys"].items()):
        if info["share"] is None:
            out.append("Key %s read as %s: %s; the key is in %.0f%% of names (override with --key-map %s=field)."
                       % (key, info["field"], info["basis"], info["coverage"], key))
        else:
            out.append("Key %s read as %s because %.0f%% of its %d values are %s; the key is in %.0f%% of names "
                       "(override with --key-map %s=field)."
                       % (key, info["field"], info["share"], info["count"], info["basis"], info["coverage"], key))
    if found["concept_candidates"]:
        out.append("No key was read as the concept. Any of these could be it: %s. Ask the user ONE question: "
                   "which of them is the concept (then pass --key-map KEY=concept)."
                   % ", ".join(found["concept_candidates"]))
    plain = {k: n for k, n in found["unknown_keys"].items() if k not in found["inferred_keys"]}
    if plain:
        out.append("Keys with no clear meaning (kept under their own name; map them with --key-map KEY=field): "
                   + ", ".join("%s (%d)" % kv for kv in sorted(plain.items())))
    issues = found["date_issues"]
    if issues["ambiguous_count"]:
        out.append("%d dates left unlabelled because day and month could swap and no name settles it (e.g. %s). "
                   "Ask the user which order the account uses."
                   % (issues["ambiguous_count"], ", ".join(issues["ambiguous"])))
    if issues["unparseable_count"]:
        out.append("%d date-like segments are not real dates and were left unlabelled (e.g. %s)."
                   % (issues["unparseable_count"], ", ".join(issues["unparseable"])))
    if found["ad_types"]:
        out.append("Ad types: " + ", ".join("%s (%d)" % kv for kv in sorted(found["ad_types"].items())))
    if found["unknown_ad_types"]:
        out.append("Ad types not among the six known: " + ", ".join("%s (%d)" % kv for kv in sorted(found["unknown_ad_types"].items()))
                   + ". Ask the user which type each one is, in one question listing them. Never drop them.")
    if found["unlabelled"]:
        out.append("Unlabelled segments left as positional: " + "; ".join(
            "position %d (%d names, e.g. %s)" % (u["position"], u["count"], ", ".join(u["examples"]))
            for u in found["unlabelled"]))
    out.append("")
    if found["unparsed_count"]:
        out.append("Unparsed / odd names (%d, first %d shown):" % (found["unparsed_count"], len(found["unparsed"])))
        out += ["  " + n for n in found["unparsed"]]
    else:
        out.append("Unparsed / odd names: none.")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detect the naming convention in a set of ad names.")
    parser.add_argument("path", help="text file (one name per line), Ads Manager CSV, or .json rows")
    parser.add_argument("--key-map", help="extra KEY=field pairs, e.g. PX=concept")
    parser.add_argument("--min-match-rate", type=float, default=cm.MATCH_RATE_ASK,
                        help="ask the user below this percent of names read (arbitrary default; set from your account)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a report")
    parser.add_argument("--profile", help="creative-profile.md: its Script settings block (key-map, type-map) fills "
                                          "any flag left unset, so a confirmed answer is never asked again")
    parser.add_argument("--type-map", help="the account's own ad-type words, e.g. core=bau")
    args = parser.parse_args(argv)
    try:
        if args.profile:
            cm.apply_settings(args, args.profile)
        cm.set_type_map(cm.parse_type_map(args.type_map) if args.type_map else None)
        key_map = cm.parse_key_map(args.key_map) if args.key_map else None
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    names = read_names(args.path)
    if not names:
        print("no ad names found in %s" % args.path, file=sys.stderr)
        return 2
    found = cm.detect_convention(names, key_map=key_map, min_match_rate=args.min_match_rate)
    print(json.dumps(found, indent=2) if args.json else render(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
