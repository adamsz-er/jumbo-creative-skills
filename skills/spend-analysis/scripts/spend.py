#!/usr/bin/env python3
"""Where the money goes, and which budget moves the account's own results support.

Usage: python3 spend.py ads.csv [--verdicts verdicts.json] [--pareto-share 80] [--top-n 3]
                        [--age-bands 9,18,36] [--min-impressions 1000] [--currency USD] [--json]

Standard library only. Totals, spend concentration (the fewest ads holding a share of spend, and of purchase
value), and spend by concept, format, ad type, age band and verdict group, each with its pooled roas and cpa
against the account's pooled roas. With --verdicts (keep-or-kill --json output) it also shows the spend on
ads judged pause, the room to scale on scale and keep ads, and budget moves. Everything is relative to this
account's own results; there is no benchmark. --pareto-share (80, a common convention, not a rule), --top-n,
--age-bands and --min-impressions are arbitrary defaults: set them from your own account. It never suggests
a step size: raise in steps you have seen your account absorb before.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

SCHEMA = 1
CONFIDENCE_ORDER = ("Confident", "Early read", "Can't judge yet")
NEEDS_VERDICTS = "Budget moves need verdicts: run keep-or-kill with --json and pass --verdicts."
NO_SCALE_AD = "hold the money back or test new creative: no ad has earned a scale call"
NO_MOVE = "no move is supported by the data"
STEP_ADVICE = "raise in steps you have seen your account absorb before"
AGE_NOTE = "age is from first delivery in the window, so older ads may be understated"
DIMENSIONS = (("concept", "Concept"), ("format", "Format"), ("ad_type", "Ad type"), ("age_band", "Age"),
              ("verdict_group", "Verdict"))
PAYBACK_FIELDS = ("roas", "cpa")


def _key(ad: Dict[str, Any]) -> str:
    return str(ad.get("ad_id") or ad.get("ad_name"))


def _pooled(ads: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Base fields summed over ads (None when no ad has the field) and the metrics computed from the sums."""
    total: Dict[str, Optional[float]] = {}
    for field in cm.NUMERIC_FIELDS:
        values = [a[field] for a in ads if a.get(field) is not None]
        total[field] = sum(values) if values else None
    total["reach"] = None
    return dict(total, **cm.compute_metrics(total))


def _ratio(value: Optional[float], base: Optional[float]) -> Optional[float]:
    return None if value is None or not base else value / base * 100


def _with_note(out: Dict[str, Any], name: str, pooled: Dict[str, Any], metric: str) -> None:
    out[name] = pooled[metric]
    out[name + "_note"] = None if pooled[metric] is not None else cm.describe_missing(pooled, metric)


def _group_row(label: str, members: Sequence[Dict[str, Any]], total_spend: float, account: Dict[str, Any]) -> Dict[str, Any]:
    pooled = _pooled(members)
    out: Dict[str, Any] = {"value": label, "ads": len(members), "ad_ids": [_key(a) for a in members],
                           "spend": pooled["spend"],
                           "spend_share": _ratio(pooled["spend"], total_spend),
                           "purchases": pooled["conversions"], "purchase_value": pooled["conversion_value"]}
    _with_note(out, "roas", pooled, "roas")
    _with_note(out, "cpa", pooled, "cpa")
    out["roas_vs_account"] = _ratio(pooled["roas"], account["roas"])
    out["roas_vs_account_note"] = None if out["roas_vs_account"] is not None else (
        out["roas_note"] or "missing account roas")
    return out


