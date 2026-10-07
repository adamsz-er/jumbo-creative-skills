#!/usr/bin/env python3
"""Draft creative-profile.md from the ads alone: only facts the data shows.

Usage: python3 profile_draft.py ads.csv [--name "Acme"] [--currency USD] [-o creative-profile.md]

Standard library only. The draft follows creative-context/references/brand-profile-template.md.
It fills formats, ad types, concepts, markets, naming style and its match rate,
the window and the currency from the data, and writes "not stated" for everything
only the brand can say: voice, offers, personas, calendar, constraints.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

NOT_STATED = "not stated"
LISTED = 8  # most values listed per field; arbitrary display cap


def _tally(values: Sequence[Any]) -> str:
    counts = Counter(str(v) for v in values if v not in (None, "", "unknown"))
    if not counts:
        return NOT_STATED
    shown = ", ".join("%s (%d)" % kv for kv in counts.most_common(LISTED))
    if len(counts) > LISTED:
        return "%d distinct, the most used: %s" % (len(counts), shown)
    return shown


def account_name(rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    """The account name a data column carries (`account_name`, `Account name`), if any row has one."""
    for row in rows:
        for key, value in row.items():
            if re.sub(r"[^a-z]", "", str(key).lower()) == "accountname" and str(value or "").strip():
                return str(value).strip()
    return None


def draft(rows: Sequence[Dict[str, Any]], names: Sequence[str], name: Optional[str] = None,
          currency: Optional[str] = None) -> str:
    """The profile as markdown. `names` are the distinct ad names the naming style is tested against."""
    ads = cm.aggregate_by_ad(rows)
    found = cm.detect_convention(list(names)) if names else None
    start, end = cm.data_window(rows)
    window = "%s to %s" % (start, end) if start else "n/a (no dates)"
    objectives = _tally([a.get("objective") for a in ads])
    sources = sorted({r["conversions_source"] for r in rows if r.get("conversions_source")})
    if found:
        naming = "%d of %d ad names read (%.0f%%): %s" % (
            round(found["match_rate"] * len(names) / 100), len(names), found["match_rate"],
            ", ".join(found["fields"]) or "no fields found")
        key_map = ",".join("%s=%s" % (k, v["field"]) for k, v in sorted(found["inferred_keys"].items()))
    else:
        naming, key_map = "no ad names to read", ""
    lines: List[str] = [
        "# Creative profile: %s" % (name or "unknown"),
        "",
        "Drafted from the ad data only. Everything marked \"%s\" is for the brand to fill in." % NOT_STATED,
        "",
        "## Brand",
        "- Name: %s" % (name or "unknown"),
        "- Category: %s" % NOT_STATED,
        "- Brand tone (3 to 5 words, plus words to avoid): %s" % NOT_STATED,
        "- Colours and type: %s" % NOT_STATED,
        "",
        "## Products",
        "- Hero products or collections: %s" % NOT_STATED,
        "",
        "## Offers and calendar",
        "- Standing offers: %s" % NOT_STATED,
        "- Sale and launch calendar for the next 90 days: %s" % NOT_STATED,
        "",
        "## Personas",
        "- Persona 1: %s" % NOT_STATED,
        "",
        "## Funnel and goals",
        "- Primary goal: %s" % NOT_STATED,
        "- Objectives in the data: %s" % objectives,
        "- Markets or regions: %s" % _tally([a.get("market") for a in ads]),
        "- Formats in use: %s" % _tally([a.get("format") for a in ads]),
        "- Ad types in use: %s" % _tally([a.get("ad_type") for a in ads]),
        "- Concepts in use: %s" % _tally([a.get("concept") for a in ads]),
        "",
        "## Data",
        "- Mode: csv",
        "- Window and currency: %s, %s" % (window, currency or NOT_STATED),
        "- Conversions column used: %s" % (", ".join(sources) or NOT_STATED),
        "- Naming convention: %s" % naming,
        "- Store revenue available for MER: %s" % NOT_STATED,
        "",
        "## Script settings",
        "- key-map:" + (" " + key_map if key_map else ""),
        "- type-map:",
        "- target:",
        "- currency:" + (" " + currency if currency else ""),
        "",
        "## Constraints",
        "- Claims that need approval or are not allowed: %s" % NOT_STATED,
        "- Approval owner: %s" % NOT_STATED,
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Draft creative-profile.md from the ad data alone.")
    parser.add_argument("path", help="Ads Manager CSV, or a .json file of rows")
    parser.add_argument("--name", help="the brand name, if you know it")
    parser.add_argument("--currency", help="three-letter currency code; default: read from the export's spend header")
    parser.add_argument("-o", "--output", help="write the draft here instead of printing it")
    args = parser.parse_args(argv)
    rows = cm.load_rows(args.path)
    names = sorted({str(r["ad_name"]) for r in rows if r.get("ad_name")})
    text = draft(rows, names, name=args.name or account_name(rows), currency=args.currency or cm.detect_currency(args.path))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print("wrote %s" % args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
