#!/usr/bin/env python3
"""Judge a past sale from the account's own daily data.

Usage: python3 sale_lift.py ads.csv --sale-from 2026-03-16 --sale-to 2026-03-22 [--baseline-days 21]
                            [--gap-days 0] [--post-days 9] [--min-baseline-days 7]
                            [--exclude 2026-02-20:2026-02-23 ...]
                            [--margin 38 [--baseline-margin 52]] [--currency USD] [--where ad_type=promo] [--json]

Standard library only. Sums spend, purchases, purchase value (and new-customer purchases and store revenue when the
export has them) per calendar day across the ads kept, then compares the sale days with what the account's own
days before the sale predict for the same weekdays. It reports the lift, the new-customer share, the dip
after the sale (sales pulled forward) and, when you give margins, the contribution after discount and spend.
Platform-attributed purchases are not store revenue: with no revenue column the read says so. Every window length is
an arbitrary default: --baseline-days, --post-days and --min-baseline-days should be set from your own account.
Earlier promotions inside the baseline window are not found automatically: name them with --exclude FROM:TO (repeatable,
inclusive) and those days leave the baseline and the post-sale window.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

SCHEMA = 1
MEASURES = ("spend", "conversions", "conversion_value", "new_customers", "revenue")
LABELS = {"spend": "spend", "conversions": "purchases", "conversion_value": "purchase value (platform-attributed)",
          "new_customers": "new-customer purchases", "revenue": "store revenue"}
ATTRIBUTED = "platform-attributed purchase value, not store revenue: it can over- or under-count the sale"
FILTERED = ("This is a filtered read: it cannot see the sale's effect on the other ads, so the lift is the lift of the "
            "ads kept, not of the whole account.")

DEFAULTS = {"baseline_days": 21, "gap_days": 0, "post_days": 9, "min_baseline_days": 7}
# Defaults that are a plain starting point rather than a length to set from the account.
PLAIN_DEFAULTS = ("gap_days",)

Day = Dict[str, Optional[float]]


def _sum(values: Sequence[Optional[float]]) -> Optional[float]:
    kept = [v for v in values if v is not None]
    return sum(kept) if kept else None


def _daily(rows: Sequence[Dict[str, Any]]) -> Dict[dt.date, Day]:
    """Each measure summed per calendar day across all rows; None when no row that day carries it."""
    by_day: Dict[dt.date, List[Dict[str, Any]]] = {}
    for row in rows:
        day = cm._parse_date(row.get("date"))
        if day:
            by_day.setdefault(day, []).append(row)
    return {d: {m: _sum([r.get(m) for r in members]) for m in MEASURES} for d, members in by_day.items()}


def _span(first: dt.date, last: dt.date) -> List[dt.date]:
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _expected(daily: Dict[dt.date, Day], base: Sequence[dt.date], day: dt.date, measure: str,
              notes: Set[str]) -> Optional[float]:
    """The baseline mean for this weekday; the all-day mean (with a note) when the baseline has none."""
    same = [daily[b][measure] for b in base if b.weekday() == day.weekday() and daily[b][measure] is not None]
    if same:
        return _mean(same)
    every = [daily[b][measure] for b in base if daily[b][measure] is not None]
    if not every:
        return None
    notes.add("no %s in the baseline: used the all-day mean" % calendar.day_name[day.weekday()])
    return _mean(every)


def _lift_pct(lift: Optional[float], expected: Optional[float], measure: str) -> Tuple[Optional[float], Optional[str]]:
    if lift is None or expected is None:
        return None, "n/a (missing %s)" % measure
    if expected == 0:
        return None, "n/a (missing baseline %s: it is zero)" % measure
    return lift / expected * 100, None


def _read(daily: Dict[dt.date, Day], base: Sequence[dt.date], days: Sequence[dt.date],
          notes: Set[str]) -> Dict[str, Dict[str, Any]]:
    """Actual vs weekday-matched expected for each measure over the days that have data."""
    out = {}
    for m in MEASURES:
        used = [d for d in days if d in daily and daily[d][m] is not None]
        actual = _sum([daily[d][m] for d in used])
        expecteds = [_expected(daily, base, d, m, notes) for d in used]
        expected = None if not used or any(e is None for e in expecteds) else sum(expecteds)
        lift = None if actual is None or expected is None else actual - expected
        pct, pct_note = _lift_pct(lift, expected, m)
        out[m] = {"actual": actual, "expected": expected, "lift": lift, "lift_pct": pct, "lift_pct_note": pct_note}
    return out


def _totals(daily: Dict[dt.date, Day], days: Sequence[dt.date]) -> Dict[str, Optional[float]]:
    present = [d for d in days if d in daily]
    totals: Dict[str, Optional[float]] = {f: None for f in cm.NUMERIC_FIELDS}
    totals.update({m: _sum([daily[d][m] for d in present]) for m in MEASURES})
    return totals


def _pooled(daily: Dict[dt.date, Day], days: Sequence[dt.date]) -> Dict[str, Any]:
    totals = _totals(daily, days)
    metrics = cm.compute_metrics(totals)
    out: Dict[str, Any] = {"days": len([d for d in days if d in daily]), "spend": totals["spend"],
                           "conversions": totals["conversions"], "conversion_value": totals["conversion_value"]}
    for name in ("roas", "cpa", "new_customer_purchase_share"):
        out[name] = metrics[name]
        out[name + "_note"] = None if metrics[name] is not None else "n/a (%s)" % cm.describe_missing(totals, name)
    return out


def _incremental_roas(sale: Dict[str, Dict[str, Any]], baseline_roas: Optional[float]) -> Dict[str, Any]:
    """Extra platform-attributed value per extra unit of spend, set against the baseline's own roas."""
    value_lift, spend_lift = sale["conversion_value"]["lift"], sale["spend"]["lift"]
    if value_lift is None or spend_lift is None:
        return {"value": None, "note": "n/a (missing %s)" % ("spend" if spend_lift is None else "conversion_value"),
                "versus_baseline": None}
    if spend_lift <= 0:
        return {"value": None, "note": "n/a (the sale did not raise spend over its expectation, so there is no extra "
                                       "spend to divide by)", "versus_baseline": None}
    value = value_lift / spend_lift
    if baseline_roas is None:
        versus = None
    else:
        versus = "beat" if value > baseline_roas else "matched" if value == baseline_roas else "fell short of"
    return {"value": value, "note": None, "versus_baseline": versus}


