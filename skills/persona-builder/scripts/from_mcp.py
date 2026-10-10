#!/usr/bin/env python3
"""Turn saved Meta Ads MCP responses into one CSV the analysis scripts read, and check the pull is complete.

Usage: python3 from_mcp.py rows.json [more.json ...] -o ads.csv
           [--expect-spend X] [--expect-impressions Y] [--expect-ads ids.txt] [--tolerance 0.5]

Standard library only. Each input is a saved connector response: a list of rows,
or an object with a "data", "rows" or "ad_entities" list (the connector sends
"ad_entities" as a JSON string, which is decoded). Anything the connector says
beside its rows (`additional_info`, for example fields it refused) is printed,
and so is every expected field that no row carries. Rows are mapped to the canonical
fields by creative_metrics.load_rows, merged, and de-duplicated on (ad id, date)
with the last copy kept. The connector can stop a long pull partway or cap a
batch silently, so give the account-level totals for the same window: a short
pull prints a WARNING line first and exits 3. The tolerance (percent of the
expected total) is an arbitrary default: set it from how closely your own totals
should reconcile.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

EXIT_SHORT = 3
EXIT_MIXED = 4
DEFAULT_TOLERANCE = 0.5

# CSV header -> row field. The headers are the Ads Manager names the loader already reads.
COLUMNS = (
    ("Day", "date"), ("Ad name", "ad_name"), ("Ad ID", "ad_id"),
    ("Amount spent", "spend"), ("Impressions", "impressions"), ("Reach", "reach"),
    ("Link clicks", "link_clicks"), ("Clicks (all)", "clicks"),
    ("3-second video plays", "video_views_3s"), ("video_views_3s_source", "video_views_3s_source"),
    ("ThruPlays", "video_thruplay"), ("Adds to cart", "add_to_carts"),
    ("Purchases", "conversions"), ("Purchases conversion value", "conversion_value"), ("Leads", "leads"),
    ("created_time", "created_time"), ("objective", "objective"), ("market", "market"),
    ("campaign_name", "campaign_name"),
)


# Fields the analysis reads when the pull has them; one that no row carries is named in the output.
EXPECTED_FIELDS = (("link_clicks", "link clicks"), ("conversions", "purchases"),
                   ("conversion_value", "purchase value"), ("video_thruplay", "ThruPlays"),
                   ("video_views_3s", "3-second plays"), ("created_time", "created time (ad age)"),
                   ("objective", "objective"))


def read_responses(paths: Sequence[str], notes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """The raw rows of every saved response, in file order; each response's own notes go into `notes`."""
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8-sig") as handle:
            loaded = json.load(handle)
        try:
            rows.extend(cm.rows_from_response(loaded))
        except ValueError as error:
            raise ValueError("%s: %s" % (path, error))
        if notes is not None:
            notes.extend("%s: %s" % (Path(path).name, note) for note in cm.response_notes(loaded))
    return rows


def fill_market(rows: Sequence[Dict[str, Any]]) -> None:
    """Fill each row's empty market from its ad name, read against all the names in the pull."""
    names = sorted({str(r["ad_name"]) for r in rows if r.get("ad_name")})
    learned = cm.learn_names(names)
    markets = {n: cm.parse_name(n, learned=learned, require_read=False).get("market") for n in names}
    for row in rows:
        if not row.get("market") and row.get("ad_name"):
            row["market"] = markets.get(str(row["ad_name"]))


