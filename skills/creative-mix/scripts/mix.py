#!/usr/bin/env python3
"""The account's creative portfolio: theme x format coverage, ad types, spend concentration.

Usage: python3 mix.py ads.csv [--pattern concept,format,...] [--key-map PX=concept] [--group-by market] [--no-family] [--json]

Standard library only. Ad names are split with the naming convention (see
creative-context). Names that do not parse go to an "unclassified" bucket that
is counted and listed, never dropped. Ad types outside the six known ones are kept as
written, counted, and flagged so the agent asks the user about them. Performance read-outs (which concepts and
formats are top quartile) use pooled ROAS over BAU ads only, relative to this
account, with no benchmark. Promo and BAU are shown separately, never blended.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

TYPES = ("bau", "promo", "launch", "hype", "partnership", "retention")
OVER_RELIANCE = 60.0  # percent of spend; arbitrary default, set from your own account
# Fewer concepts or formats than this are not ranked against each other. An arbitrary
# default, not a statistical rule: set your own from how many concepts you run.
MIN_FOR_QUARTILES = 5
MAX_GAPS_SHOWN = 8


def concept_families(concepts: Sequence[str]) -> Dict[str, str]:
    """Map each concept to a family: "x-two" and "x-reviews" belong to the family of "x".

    A concept joins the family of the longest other concept that is a
    "-"-delimited prefix of its name. Several ads of one family are ONE concept
    with one fatigue clock.
    """
    names = sorted(set(concepts), key=len)
    parent: Dict[str, str] = {}
    for name in names:
        prefixes = [o for o in names if o != name and name.startswith(o + "-")]
        if prefixes:
            parent[name] = max(prefixes, key=len)

    def root(name: str) -> str:
        while name in parent:
            name = parent[name]
        return name

    return {name: root(name) for name in names}


def pooled(ads: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Metrics from summed base fields over several ads (never an average of ratios)."""
    totals = {}
    for field in cm.NUMERIC_FIELDS:
        values = [a[field] for a in ads if a.get(field) is not None]
        totals[field] = sum(values) if values else None
    return cm.compute_metrics(totals)


def _table(ads: Sequence[Dict[str, Any]], key: str, total: float) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ad in ads:
        groups.setdefault(ad["fields"].get(key) or "unknown", []).append(ad)
    rows = []
    for name, group_ads in groups.items():
        spend = sum(a.get("spend") or 0 for a in group_ads)
        rows.append({key: name, "ads": len(group_ads), "spend": spend,
                     "share": spend / total * 100 if total else None,
                     "roas": pooled(group_ads)["roas"], "cpa": pooled(group_ads)["cpa"]})
    return sorted(rows, key=lambda r: -r["spend"])


def _top_quartile(values: Dict[str, Optional[float]]) -> List[str]:
    known = {k: v for k, v in values.items() if v is not None}
    if len(known) < MIN_FOR_QUARTILES:
        return []
    p75 = statistics.quantiles(list(known.values()), n=4, method="inclusive")[2]
    return sorted(k for k, v in known.items() if v >= p75)