def _new_share(pooled: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {w: {"share": pooled[w]["new_customer_purchase_share"], "note": pooled[w]["new_customer_purchase_share_note"]}
            for w in ("sale", "baseline")}


def _pull_forward(post: Optional[Dict[str, Dict[str, Any]]], asked: int, used: int, lead: str) -> Dict[str, Any]:
    if post is None:
        return {"available": False, "note": "n/a (no days after the sale in the data)"}
    dip = None
    for measure, unit in (("conversions", "purchases"), (lead, LABELS[lead])):
        lift = post[measure]["lift"]
        if lift is not None and round(-lift) >= 1:
            dip = ("a dip of %.0f %s after the sale: some of the sale's lift may be sales pulled forward from these days"
                   % (-lift, unit))
            break
    return {"available": True, "days_used": used, "days_missing": asked - used, "measures": post, "dip": dip}


def _net(sale: Dict[str, Dict[str, Any]], post: Optional[Dict[str, Dict[str, Any]]], lead: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"includes_post": post is not None}
    for m in ("conversions", lead):
        parts = [sale[m]] + ([post[m]] if post is not None else [])
        lifts, expecteds = [p["lift"] for p in parts], [p["expected"] for p in parts]
        lift = None if None in lifts else sum(lifts)
        expected = None if None in expecteds else sum(expecteds)
        pct, note = _lift_pct(lift, expected, m)
        out[m] = {"lift": lift, "lift_pct": pct, "lift_pct_note": note}
    return out


def _contribution(reads: Sequence[Tuple[Dict[str, Dict[str, Any]], float]], lead: str,
                  base_margin: float) -> Optional[float]:
    """Each window's value * the margin it sold at - expected value * baseline margin - the extra spend. The
    sale days sold at the sale margin; the days after it are back at full price, so they use the baseline."""
    cells = [r[m][k] for r, _ in reads for m in ("spend", lead) for k in ("actual", "expected")]
    if None in cells:
        return None
    spend = sum(r["spend"]["actual"] - r["spend"]["expected"] for r, _ in reads)
    return (sum(r[lead]["actual"] * sold_at / 100 for r, sold_at in reads)
            - sum(r[lead]["expected"] for r, _ in reads) * base_margin / 100 - spend)


def _contributions(sale: Dict[str, Dict[str, Any]], post: Optional[Dict[str, Dict[str, Any]]], lead: str,
                   margin: float, base_margin: float, defaulted: bool) -> Dict[str, Any]:
    missing = "n/a (missing %s or spend)" % lead
    sale_only = _contribution([(sale, margin)], lead, base_margin)
    both = _contribution([(sale, margin), (post, base_margin)], lead, base_margin) if post is not None else None
    return {"sale": sale_only, "sale_note": None if sale_only is not None else missing,
            "sale_and_post": both,
            "sale_and_post_note": None if both is not None else
            "n/a (no days after the sale in the data)" if post is None else missing,
            "baseline_margin_note": "the baseline margin was taken as the sale margin: this understates a discount's cost"
            if defaulted else None}


def _unjudged_lead(result: Dict[str, Any], minimum: int) -> List[str]:
    base = result["baseline"]
    pooled = result["pooled"]["sale"]
    return [
        "Too little baseline to judge: %d dated days between %s and %s, and the read needs at least %d. No lift number."
        % (base["days"], base["from"], base["to"], minimum),
        "The sale days themselves: spend %s, purchases %s, purchase value %s."
        % (_n(pooled["spend"]), _n(pooled["conversions"], 1), _n(pooled["conversion_value"])),
        "Widen --baseline-days (or lower --min-baseline-days if you accept a thinner read) and run it again.",
    ]


def _lead(result: Dict[str, Any]) -> List[str]:
    lead_m = result["lead_value"]
    net, base = result["net"], result["baseline"]
    value, buys = net[lead_m], net["conversions"]
    scope = "sale plus the days after" if net["includes_post"] else "sale only (no days after the sale in the data)"
    first = "Net lift, %s: %s %s%s and %s purchases%s (baseline: weekday-matched mean of %d days, %s to %s)." % (
        scope, LABELS[lead_m], _n(value["lift"], sign=True), _pct(value["lift_pct"]), _n(buys["lift"], 1, True),
        _pct(buys["lift_pct"]), base["days"], base["from"], base["to"])
    inc, base_roas = result["incremental_roas"], result["pooled"]["baseline"]["roas"]
    if inc["value"] is None:
        second = "Incremental roas: %s." % inc["note"]
    elif base_roas is None:
        second = "Incremental roas %.2f; the baseline roas is %s." % (inc["value"], result["pooled"]["baseline"]["roas_note"])
    else:
        second = "Incremental roas %.2f %s the account's own baseline roas of %.2f." % (
            inc["value"], inc["versus_baseline"], base_roas)
    dip = result["pull_forward"].get("dip")
    if dip:
        third = "Biggest caveat: " + dip + "."
    elif lead_m == "conversion_value":
        third = "Biggest caveat: this is " + ATTRIBUTED + "."
    else:
        third = ("Biggest caveat: the baseline is the account's own earlier days; a price change, stock-out or season "
                 "in the same weeks is not separated from the sale.")
    return [first, second, third]


def build_sale(rows: Sequence[Dict[str, Any]], sale_from: dt.date, sale_to: dt.date, baseline_days: int = 21,
               gap_days: int = 0, post_days: int = 9, min_baseline_days: int = 7, margin: Optional[float] = None,
               baseline_margin: Optional[float] = None, currency: Optional[str] = None,
               filtered: bool = False, exclude: Sequence[Tuple[dt.date, dt.date]] = (),
               user_set: Sequence[str] = ()) -> Dict[str, Any]:
    """The sale read (schema 1). Raises ValueError for dates the data cannot support."""
    if sale_from > sale_to:
        raise ValueError("--sale-from %s is after --sale-to %s" % (sale_from, sale_to))
    if baseline_days < 1 or min_baseline_days < 1 or gap_days < 0 or post_days < 0:
        raise ValueError("--baseline-days and --min-baseline-days must be at least 1; --gap-days and --post-days at least 0")
    daily = _daily(rows)
    if not daily:
        raise ValueError("no dated rows in the data: the sale read needs a Day or date column")
    first, last = min(daily), max(daily)
    if sale_from < first or sale_to > last:
        raise ValueError("the sale (%s to %s) is outside the data, which runs from %s to %s" % (
            sale_from, sale_to, first, last))
    defaulted = margin is not None and baseline_margin is None
    if defaulted:
        baseline_margin = margin
    base_last = sale_from - dt.timedelta(days=gap_days + 1)
    base_window = _span(base_last - dt.timedelta(days=baseline_days - 1), base_last)
    skipped = {d for first_day, last_day in exclude for d in _span(first_day, last_day)}
    base = [d for d in base_window if d in daily and d not in skipped]
    sale_window = _span(sale_from, sale_to)
    post_window = _span(sale_to + dt.timedelta(days=1), sale_to + dt.timedelta(days=post_days)) if post_days else []
    post = [d for d in post_window if d in daily and d not in skipped]
    excluded = []
    for first_day, last_day in exclude:
        span = set(_span(first_day, last_day))
        excluded.append({"from": first_day.isoformat(), "to": last_day.isoformat(),
                         "baseline_days_removed": sum(1 for d in base_window if d in daily and d in span),
                         "post_days_removed": sum(1 for d in post_window if d in daily and d in span)})
    has_revenue = any(daily[d]["revenue"] is not None for d in daily)
    lead = "revenue" if has_revenue else "conversion_value"
    result: Dict[str, Any] = {
        "schema": SCHEMA, "currency": currency or "currency not stated", "window": [first.isoformat(), last.isoformat()],
        "sale": {"from": sale_from.isoformat(), "to": sale_to.isoformat(), "days": len(sale_window),
                 "gaps": [d.isoformat() for d in sale_window if d not in daily]},
        "baseline": {"from": base_window[0].isoformat(), "to": base_window[-1].isoformat(), "days": len(base),
                     "excluded": excluded},
        "lead_value": lead, "value_basis": "store revenue" if has_revenue else ATTRIBUTED,
        "filtered": FILTERED if filtered else None,
        "settings": {"baseline_days": baseline_days, "gap_days": gap_days, "post_days": post_days,
                     "min_baseline_days": min_baseline_days, "margin": margin, "baseline_margin": baseline_margin,
                     "user_set": sorted(user_set)},
        "judged": len(base) >= min_baseline_days,
        "pooled": {"sale": _pooled(daily, sale_window), "baseline": _pooled(daily, base)},
    }
    if not result["judged"]:
        result["lead"] = _unjudged_lead(result, min_baseline_days)
        return result
    notes: Set[str] = set()
    sale = _read(daily, base, sale_window, notes)
    post_read = _read(daily, base, post, notes) if post else None
    result.update(measures=sale, notes=sorted(notes), new_customers=_new_share(result["pooled"]),
                  incremental_roas=_incremental_roas(sale, result["pooled"]["baseline"]["roas"]),
                  pull_forward=_pull_forward(post_read, post_days, len(post), lead), net=_net(sale, post_read, lead))
    result["contribution"] = (_contributions(sale, post_read, lead, margin, baseline_margin, defaulted)
                              if margin is not None else
                              {"note": "n/a (give --margin to judge profit, not just revenue)"})
    result["lead"] = _lead(result)
    return result


def _n(value: Optional[float], digits: int = 2, sign: bool = False) -> str:
    if value is None:
        return "n/a"
    return "%+.*f" % (digits, value) if sign else "%.*f" % (digits, value)


def _pct(value: Optional[float]) -> str:
    return "" if value is None else " (%+.1f%%)" % value


def _cell(value: Optional[float], note: Optional[str], digits: int = 2, sign: bool = False) -> str:
    return note if value is None and note else _n(value, digits, sign)


def render(result: Dict[str, Any]) -> str:
    """The text read: the three lead lines, then the numbers behind them."""
    s, b, cfg = result["sale"], result["baseline"], result["settings"]
    out = ["Sale read: %s to %s (%d days)" % (s["from"], s["to"], s["days"])] + result["lead"] + [""]
    flags = "; ".join("--%s %d (%s)" % (k.replace("_", "-"), cfg[k], "yours" if k in cfg["user_set"] else
                                          "default" if k in PLAIN_DEFAULTS else "default, arbitrary")
                      for k in DEFAULTS)
    out.append("Basis: the account's own daily data %s to %s, amounts in %s. Baseline: %d dated days %s to %s (%s%s)."
               % (result["window"][0], result["window"][1], result["currency"], b["days"], b["from"], b["to"], flags,
                  "; set the arbitrary ones from your own account" if any(
                      k not in cfg["user_set"] and k not in PLAIN_DEFAULTS for k in DEFAULTS) else ""))
    removed = [e for e in b["excluded"] if e["baseline_days_removed"] or e["post_days_removed"]]
    for e in b["excluded"]:
        if e in removed:
            out.append("Left out: %s to %s (baseline days removed: %d; post-sale days removed: %d)." % (
                e["from"], e["to"], e["baseline_days_removed"], e["post_days_removed"]))
        else:
            out.append("--exclude %s:%s removed nothing: it overlaps neither the baseline nor the post-sale days."
                       % (e["from"], e["to"]))
    if removed:
        out.append("%d baseline days remain." % b["days"])
    else:
        out.append("The baseline may include other promotions: pass --exclude FROM:TO (YYYY-MM-DD, inclusive, "
                   "repeatable) for each one.")
    out.append("Value: " + result["value_basis"] + ".")
    if result["filtered"]:
        out.append(result["filtered"])
    if s["gaps"]:
        out.append("Days in the sale with no data (left out of actual and expected): " + ", ".join(s["gaps"]) + ".")
    if not result["judged"]:
        return "\n".join(out)
    out += ["Notes: " + n for n in result["notes"]]
    out += ["", "Sale window: actual vs what the baseline predicts for the same weekdays"]
    for m, r in result["measures"].items():
        if r["actual"] is None and m == "revenue":
            continue
        if r["actual"] is None:
            out.append("  %s: n/a (missing %s)" % (LABELS[m], m))
            continue
        out.append("  %s: actual %s, expected %s, lift %s%s" % (
            LABELS[m], _n(r["actual"]), _n(r["expected"]), _n(r["lift"], sign=True),
            _pct(r["lift_pct"]) if r["lift_pct"] is not None else " (lift %% %s)" % r["lift_pct_note"]))
    pooled = result["pooled"]
    for name in ("sale", "baseline"):
        p = pooled[name]
        out.append("  %s roas %s, cpa %s" % (name, _cell(p["roas"], p["roas_note"]), _cell(p["cpa"], p["cpa_note"])))
    inc = result["incremental_roas"]
    out.append("  incremental roas: %s" % _cell(inc["value"], inc["note"]))
    out += ["", "New vs returning customers (new-customer purchase share):"]
    for name, share in result["new_customers"].items():
        out.append("  %s: %s" % (name, _cell(share["share"], share["note"], 1) + ("%" if share["share"] is not None else "")))
    out += ["", "After the sale (pull-forward):"]
    pull = result["pull_forward"]
    if not pull["available"]:
        out.append("  " + pull["note"])
    else:
        if pull["days_missing"]:
            out.append("  %d of the %d post-sale days are not in the data; the %d that exist were used."
                       % (pull["days_missing"], cfg["post_days"], pull["days_used"]))
        for m in ("conversions", result["lead_value"]):
            r = pull["measures"][m]
            out.append("  %s: actual %s, expected %s, lift %s" % (
                LABELS[m], _n(r["actual"]), _n(r["expected"]), _cell(r["lift"], "n/a (missing %s)" % m, sign=True)))
        out.append("  " + (pull["dip"] or "no dip after the sale in the days read") + ".")
    out += ["", "Contribution:"]
    con = result["contribution"]
    if "note" in con:
        out.append("  contribution: " + con["note"])
    else:
        out.append("  sale window: %s" % _cell(con["sale"], con["sale_note"], sign=True))
        out.append("  sale + post window: %s" % _cell(con["sale_and_post"], con["sale_and_post_note"], sign=True))
        out.append("  formula: sale value x margin %g%% - expected value x baseline margin %g%% - extra spend."
                   % (cfg["margin"], cfg["baseline_margin"]))
        if con["baseline_margin_note"]:
            out.append("  " + con["baseline_margin_note"] + ".")
    return "\n".join(out)


def _date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise ValueError("%r is not an ISO date (write YYYY-MM-DD)" % text)


def _exclusion(text: str) -> Tuple[dt.date, dt.date]:
    first_text, colon, last_text = text.partition(":")
    if not colon:
        raise ValueError("--exclude %r is not FROM:TO (write two ISO dates, e.g. 2026-02-20:2026-02-23)" % text)
    try:
        first_day, last_day = _date(first_text), _date(last_text)
    except ValueError as exc:
        raise ValueError("--exclude %s: %s" % (text, exc))
    if first_day > last_day:
        raise ValueError("--exclude %s is after %s" % (first_day, last_day))
    return first_day, last_day


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Judge a past sale from the account's own daily data.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--sale-from", required=True, help="first sale day, ISO date (inclusive)")
    parser.add_argument("--sale-to", required=True, help="last sale day, ISO date (inclusive)")
    parser.add_argument("--baseline-days", type=int, default=None,
                        help="days before the sale that set the baseline, minus any --exclude days (default %d: arbitrary, "
                             "set it from your own account)" % DEFAULTS["baseline_days"])
    parser.add_argument("--gap-days", type=int, default=None,
                        help="days skipped right before the sale, e.g. a teaser period (default %d)" % DEFAULTS["gap_days"])
    parser.add_argument("--post-days", type=int, default=None,
                        help="days after the sale read for pull-forward (default %d: arbitrary, set it from your own "
                             "account)" % DEFAULTS["post_days"])
    parser.add_argument("--min-baseline-days", type=int, default=None,
                        help="fewer dated baseline days than this gives no lift number (default %d: arbitrary)"
                             % DEFAULTS["min_baseline_days"])
    parser.add_argument("--exclude", action="append", metavar="FROM:TO",
                        help="ISO dates, inclusive: drop an earlier promotion from the baseline (and the post-sale "
                             "days); repeat for each one")
    parser.add_argument("--margin", type=float,
                        help="contribution margin in percent on sale-period revenue after the discount and cost of goods")
    parser.add_argument("--baseline-margin", type=float,
                        help="contribution margin in percent at full price (default: the --margin value)")
    parser.add_argument("--currency", help="currency code for the output (default: read from the spend column)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        if args.baseline_margin is not None and args.margin is None:
            raise ValueError("--baseline-margin needs --margin")
        exclude = [_exclusion(t) for t in args.exclude or []]
        user_set = [k for k in DEFAULTS if getattr(args, k) is not None]
        window = {k: DEFAULTS[k] if getattr(args, k) is None else getattr(args, k) for k in DEFAULTS}
        rows, _, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        result = build_sale(rows, _date(args.sale_from), _date(args.sale_to), window["baseline_days"],
                            window["gap_days"], window["post_days"], window["min_baseline_days"], args.margin,
                            args.baseline_margin, args.currency or cm.detect_currency(args.path),
                            filtered=bool(args.where), exclude=exclude, user_set=user_set)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["run_notes"] = run_notes
    print(json.dumps(result, indent=2) if args.json else "\n".join(run_notes + [render(result)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