def absent_fields(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """The expected fields that no row carries, in words; 3-second plays count as present when refused for a reason."""
    absent = []
    for field, words in EXPECTED_FIELDS:
        if any(r.get(field) not in (None, "") for r in rows):
            continue
        refused = next((r["video_views_3s_source"] for r in rows if field == "video_views_3s"
                        and str(r.get("video_views_3s_source", "")).startswith("not derived")), None)
        absent.append("%s (%s)" % (words, refused) if refused else words)
    return absent


CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


def money_units(raw: Dict[str, Any]) -> Dict[str, str]:
    """{"spend": "USD", ...}: the currency code each money field of a raw row states ({"value": ..., "unit": "USD"}).

    A unit that is not a three-letter code is treated as no unit.
    """
    found = {}
    for key, value in raw.items():
        field = cm.money_field(key) if isinstance(value, dict) else None
        unit = str(value.get("unit") or "").strip().upper() if field else ""
        if CURRENCY_CODE.match(unit):
            found.setdefault(field, unit)
    return found


def spend_currency(rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    """The one currency every spending row states, else None (some row states none, or the units differ)."""
    units = {r.get("spend_unit") for r in rows if r.get("spend") is not None}
    return next(iter(units)) if len(units) == 1 and None not in units else None


def all_units(raw_rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Every distinct currency code the raw rows state on any money field, sorted."""
    return sorted({u for r in raw_rows for u in money_units(r).values()})


def rows_without_unit(raw_rows: Sequence[Dict[str, Any]]) -> int:
    """How many raw rows with spend state no currency for it."""
    return sum(1 for r in raw_rows if any(cm.money_field(k) == "spend" for k in r) and "spend" not in money_units(r))


def merge(raw_rows: Sequence[Dict[str, Any]], level: Optional[str] = "ad") -> List[Dict[str, Any]]:
    """Normalise rows and keep the last copy of each (ad id, date), or (ad id, window end) for undated rows.

    A row whose spend states a currency keeps it as `spend_unit`.

    A row with an ad but neither a date nor a window end cannot be told apart from
    a repeat of itself, so it raises ValueError rather than risk double counting.
    """
    merged: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for position, (raw, row) in enumerate(zip(raw_rows, cm.load_rows(raw_rows, level=level))):
        unit = money_units(raw).get("spend")
        if unit:
            row["spend_unit"] = unit
        ad_id = row.get("ad_id") or row.get("ad_name")
        if not ad_id:
            merged[("row", position)] = row
            continue
        day = row.get("date") or row.get("date_stop")
        if not day:
            raise ValueError("row %d (ad %s) has no date or date_stop: cannot de-duplicate it" % (position, ad_id))
        merged[(ad_id, day)] = row
    return list(merged.values())


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(round(value, 6))
    return str(value)


def write_csv(rows: Sequence[Dict[str, Any]], path: str) -> None:
    """Write the CSV; the spend header carries the currency ("Amount spent (USD)") when every row states the same one."""
    currency = spend_currency(rows)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["%s (%s)" % (header, currency) if field == "spend" and currency else header for header, field in COLUMNS])
        for row in rows:
            writer.writerow([_cell(row.get(field)) for _, field in COLUMNS])


def _total(rows: Sequence[Dict[str, Any]], field: str) -> float:
    return sum(r[field] for r in rows if r.get(field) is not None)


def summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    start, end = cm.data_window(rows)
    return {"rows": len(rows), "ads": sorted({r["ad_id"] for r in rows if r.get("ad_id")}),
            "start": start, "end": end,
            "spend": _total(rows, "spend"), "impressions": _total(rows, "impressions")}


def _shortfall(label: str, pulled: float, expected: Optional[float], tolerance: float) -> Optional[str]:
    """A shortfall line, or None when the pull is within tolerance (or nothing was expected)."""
    if expected is None or expected <= 0:
        return None
    gap = expected - pulled
    percent = gap / expected * 100
    if -percent > tolerance:
        return "%s over-counted: likely duplicate rows or overlapping windows (%.2f, %.2f%% above the expected %.2f; " \
               "tolerance %.2f%%)" % (label, -gap, -percent, expected, tolerance)
    if percent <= tolerance:
        return None
    return "%s short by %.2f (%.2f%% of the expected %.2f; tolerance %.2f%%)" % (
        label, gap, percent, expected, tolerance)


def reconcile(summary: Dict[str, Any], expect_spend: Optional[float], expect_impressions: Optional[float],
              expect_ads: Sequence[str], tolerance: float) -> List[str]:
    problems = []
    if not summary["rows"]:
        problems.append("no rows were read")
    for line in (_shortfall("spend", summary["spend"], expect_spend, tolerance),
                 _shortfall("impressions", summary["impressions"], expect_impressions, tolerance)):
        if line:
            problems.append(line)
    absent = [a for a in expect_ads if a not in set(summary["ads"])]
    if absent:
        problems.append("%d expected ads have no rows: %s" % (len(absent), ", ".join(absent)))
    return problems


def _read_ids(path: str) -> List[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Merge saved Meta Ads MCP responses into a CSV and reconcile them.")
    parser.add_argument("inputs", nargs="+", help="saved connector responses (JSON)")
    parser.add_argument("-o", "--output", required=True, help="CSV to write")
    parser.add_argument("--expect-spend", type=float, help="account-level spend for the same window")
    parser.add_argument("--expect-impressions", type=float, help="account-level impressions for the same window")
    parser.add_argument("--expect-ads", help="text file with one expected ad id per line")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help="percent of the expected total a pull may fall short before it counts as "
                             "incomplete (arbitrary default %g)" % DEFAULT_TOLERANCE)
    parser.add_argument("--level", default="ad",
                        help="level of the rows; `id` and `name` read as ad id and name only for ad rows (default: ad)")
    args = parser.parse_args(argv)

    notes: List[str] = []
    try:
        raw_rows = read_responses(args.inputs, notes)
        units = all_units(raw_rows)
        if len(units) > 1:
            print("ERROR: mixed currency: %s" % ", ".join(units))
            return EXIT_MIXED
        rows = merge(raw_rows, level=args.level)
    except ValueError as error:
        print("ERROR: %s" % error)
        return 2
    unlabelled = rows_without_unit(raw_rows) if units else 0
    fill_market(rows)
    write_csv(rows, args.output)
    summary = summarise(rows)
    problems = reconcile(summary, args.expect_spend, args.expect_impressions,
                         _read_ids(args.expect_ads) if args.expect_ads else [], args.tolerance)

    out = []
    if unlabelled:
        out.append("WARNING: %d row%s state no currency for spend, so the CSV header names none: pass --currency to the review."
                   % (unlabelled, "" if unlabelled == 1 else "s"))
    if problems:
        out.append("WARNING: the pull does not reconcile, do not analyse it yet: " + "; ".join(problems))
        out.append("If short, re-fetch the missing ads in small batches by id; if over-counted, drop the "
                   "duplicate or overlapping responses. Then run this again.")
    out += ["CONNECTOR NOTE %s" % note for note in notes]
    if any("unsupported field" in note.lower() for note in notes):
        out.append("WARNING: the connector refused some requested fields (see the notes above); every row came back "
                   "without them. Check the field catalogue for the current names and pull again, or accept them as n/a.")
    absent = absent_fields(rows) if rows else []
    if absent:
        out.append("fields no row carries: %s" % ", ".join(absent))
    out += [
        "wrote %s" % args.output,
        "rows: %d" % summary["rows"],
        "distinct ads: %d" % len(summary["ads"]),
        "date range: %s to %s" % (summary["start"] or "n/a", summary["end"] or "n/a"),
        "total spend: %.2f" % summary["spend"],
        "total impressions: %d" % summary["impressions"],
    ]
    if not problems and (args.expect_spend is not None or args.expect_impressions is not None or args.expect_ads):
        out.append("reconciled against the expected totals (tolerance %g%%)" % args.tolerance)
    elif args.expect_spend is None and args.expect_impressions is None and not args.expect_ads:
        out.append("not reconciled: no expected totals were given")
    print("\n".join(out))
    return EXIT_SHORT if problems else 0


if __name__ == "__main__":
    sys.exit(main())