def parse_age_bands(text: str) -> List[int]:
    """Day edges such as "9,18,36" -> [9, 18, 36]; raises ValueError unless they are whole numbers rising from 1."""
    try:
        edges = [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        raise ValueError("bad --age-bands %r: use whole day numbers such as 9,18,36" % text)
    if not edges or edges[0] < 1 or any(b <= a for a, b in zip(edges, edges[1:])):
        raise ValueError("bad --age-bands %r: use rising whole day numbers from 1, such as 9,18,36" % text)
    return edges


def age_labels(edges: Sequence[int]) -> List[str]:
    labels = ["under %d days" % edges[0]] + ["%d-%d days" % (lo, hi - 1) for lo, hi in zip(edges, edges[1:])]
    return labels + ["%d+ days" % edges[-1]]


def _age_band(age: Optional[int], edges: Sequence[int], labels: Sequence[str]) -> str:
    if age is None:
        return "age unknown"
    return labels[sum(1 for e in edges if age >= e)]


def verdict_group(verdict_id: Optional[str]) -> str:
    if verdict_id is None:
        return "no verdict"
    if verdict_id.startswith("pause_"):
        return "pause"
    if verdict_id.startswith("check_"):
        return "check"
    if verdict_id in ("scale", "keep", "iterate"):
        return verdict_id
    return "not judged yet"


def load_verdicts(path_or_data: Any) -> Dict[str, Dict[str, Any]]:
    """{ad: verdict entry} from keep-or-kill --json output (a path or the loaded dict)."""
    data = path_or_data
    if isinstance(path_or_data, (str, Path)):
        try:
            data = json.loads(Path(path_or_data).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("--verdicts is not valid JSON: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("ads"), list):
        raise ValueError("--verdicts must be keep-or-kill --json output (an object with an \"ads\" list)")
    return {str(a["ad"]): a for a in data["ads"] if isinstance(a, dict) and a.get("ad")}


def _window_days(rows: Sequence[Dict[str, Any]]) -> Optional[int]:
    first, last = cm.data_window(rows)
    if not first:
        return None
    return (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days + 1


def _pareto(items: Sequence[Tuple[str, float]], share: float, n_ads: int) -> Dict[str, Any]:
    """The fewest items (largest first) holding at least `share` percent of their total."""
    total = sum(v for _, v in items)
    if not total:
        return {"ads": None, "ad_share": None, "held": None, "note": "no values to rank"}
    running = 0.0
    for count, (_, value) in enumerate(sorted(items, key=lambda i: i[1], reverse=True), start=1):
        running += value
        if running / total * 100 >= share - 1e-9:
            return {"ads": count, "ad_share": count / n_ads * 100, "held": running / total * 100, "note": None}
    return {"ads": None, "ad_share": None, "held": None, "note": "no values to rank"}


def _concentration(ads: Sequence[Dict[str, Any]], pareto_share: float, top_n: int) -> Dict[str, Any]:
    spend = [(_key(a), a["spend"]) for a in ads if a.get("spend")]
    value = [(_key(a), a["conversion_value"]) for a in ads if a.get("conversion_value")]
    return {"pareto_share": pareto_share, "top_n": top_n, "ads": len(ads),
            "spend_pareto": _pareto(spend, pareto_share, len(ads)),
            "value_pareto": _pareto(value, pareto_share, len(ads)),
            "top_n_spend_share": cm.concentration(ads, top_n)}


def _dimensions(ads: Sequence[Dict[str, Any]], total_spend: float, account: Dict[str, Any],
                with_verdicts: bool) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for field, _ in DIMENSIONS:
        if field == "verdict_group" and not with_verdicts:
            continue
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for ad in ads:
            groups.setdefault(str(ad.get(field) or "unknown"), []).append(ad)
        rows = [_group_row(label, members, total_spend, account) for label, members in groups.items()]
        out[field] = sorted(rows, key=lambda r: r["spend"] or 0, reverse=True)
    return out


def _entry(ad: Dict[str, Any], total_spend: float) -> Dict[str, Any]:
    return {"ad": _key(ad), "ad_name": ad.get("ad_name"), "spend": ad.get("spend"),
            "spend_share": _ratio(ad.get("spend"), total_spend), "verdict_id": ad.get("verdict_id"),
            "confidence": ad.get("confidence"), "sentence": ad.get("sentence")}


def _pause_section(ads: Sequence[Dict[str, Any]], total_spend: float, days: Optional[int]) -> Dict[str, Any]:
    paused = [a for a in ads if verdict_group(a.get("verdict_id")) == "pause"]
    spend = sum(a.get("spend") or 0 for a in paused)
    listed = [dict(_entry(a, total_spend), never_worked=a.get("verdict_id") == "pause_never_worked")
              for a in sorted(paused, key=lambda a: a.get("spend") or 0, reverse=True)]
    never = sum(e["spend"] or 0 for e in listed if e["never_worked"])
    return {"ads": listed, "spend": spend, "spend_share": _ratio(spend, total_spend),
            "never_worked_spend": never, "never_worked_share": _ratio(never, total_spend),
            "per_day": spend / days if days else None,
            "per_day_note": None if days else "missing dates"}


def _frequency_read(ad: Dict[str, Any], base: Dict[str, Any], min_impressions: int) -> Tuple[Optional[float], str]:
    freq = ad.get("frequency")
    if freq is None:
        return None, "n/a (missing reach)"
    stats = base["groups"].get(str(ad.get("format") or "unknown"))
    if not stats or stats["median"] is None:
        return freq, "n/a (no format baseline: needs ads with at least %d impressions)" % min_impressions
    if freq <= stats["median"]:
        return freq, "room: frequency at or below the format median"
    if freq > stats["p75"]:
        return freq, "watch: frequency above most ads of its format"
    return freq, "frequency between the format median and the top quarter of its format"


def _room_section(ads: Sequence[Dict[str, Any]], total_spend: float, account: Dict[str, Any],
                  min_impressions: int) -> Dict[str, Any]:
    base = cm.baseline(ads, "frequency", ("format",), min_impressions)
    out: Dict[str, Any] = {}
    for group in ("scale", "keep"):
        entries = []
        for ad in sorted((a for a in ads if a.get("verdict_id") == group), key=lambda a: a.get("spend") or 0, reverse=True):
            freq, read = _frequency_read(ad, base, min_impressions)
            stats = base["groups"].get(str(ad.get("format") or "unknown")) or {}
            entries.append(dict(_entry(ad, total_spend), roas=ad.get("roas"),
                                roas_vs_account=_ratio(ad.get("roas"), account["roas"]),
                                frequency=freq, format_median_frequency=stats.get("median"), room=read))
        out[group] = entries
    return out


def _weakest(confidences: Sequence[Optional[str]]) -> Optional[str]:
    rank = {c: i for i, c in enumerate(CONFIDENCE_ORDER)}
    return max(confidences, key=lambda c: rank.get(c, len(rank)), default=None)


def _moves_section(ads: Sequence[Dict[str, Any]], account: Dict[str, Any]) -> Dict[str, Any]:
    sources = sorted((a for a in ads if verdict_group(a.get("verdict_id")) == "pause"),
                     key=lambda a: a.get("spend") or 0, reverse=True)
    dests = [a for a in ads if a.get("verdict_id") == "scale" and a.get("spend")]
    held = [{"ad": _key(a), "action": "check before moving money", "sentence": a.get("sentence")}
            for a in ads if verdict_group(a.get("verdict_id")) == "check"]
    held += [{"ad": _key(a), "action": "refresh the creative before changing its budget", "sentence": a.get("sentence")}
             for a in ads if a.get("verdict_id") == "iterate"]
    moves: List[Dict[str, Any]] = []
    note = None
    if not sources:
        note = NO_MOVE
    elif not dests:
        note = NO_SCALE_AD
    else:
        dest_total = sum(d["spend"] for d in dests)
        for src in sources:
            days = src.get("active_days")
            if not src.get("spend") or not days:
                continue
            daily = src["spend"] / days
            to = [{"ad": _key(d), "amount_per_day": daily * d["spend"] / dest_total,
                   "share": d["spend"] / dest_total * 100, "confidence": d.get("confidence"),
                   "roas_vs_account": _ratio(d.get("roas"), account["roas"])} for d in dests]
            moves.append({"from": _key(src), "to": to, "amount_per_day": daily,
                          "confidence": _weakest([src.get("confidence")] + [d.get("confidence") for d in dests]),
                          "evidence": [src.get("sentence")] + [
                              "%s: roas %s against the account's pooled roas" % (
                                  t["ad"], "n/a (%s)" % (cm.describe_missing(account, "roas") or "missing roas")
                                  if t["roas_vs_account"] is None else "%.0f%%" % t["roas_vs_account"])
                              for t in to]})
        note = None if moves else NO_MOVE
    return {"moves": moves, "note": note, "held": held, "step_advice": STEP_ADVICE}


def build_spend(rows: Sequence[Dict[str, Any]], key_map: Optional[Dict[str, str]] = None, verdicts: Any = None,
                pareto_share: float = 80.0, top_n: int = 3, age_bands: Sequence[int] = (9, 18, 36),
                min_impressions: int = 1000, currency: Optional[str] = None, path: Any = None) -> Dict[str, Any]:
    """The spend read: totals, concentration, dimensions and, with verdicts, pause spend, room and budget moves."""
    if not 0 < pareto_share <= 100:
        raise ValueError("bad --pareto-share %s: use a percent above 0 and up to 100" % pareto_share)
    if top_n < 1:
        raise ValueError("bad --top-n %s: use 1 or more" % top_n)
    ads = cm.aggregate_by_ad(rows, key_map)
    if not ads or not any(a.get("spend") for a in ads):
        raise ValueError("no ads with spend in the data, so there is nothing to analyse")
    records = load_verdicts(verdicts) if verdicts is not None else None
    if records is not None:
        matched = [a for a in ads if _key(a) in records]
        if not matched:
            raise ValueError("no ad in --verdicts matches an ad in the data: run keep-or-kill on this same file")
        for ad in ads:
            rec = records.get(_key(ad)) or {}
            ad.update(verdict_id=rec.get("verdict_id"), confidence=rec.get("confidence"), sentence=rec.get("sentence"))
    edges = list(age_bands)
    labels = age_labels(edges)
    for ad in ads:
        ad["age_band"] = _age_band(ad.get("age_days"), edges, labels)
        ad["verdict_group"] = verdict_group(ad.get("verdict_id")) if records is not None else None
    account = _pooled(ads)
    total_spend = account["spend"]
    days = _window_days(rows)
    first, last = cm.data_window(rows)
    bases = {a.get("age_basis") for a in ads if a.get("age_basis")}
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "settings": {"pareto_share": pareto_share, "top_n": top_n, "age_bands": edges,
                     "min_impressions": min_impressions, "verdicts": records is not None},
        "currency": currency or cm.detect_currency(path) or "currency not stated",
        "window": {"first": first, "last": last, "days": days},
        "totals": {"ads": len(ads), "spend": total_spend, "purchases": account["conversions"],
                   "purchase_value": account["conversion_value"],
                   **{n: account[n] for n in PAYBACK_FIELDS},
                   **{n + "_note": None if account[n] is not None else cm.describe_missing(account, n) for n in PAYBACK_FIELDS}},
        "concentration": _concentration(ads, pareto_share, top_n),
        "dimensions": _dimensions(ads, total_spend, account, records is not None),
        "age_note": AGE_NOTE if any(b and b.startswith("first delivery") for b in bases) else None,
        "age_bands": labels,
    }
    if records is None:
        result.update(pause=None, room=None, budget=None, budget_note=NEEDS_VERDICTS)
    else:
        result.update(pause=_pause_section(ads, total_spend, days),
                      room=_room_section(ads, total_spend, account, min_impressions),
                      budget=_moves_section(ads, account), budget_note=None)
    result["headline"] = _headline(result)
    return result


def _money(result: Dict[str, Any], value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    code = result["currency"]
    return "%s%.2f" % (code + " " if len(code) == 3 else "", value)


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.0f%%" % value


def _headline(result: Dict[str, Any]) -> List[str]:
    conc = result["concentration"]
    pareto = conc["spend_pareto"]
    top = next(iter(result["dimensions"].get("concept") or result["dimensions"]["format"]), None)
    first = "Where the money goes: %s of %d ads hold %s of spend" % (
        pareto["ads"] if pareto["ads"] is not None else "n/a", conc["ads"], _pct(conc["pareto_share"]))
    if top:
        first += "; the biggest %s is %s (%s of spend)." % (
            "concept" if result["dimensions"].get("concept") and top["value"] != "unknown" else "group",
            top["value"], _pct(top["spend_share"]))
    else:
        first += "."
    if result["pause"] is None:
        return [first, "Spend on ads judged pause: needs --verdicts.", NEEDS_VERDICTS]
    pause = result["pause"]
    second = "Spend on ads judged pause: %s (%s of spend, %d ad%s)." % (
        _money(result, pause["spend"]), _pct(pause["spend_share"]), len(pause["ads"]), "" if len(pause["ads"]) == 1 else "s")
    budget = result["budget"]
    if budget["moves"]:
        move = max(budget["moves"], key=lambda m: m["amount_per_day"])
        third = "Top move: shift %s a day from %s to the scale ads (%s). %s." % (
            _money(result, move["amount_per_day"]), move["from"], move["confidence"] or "confidence n/a", STEP_ADVICE)
    else:
        third = "Top move: %s." % (budget["note"] or NO_MOVE)
    return [first, second, third]


def _cell(value: Optional[float], note: Optional[str], digits: int = 2) -> str:
    return "%.*f" % (digits, value) if value is not None else "n/a (%s)" % (note or "no value")


def render(result: Dict[str, Any]) -> str:
    totals, conc, win = result["totals"], result["concentration"], result["window"]
    out = list(result["headline"]) + ["", "Totals (%s; %s to %s, %s days)" % (
        result["currency"], win["first"] or "n/a", win["last"] or "n/a", win["days"] if win["days"] is not None else "n/a")]
    out.append("  spend %s; purchases %s; purchase value %s; roas %s; cpa %s" % (
        _money(result, totals["spend"]),
        "n/a (missing conversions)" if totals["purchases"] is None else "%.0f" % totals["purchases"],
        "n/a (missing conversion_value)" if totals["purchase_value"] is None else "%.2f" % totals["purchase_value"],
        _cell(totals["roas"], totals["roas_note"]), _cell(totals["cpa"], totals["cpa_note"])))
    out += ["", "Concentration (%s%% is a common convention, not a rule; set your own)" % ("%g" % conc["pareto_share"])]
    for label, key in (("spend", "spend_pareto"), ("purchase value", "value_pareto")):
        p = conc[key]
        out.append("  %s: %s" % (label, "%d of %d ads (%s) hold %s of %s" % (
            p["ads"], conc["ads"], _pct(p["ad_share"]), _pct(p["held"]), label) if p["ads"] is not None
            else "n/a (%s)" % p["note"]))
    out.append("  top %d ads hold %s of spend" % (conc["top_n"], _pct(conc["top_n_spend_share"])))
    out += ["", "Spend by dimension (roas vs account: 100 = the same as the account)"]
    if result["age_note"]:
        out.append("  Note: %s." % result["age_note"])
    for field, title in DIMENSIONS:
        rows = result["dimensions"].get(field)
        if not rows:
            continue
        out.append("  %s:" % title)
        for r in rows:
            out.append("    %s: %d ad%s; spend %s (%s); purchases %s; value %s; roas %s; cpa %s; vs account %s" % (
                r["value"], r["ads"], "" if r["ads"] == 1 else "s", _money(result, r["spend"]), _pct(r["spend_share"]),
                "n/a (missing conversions)" if r["purchases"] is None else "%.0f" % r["purchases"],
                "n/a (missing conversion_value)" if r["purchase_value"] is None else "%.2f" % r["purchase_value"],
                _cell(r["roas"], r["roas_note"]), _cell(r["cpa"], r["cpa_note"]),
                _cell(r["roas_vs_account"], r["roas_vs_account_note"], 0)))
    if result["pause"] is None:
        return "\n".join(out + ["", result["budget_note"]])
    pause = result["pause"]
    out += ["", "Spend on ads judged pause: %s (%s of spend); never worked: %s (%s); %s a day across the window" % (
        _money(result, pause["spend"]), _pct(pause["spend_share"]), _money(result, pause["never_worked_spend"]),
        _pct(pause["never_worked_share"]), _money(result, pause["per_day"]))]
    out += ["  %s%s (%s, %s): %s" % (e["ad"], " [never worked]" if e["never_worked"] else "", _money(result, e["spend"]),
                                     _pct(e["spend_share"]), e["sentence"]) for e in pause["ads"]] or ["  none"]
    out += ["", "Room to scale"]
    for group in ("scale", "keep"):
        out.append("  %s:" % group)
        for e in result["room"][group] or []:
            out.append("    %s: %s of spend; roas vs account %s; frequency %s; %s" % (
                e["ad"], _pct(e["spend_share"]), _cell(e["roas_vs_account"], "missing roas", 0),
                "n/a" if e["frequency"] is None else "%.2f" % e["frequency"], e["room"]))
        if not result["room"][group]:
            out.append("    none")
    budget = result["budget"]
    out += ["", "Budget moves (%s)" % STEP_ADVICE]
    for m in budget["moves"]:
        out.append("  Move %s a day from %s [%s]" % (_money(result, m["amount_per_day"]), m["from"], m["confidence"] or "confidence n/a"))
        out += ["    to %s: %s a day (%s of the scale spend)" % (t["ad"], _money(result, t["amount_per_day"]), _pct(t["share"]))
                for t in m["to"]]
        out += ["    evidence: %s" % e for e in m["evidence"]]
    if budget["note"]:
        out.append("  %s" % budget["note"])
    out += ["  %s: %s" % (h["action"], "%s - %s" % (h["ad"], h["sentence"])) for h in budget["held"]]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Where the money goes and which budget moves the account's results support.")
    parser.add_argument("path", help="Ads Manager CSV with daily rows, or a .json file of rows")
    parser.add_argument("--verdicts", help="keep-or-kill --json output, for pause spend, room to scale and budget moves")
    parser.add_argument("--pareto-share", type=float, default=80.0,
                        help="percent of spend (and of value) the fewest ads hold (80, a common convention, not a rule)")
    parser.add_argument("--top-n", type=int, default=3, help="ads in the top-N spend share (arbitrary default)")
    parser.add_argument("--age-bands", default="9,18,36",
                        help="day edges for age bands, 9,18,36 giving under 9, 9-17, 18-35 and 36+ days (arbitrary default)")
    parser.add_argument("--min-impressions", type=int, default=1000,
                        help="ads below this are left out of the frequency baseline (arbitrary default)")
    parser.add_argument("--currency", help="currency code to show (default: read from the spend column header)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept,6=tone")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    cm.add_run_arguments(parser)
    args = parser.parse_args(argv)
    try:
        rows, key_map, run_notes = cm.prepare_run(args, cm.load_rows(args.path))
        result = build_spend(rows, key_map, verdicts=args.verdicts, pareto_share=args.pareto_share, top_n=args.top_n,
                             age_bands=parse_age_bands(args.age_bands), min_impressions=args.min_impressions,
                             currency=args.currency, path=args.path)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["run_notes"] = run_notes
    print(json.dumps(result, indent=2) if args.json else "\n".join(run_notes + [render(result)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
