"""Public industry figures by creative format, shown as context beside an account's own numbers.

A figure is only ever drawn when a cited public source gives it for that format. Each entry says how its definition compares
with ours: "matches", "not_stated" (the source does not say; the band is drawn with its caveat printed) or "differs" (no band). Nothing here feeds a verdict, a grade or "Do these first": the account is graded against its own ads.
Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DATA = Path(__file__).resolve().parent.parent / "references" / "benchmarks.json"

NO_BAND_METRICS = {
    "hold_rate": "No industry band for hold rate: the only public source counts views of a different fixed length against 3-second views, "
                 "and ours is ThruPlays against 3-second plays, so the two are not the same measure.",
}
NO_SOURCE = "no public figure found for this metric"
NOT_COVERED = "no public figure for this format"
GUIDE = "A guide, not a target: other accounts, attribution and products."


DEFINITIONS = ("matches", "not_stated", "differs")


def check_definition(entry: Dict[str, Any]) -> None:
    if entry.get("definition") not in DEFINITIONS:
        raise ValueError("benchmark entry for %r (%s): definition must be one of %s, got %r"
                         % (entry.get("metric"), entry.get("source"), ", ".join(DEFINITIONS), entry.get("definition")))


def load(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    entries = json.loads((path or DATA).read_text(encoding="utf-8"))
    for entry in entries:
        check_definition(entry)
    return entries


def source_key(fmt: Any, available: Sequence[str]) -> Optional[str]:
    """Which of a source's format keys one of our format words belongs to; None when it does not map (never a guess).

    Video words (video, ugc video, reel) map to a source's plain "video" key, since the sources here do not split video finer.
    A bare "ugc", "story" or "partnership" could be a still or a video, so it maps to nothing.
    """
    words = set(re.split(r"[^a-z0-9]+", str(fmt or "").lower())) - {""}
    ordered = (("carousel", {"carousel"}), ("catalog", {"collection", "catalogue", "catalog"}), ("dynamic", {"dynamic", "dpa"}),
               ("video", {"video", "reel", "reels"}), ("image", {"static", "image"}))
    for key, names in ordered:
        if words & names:
            return key if key in available else None
    return None


def entry_for(metric: str, entries: Optional[Sequence[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    return next((e for e in (load() if entries is None else entries) if e["metric"] == metric), None)


def lookup(metric: str, fmt: Any, currency: Optional[str], entries: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """(band, "") when a figure applies, else (None, the plain reason there is none).

    A band is {value, low, high, unit, source, url, year, sample, definition, caveat}; low and high default to the value.
    """
    if metric in NO_BAND_METRICS:
        return None, NO_BAND_METRICS[metric]
    entry = entry_for(metric, entries)
    if entry is None:
        return None, NO_SOURCE
    check_definition(entry)
    if entry["definition"] == "differs":
        return None, "the source's definition differs from ours, so there is no band"
    needs = entry.get("currency")
    if needs and (currency or "").upper() != needs.upper():
        who = "%s accounts" % currency.upper() if currency else "an account whose currency is not stated"
        return None, "industry figure is in %s; not shown for %s" % (needs, who)
    key = source_key(fmt, list(entry["formats"]))
    if key is None:
        return None, NOT_COVERED
    figure = entry["formats"][key]
    return {"value": figure["value"], "low": figure.get("low", figure["value"]), "high": figure.get("high", figure["value"]),
            "unit": entry["unit"], "source": entry["source"], "url": entry["url"], "year": str(entry["published"])[:4],
            "sample": entry["sample"], "definition": entry["metric_definition"], "caveat": entry["caveat"]}, ""


def citation(band: Dict[str, Any]) -> str:
    """The line printed under a band: source, year, sample, definition caveat and the not-a-target warning."""
    return "Industry figure: %s, %s, %s. %s %s" % (band["source"], band["year"], band["sample"], band["caveat"], GUIDE)


def source_lines(used: Sequence[Dict[str, Any]]) -> List[str]:
    """One footer line per distinct source actually drawn on the page, with its URL and year."""
    seen: Dict[str, str] = {}
    for band in used:
        seen.setdefault(band["url"], "%s (%s), %s" % (band["source"], band["year"], band["url"]))
    return list(seen.values())