def analyse_mix(rows: Sequence[Dict[str, Any]], pattern: Optional[Sequence[str]] = None,
                families: bool = True, group_by: Optional[Sequence[str]] = None,
                key_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Portfolio tables and read-outs from daily or per-ad rows.

    `group_by` adds a table by any column the data carries (market, objective, ...).
    """
    ads = cm.aggregate_by_ad(rows, key_map=key_map)
    group_by = cm.resolve_group_by(ads, group_by) if group_by else ()
    learned = cm.learn_names([a["ad_name"] for a in ads if a.get("ad_name")], key_map)
    classified, unclassified = [], []
    for ad in ads:
        fields = cm.parse_name(ad["ad_name"], pattern, key_map, learned) if ad.get("ad_name") else {}
        if not fields and pattern is None and ad.get("concept") and ad.get("format"):
            fields = {f: ad.get(f) for f in cm.NAME_FIELDS if ad.get(f)}
        (classified if fields else unclassified).append(dict(ad, fields=fields))
    total = sum(a.get("spend") or 0 for a in classified)
    all_concepts = [a["fields"].get("concept") or "unknown" for a in classified]
    family_of = concept_families(all_concepts) if families else {c: c for c in all_concepts}
    for ad in classified:
        concept = ad["fields"].get("concept") or "unknown"
        ad["concept"] = concept
        ad["family"] = family_of[concept]
        ad["fields"]["family"] = ad["family"]

    by_concept = _table(classified, "family", total)
    group_ads: Dict[str, List[str]] = {}
    for ad in classified:
        group_ads.setdefault(ad["family"], []).append(str(ad.get("ad_id") or ad.get("ad_name")))
    for row in by_concept:
        row["concept"] = row.pop("family")
        row["ad_ids"] = group_ads[row["concept"]]
        row["variants"] = sorted({a["concept"] for a in classified if a["family"] == row["concept"]})
    formats = sorted({a["fields"].get("format") or "unknown" for a in classified},
                     key=lambda f: -sum(a.get("spend") or 0 for a in classified
                                        if (a["fields"].get("format") or "unknown") == f))
    family_names = [r["concept"] for r in by_concept]
    cells = []
    for name in family_names:
        line = {}
        for fmt in formats:
            hit = [a for a in classified if a["family"] == name and (a["fields"].get("format") or "unknown") == fmt]
            line[fmt] = {"ads": len(hit), "spend": sum(a.get("spend") or 0 for a in hit)}
        cells.append(line)

    for ad in classified:
        ad["fields"]["group"] = cm.group_key(ad, group_by) if group_by else None
    by_group = _table(classified, "group", total) if group_by else []

    stage_ads = [a for a in classified if a["fields"].get("funnel_stage")]
    by_stage = _table(stage_ads, "funnel_stage", sum(a.get("spend") or 0 for a in stage_ads))
    for row in by_stage:
        row["stage"] = row.pop("funnel_stage")

    bau = [a for a in classified if a["fields"].get("ad_type") == "bau"]
    fam_roas = {f: pooled([a for a in bau if a["family"] == f])["roas"] for f in family_names
                if any(a["family"] == f for a in bau)}
    fmt_roas = {f: pooled([a for a in bau if (a["fields"].get("format") or "unknown") == f])["roas"]
                for f in formats if any((a["fields"].get("format") or "unknown") == f for a in bau)}
    top_concepts, top_formats = _top_quartile(fam_roas), _top_quartile(fmt_roas)
    gaps = []
    for name, line in zip(family_names, cells):
        for fmt in formats:
            count = line[fmt]["ads"]
            if count > 1:
                continue
            why = []
            if name in top_concepts:
                why.append("top concept")
            if fmt in top_formats:
                why.append("top format")
            if why:
                gaps.append({"concept": name, "format": fmt, "ads": count, "why": why,
                             "strength": len(why)})
    gaps.sort(key=lambda g: (-g["strength"], g["ads"], g["concept"], g["format"]))

    over = []
    scopes = (("all ads", classified), ("BAU ads", bau))
    for label, group in scopes:
        scope_total = sum(a.get("spend") or 0 for a in group)
        if not scope_total:
            continue
        for key, name in (("family", "concept"), (None, "format")):
            sums: Dict[str, float] = {}
            for a in group:
                k = a["family"] if key else (a["fields"].get("format") or "unknown")
                sums[k] = sums.get(k, 0) + (a.get("spend") or 0)
            for k, v in sums.items():
                if v / scope_total * 100 > OVER_RELIANCE:
                    over.append({"scope": label, "kind": name, "name": k, "share": v / scope_total * 100})

    return {
        "classified": len(classified),
        "unclassified": {"count": len(unclassified),
                         "ads": [str(a.get("ad_name") or a.get("ad_id")) for a in unclassified],
                         "spend": sum(a.get("spend") or 0 for a in unclassified)},
        "total_spend": total, "families_on": families,
        "by_format": _table(classified, "format", total),
        "by_concept": by_concept,
        "by_type": _table(classified, "ad_type", total),
        "group_by": list(group_by), "by_group": by_group,
        "unknown_types": sorted({a["fields"]["ad_type"] for a in classified
                                 if a["fields"].get("ad_type") and a["fields"]["ad_type"] not in TYPES}),
        "by_stage": by_stage,
        "grid": {"formats": formats, "families": family_names, "cells": cells},
        "top_concepts": top_concepts, "top_formats": top_formats,
        "gaps": gaps, "over_reliance": over,
        "duplicates": [{"concept": r["concept"], "variants": r["variants"], "ads": r["ad_ids"]}
                       for r in by_concept if len(r["ad_ids"]) > 1],
        "window": cm.data_window(rows),
    }


def _fmt_table(header: Sequence[str], lines: Sequence[Sequence[str]]) -> List[str]:
    widths = [max(len(header[i]), *(len(r[i]) for r in lines)) if lines else len(header[i])
              for i in range(len(header))]
    out = ["  ".join(h.ljust(w) for h, w in zip(header, widths))]
    return out + ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in lines]


def _num(value: Optional[float], digits: int = 2) -> str:
    return "n/a" if value is None else "%.*f" % (digits, value)


def _simple(rows: Sequence[Dict[str, Any]], key: str, label: str, note: str = "") -> List[str]:
    lines = [[str(r[key]) + (note if key == "ad_type" and r[key] not in TYPES else ""), str(r["ads"]),
              _num(r["spend"], 0), _num(r["share"], 1), _num(r["roas"]), _num(r["cpa"])] for r in rows]
    return _fmt_table([label, "ads", "spend", "share%", "roas", "cpa"], lines)


def render(result: Dict[str, Any]) -> str:
    start, end = result["window"]
    un = result["unclassified"]
    out = [
        "Basis: this account's own ads. Window %s to %s. Shares are of classified spend (%s); "
        "roas and cpa are pooled from summed spend, conversions and value." % (
            start or "n/a", end or "n/a", _num(result["total_spend"], 0)),
        "Classified: %d ads. unclassified: %d ads, spend %s (names that do not match the naming "
        "convention are listed, never dropped)." % (result["classified"], un["count"], _num(un["spend"], 0)),
        "Concept grouping: %s. Top quartile = at or above p75 of pooled ROAS across this account's BAU "
        "concepts or formats." % ("'-suffix' variants share a family (--no-family turns it off)"
                                  if result["families_on"] else "off, every concept name is its own concept"),
    ]
    if un["ads"]:
        out += ["  " + name for name in un["ads"]]
    out += ["", "By format"] + _simple(result["by_format"], "format", "format")
    label = "concept family" if result["families_on"] else "concept"
    out += ["", "By %s (several ads of one family count as ONE concept and one fatigue clock)" % label]
    lines = [[r["concept"], str(r["ads"]), _num(r["spend"], 0), _num(r["share"], 1), _num(r["roas"]),
              _num(r["cpa"]), ", ".join(r["variants"]) if len(r["variants"]) > 1 else "-"]
             for r in result["by_concept"]]
    out += _fmt_table([label, "ads", "spend", "share%", "roas", "cpa", "grouped from"], lines)
    out += ["", "By ad type (shown separately, never blended: promo and BAU do different jobs)"]
    out += _simple(result["by_type"], "ad_type", "ad type", " (not in the ad-type list)")
    if result["unknown_types"]:
        out.append("Ad types not in the list: %s. Ask the user which type each one is (one question listing them); "
                   "until then they stay as written, counted, never dropped." % ", ".join(result["unknown_types"]))
    if result["group_by"]:
        out += ["", "By %s" % ", ".join(result["group_by"])]
        out += _simple(result["by_group"], "group", ", ".join(result["group_by"]))
    grid = result["grid"]
    out += ["", "Concept x format grid (ads / spend; gap = no ad)"]
    lines = []
    for name, line in zip(grid["families"], grid["cells"]):
        lines.append([name] + ["gap" if line[f]["ads"] == 0 else "%d / %s" % (line[f]["ads"], _num(line[f]["spend"], 0))
                               for f in grid["formats"]])
    out += _fmt_table(["concept"] + grid["formats"], lines)
    out += ["", "Funnel stage"]
    if result["by_stage"]:
        out += _simple([dict(r, funnel_stage=r["stage"]) for r in result["by_stage"]], "funnel_stage", "stage")
    else:
        out.append("  Names carry no funnel stage field, so there is no funnel stage view. "
                   "Add the field to your naming convention and pass --pattern to read it.")
    out += ["", "Read-outs"]
    if result["top_concepts"] or result["top_formats"]:
        out.append("  Top quartile on pooled ROAS among BAU ads: concepts %s; formats %s." % (
            ", ".join(result["top_concepts"]) or "none", ", ".join(result["top_formats"]) or "none"))
    else:
        out.append("  Performance not read: fewer than %d BAU concepts or formats to rank against each other."
                   % MIN_FOR_QUARTILES)
    out.append("  Gaps worth testing: empty or single-ad cells beside a top-quartile concept or format, "
               "strongest first. A hypothesis to test, not a result:")
    for gap in result["gaps"][:MAX_GAPS_SHOWN]:
        out.append("    %s in %s: %s (%s)" % (gap["concept"], gap["format"],
                                              "gap" if gap["ads"] == 0 else "1 ad", " and ".join(gap["why"])))
    if len(result["gaps"]) > MAX_GAPS_SHOWN:
        out.append("    ... %d more (see --json)" % (len(result["gaps"]) - MAX_GAPS_SHOWN))
    if not result["gaps"]:
        out.append("    none found")
    if result["over_reliance"]:
        out.append("  Over-reliance (more than %g%% of spend; an arbitrary default, set it from your own account):" % OVER_RELIANCE)
        out += ["    %s %s holds %.0f%% of %s" % (o["kind"], o["name"], o["share"], o["scope"]) for o in result["over_reliance"]]
    else:
        out.append("  Over-reliance: no concept family or format holds more than %g%% of spend." % OVER_RELIANCE)
    if result["duplicates"]:
        out.append("  Near-duplicates counted as one concept (override with --no-family):")
        out += ["    %s: %s (ads %s)" % (d["concept"], ", ".join(d["variants"]), ", ".join(d["ads"]))
                for d in result["duplicates"]]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Creative portfolio mix from an Ads Manager export.")
    parser.add_argument("path", help="Ads Manager CSV, or a .json file of rows")
    parser.add_argument("--pattern", help="comma-separated naming-convention fields, in order "
                                          "(default: concept,format,creator,ad_type,product,tone,launch_date)")
    parser.add_argument("--key-map", help="extra KEY=field pairs for KEY:value ad names, e.g. PX=concept")
    parser.add_argument("--group-by", help="also show a table by these comma-separated columns: a name field or "
                                           "any column in the data, e.g. market or format,market")
    parser.add_argument("--no-family", action="store_true",
                        help="do not group '-suffix' variants of a concept into one family")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    pattern = [f.strip() for f in args.pattern.split(",")] if args.pattern else None
    group_by = tuple(g.strip() for g in args.group_by.split(",") if g.strip()) if args.group_by else None
    try:
        key_map = cm.parse_key_map(args.key_map) if args.key_map else None
        result = analyse_mix(cm.load_rows(args.path), pattern, families=not args.no_family,
                             group_by=group_by, key_map=key_map)
    except (cm.GroupColumnError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
