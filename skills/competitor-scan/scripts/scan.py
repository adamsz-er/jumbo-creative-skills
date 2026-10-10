#!/usr/bin/env python3
"""Cluster rivals' live ads and compare them with your own winners.

Usage: scan.py ads.csv [--evidence evidence.json] [--as-of YYYY-MM-DD] [--long-days N] [--crowded-share PCT]
                       [--source TEXT] [--keep-text] [--json]

Reads a CSV or JSON file of rivals' ads copied from the public Meta Ad Library
(https://www.facebook.com/ads/library). It reads TEXT only: it makes no network
calls and never downloads, stores or embeds images, videos or URLs. Every http://,
https:// or www. link, wherever it sits in a value, is removed and counted.

Each ad is sorted by a transparent keyword heuristic into angles, a hook type, an
offer type and a format, and given a days-running count. The ads are then clustered
per dimension and compared with your own concepts (the --evidence file is the output
of the evidence script run with --json): angles that are crowded, open ground, worth
testing, and not to chase. The keyword lists are a first pass, not a verdict: read
the ads and correct the sorting.

The defaults (--long-days 36, --crowded-share 60) are arbitrary: set them from your
own account and the category you are scanning. A long run suggests the ad is working
for the rival; it is not proof.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_SOURCE = "Meta Ad Library (public)"
DEFAULT_LONG_DAYS = 36
DEFAULT_CROWDED_SHARE = 60.0
NO_EVIDENCE = "n/a (no evidence file: run the evidence script with --json and pass --evidence)"
NO_TEXT = "n/a (no text)"
MISSING_STARTED = "n/a (missing started date)"
UNCLASSIFIED = "unclassified"

ANGLE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "problem": ("problem", "struggle", "tired of", "stop", "never again", "finally"),
    "proof": ("reviews", "rated", "customers", "tested", "proven", "stars", "sold"),
    "offer": ("% off", "sale", "save", "discount", "deal", "free shipping", "gift"),
    "comparison": ("vs", "versus", "compared", "unlike", "better than"),
    "story": ("founder", "our story", "started", "why we", "made by"),
    "education": ("how to", "tips", "guide", "learn", "steps"),
    "identity": ("for people who", "if you're a", "made for"),
    "feature": ("waterproof", "lightweight", "material", "made from", "features"),
    "urgency": ("ends", "last chance", "today only", "limited", "hurry", "final"),
}
"""Angle keywords, lowercase. A first pass, not a verdict: an ad can match several angles, so correct them by reading the ads."""

CONCEPT_EXTRAS: Dict[str, Tuple[str, ...]] = {
    "proof": ("social",),
    "story": ("behind",),
    "offer": ("bundle", "percent"),
}
"""Extra words that map one of your own concept names to an angle, on top of the angle name and its keywords. A first pass, not a verdict."""

HOOK_NEGATIVE = ("don't", "stop", "never", "mistake", "avoid", "worst")
"""Words that make an opening negative. A first pass, not a verdict; correct the hook types you disagree with."""

OFFER_BUNDLE = ("bundle", "kit", "set", "buy 2", "bogo", "buy one")
"""Words that mark a bundle offer. A first pass, not a verdict; correct the offer types you disagree with."""

OFFER_GIFT = ("free gift", "gift with", "bonus")
"""Words that mark a gift with purchase. A first pass, not a verdict; correct the offer types you disagree with."""

OFFER_TIERED = ("spend more save more", "the more you buy")
"""Phrases that mark a tiered offer. A first pass, not a verdict; correct the offer types you disagree with."""

FORMAT_WORDS: Dict[str, Tuple[str, ...]] = {
    "image": ("image", "photo", "static", "picture"),
    "video": ("video", "reel"),
    "carousel": ("carousel",),
}
"""Words that normalise the format column. Anything else filled in is "other"; blank is "unknown"."""

ALIASES: Dict[str, Tuple[str, ...]] = {
    "advertiser": ("advertiser",),
    "ad_text": ("ad_text", "body", "primary_text", "text"),
    "headline": ("headline", "title"),
    "format": ("format", "media_type"),
    "started": ("started", "start_date", "started_running"),
    "cta": ("cta", "call_to_action"),
    "platforms": ("platforms",),
}
DIMENSIONS = ("angle", "hook_type", "offer", "format")
MONEY_OFF = re.compile(r"[$£€]\s?\d[\d.,]*\s*off\b|\bdollars off\b")
PERCENT_OFF = re.compile(r"\d+\s?% off")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _has(text: str, words: Sequence[str]) -> bool:
    for word in words:
        lead = r"(?<!\w)" if word[0].isalnum() else ""
        if re.search(lead + re.escape(word) + r"(?!\w)", text):
            return True
    return False


def _clean(text: str) -> str:
    return text.lower().replace("’", "'").strip()


def find_angles(text: str) -> List[str]:
    """Every angle whose keywords appear in the text, or ["unclassified"]."""
    low = _clean(text)
    found = [angle for angle, words in ANGLE_KEYWORDS.items() if _has(low, words)]
    return found or [UNCLASSIFIED]


def hook_type(text: str) -> str:
    """The opening's type, read from the first sentence."""
    first = SENTENCE_END.split(text.strip(), maxsplit=1)[0]
    low = _clean(first)
    if low[:1] in ("\"", "'", "“", "‘"):
        return "testimonial"
    if low.startswith("pov") or low.startswith("when you"):
        return "pov"
    if low.startswith("how"):
        return "how-to"
    if low.endswith("?"):
        return "question"
    if any(ch.isdigit() for w in low.split()[:6] for ch in w):
        return "number"
    if _has(low, HOOK_NEGATIVE):
        return "negative"
    return "claim"


def offer_type(text: str) -> str:
    """The kind of deal the copy states, or "none"."""
    low = _clean(text)
    if _has(low, OFFER_TIERED):
        return "tiered"
    if PERCENT_OFF.search(low):
        return "percent off"
    if MONEY_OFF.search(low):
        return "money off"
    if _has(low, ("free shipping",)):
        return "free shipping"
    if _has(low, OFFER_GIFT):
        return "gift with purchase"
    if _has(low, OFFER_BUNDLE):
        return "bundle"
    return "none"


def normalise_format(value: str) -> str:
    low = _clean(value)
    if not low:
        return "unknown"
    for name, words in FORMAT_WORDS.items():
        if _has(low, words):
            return name
    return "other"


def parse_date(value: str) -> Optional[dt.date]:
    text = value.strip().split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _norm_header(header: str) -> str:
    return re.sub(r"[\s\-]+", "_", header.strip().lower())


def read_input(path: str) -> List[Dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    if path.lower().endswith(".json"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("ads") or data.get("rows")
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise ValueError("JSON input must be a list of ad objects (or an object with an \"ads\" list)")
        return data
    return list(csv.DictReader(io.StringIO(text, newline="")))


URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)


def canonical_rows(raw: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], int]:
    """Rows keyed by canonical field, URLs removed from every value, and how many were removed."""
    if not raw:
        raise ValueError("input has no ads")
    headers = {_norm_header(k): k for r in raw for k in r}
    column: Dict[str, Optional[str]] = {}
    for field, names in ALIASES.items():
        column[field] = next((headers[n] for n in names if n in headers), None)
    missing = []
    if column["advertiser"] is None:
        missing.append("advertiser")
    if column["ad_text"] is None:
        missing.append("ad_text (or body, primary_text, text)")
    if missing:
        raise ValueError("input is missing the required column: " + ", ".join(missing))
    skipped = 0
    rows: List[Dict[str, str]] = []
    for number, record in enumerate(raw, start=1):
        skipped += sum(len(URL_RE.findall(str(v or ""))) for v in record.values())
        row = {}
        for field, name in column.items():
            value = "" if name is None else str(record.get(name) or "").strip()
            row[field] = re.sub(r"[ \t]{2,}", " ", URL_RE.sub("", value)).strip()
        if not row["advertiser"]:
            raise ValueError("row %d has no advertiser" % number)
        rows.append(row)
    return rows, skipped


def classify(row: Dict[str, str], as_of: dt.date, long_days: int, keep_text: bool) -> Dict[str, Any]:
    both = " ".join(p for p in (row["ad_text"], row["headline"]) if p)
    out: Dict[str, Any] = {"advertiser": row["advertiser"]}
    if both:
        out.update(angle=find_angles(both), hook_type=hook_type(row["ad_text"] or row["headline"]),
                   offer=offer_type(both))
    else:
        out.update(angle=[NO_TEXT], hook_type=NO_TEXT, offer=NO_TEXT)
    out["format"] = normalise_format(row["format"])
    started = parse_date(row["started"]) if row["started"] else None
    days = (as_of - started).days if started else None
    out["days_running"] = days if days is not None and days >= 0 else None
    if out["days_running"] is None:
        out["days_running_note"] = MISSING_STARTED if started is None else "n/a (started after the as-of date)"
        out["long_running"] = None
    else:
        out["long_running"] = days >= long_days
    if keep_text:
        out.update(ad_text=row["ad_text"], headline=row["headline"])
    return out


def build_clusters(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    clusters: Dict[str, List[Dict[str, Any]]] = {}
    for dim in DIMENSIONS:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            values = r[dim] if isinstance(r[dim], list) else [r[dim]]
            if values == [NO_TEXT]:
                continue
            for v in values:
                groups.setdefault(v, []).append(r)
        total = sum(1 for r in rows if r[dim] not in (NO_TEXT, [NO_TEXT]))
        items = []
        for value, ads in groups.items():
            names = sorted({a["advertiser"] for a in ads})
            items.append({"value": value, "ads": len(ads), "advertisers": len(names), "advertiser_names": names,
                          "long_running": sum(1 for a in ads if a["long_running"]),
                          "share": round(100.0 * len(ads) / total, 1)})
        clusters[dim] = sorted(items, key=lambda i: (-i["ads"], i["value"]))
    return clusters


def concept_angles(concept: str) -> List[str]:
    low = re.sub(r"[-_]+", " ", _clean(concept))
    return [a for a, words in ANGLE_KEYWORDS.items() if _has(low, words + (a,) + CONCEPT_EXTRAS.get(a, ()))]


def brand_by_angle(evidence: Any) -> Dict[str, List[Tuple[str, str]]]:
    if not isinstance(evidence, dict) or not isinstance(evidence.get("angles"), list):
        raise ValueError("--evidence must be the evidence script's --json output (an object with \"angles\")")
    mapped: Dict[str, List[Tuple[str, str]]] = {}
    for entry in evidence["angles"]:
        for angle in concept_angles(str(entry.get("concept") or "")):
            mapped.setdefault(angle, []).append((str(entry["concept"]), str(entry.get("label") or "unjudged")))
    return mapped


def compare(clusters: Dict[str, List[Dict[str, Any]]], advertisers: int, crowded_share: float,
            brand: Optional[Dict[str, List[Tuple[str, str]]]]) -> Dict[str, List[Dict[str, Any]]]:
    seen = {c["value"]: c for c in clusters["angle"] if c["value"] != UNCLASSIFIED}
    stats = {a: seen.get(a, {"advertisers": 0, "long_running": 0}) for a in ANGLE_KEYWORDS}

    def brand_text(angle: str) -> str:
        if brand is None:
            return NO_EVIDENCE
        return "; ".join("%s: %s" % pair for pair in brand.get(angle, [])) or "not tried"

    def item(angle: str, why: str) -> Dict[str, Any]:
        return {"label": angle, "why": why, "advertisers": stats[angle]["advertisers"],
                "long_running": stats[angle]["long_running"], "brand": brand_text(angle)}

    def labels(angle: str) -> List[str]:
        return [label for _, label in (brand or {}).get(angle, [])]

    crowded = [item(a, "used by %d of %d advertisers (%.0f%%)" % (s["advertisers"], advertisers,
                                                                  100.0 * s["advertisers"] / advertisers))
               for a, s in sorted(stats.items(), key=lambda kv: (-kv[1]["advertisers"], kv[0]))
               if 100.0 * s["advertisers"] / advertisers >= crowded_share]
    open_ground = [item(a, "used by %s of %d advertisers" % (s["advertisers"] or "none", advertisers))
                   for a, s in sorted(stats.items(), key=lambda kv: (-kv[1]["long_running"], -kv[1]["advertisers"], kv[0]))
                   if s["advertisers"] <= 1]
    worth: List[Dict[str, Any]] = []
    for a, s in sorted(stats.items(), key=lambda kv: (-kv[1]["long_running"], kv[0])):
        if s["long_running"] and (brand is None or a not in brand):
            tail = "you have not tried it" if brand is not None else "no evidence file to check what you have tried"
            worth.append(item(a, "rivals run it long (long-running ads: %d, advertisers using it: %d); %s"
                              % (s["long_running"], s["advertisers"], tail)))
    for a, s in stats.items():
        if brand is not None and "winning" in labels(a) and s["advertisers"] <= 1:
            worth.append(item(a, "your own ads win with it and rivals are thin there (advertisers using it: %d)"
                              % s["advertisers"]))
    not_chase = [item(a, "your own ads say this has not worked for you") for a in stats
                 if brand is not None and "losing" in labels(a) and "winning" not in labels(a)]
    return {"crowded": crowded, "open_ground": open_ground, "worth_testing": worth, "not_to_chase": not_chase}


def build_scan(records: Sequence[Dict[str, str]], skipped_urls: int, as_of: dt.date, long_days: int,
               crowded_share: float, source: str = DEFAULT_SOURCE, evidence: Any = None,
               keep_text: bool = False) -> Dict[str, Any]:
    rows = [classify(r, as_of, long_days, keep_text) for r in records]
    clusters = build_clusters(rows)
    advertisers = len({r["advertiser"] for r in rows})
    brand = brand_by_angle(evidence) if evidence is not None else None
    result: Dict[str, Any] = {
        "source": source, "as_of": as_of.isoformat(), "advertisers": advertisers, "ads": len(rows),
        "skipped_urls": skipped_urls, "no_text": sum(1 for r in records if not r["ad_text"]),
        "clusters": clusters}
    result.update(compare(clusters, advertisers, crowded_share, brand))
    result["rows"] = rows
    result["settings"] = {"long_days": long_days, "crowded_share": crowded_share, "as_of": as_of.isoformat(),
                          "keep_text": keep_text, "evidence_supplied": evidence is not None}
    return result


def _line(items: Sequence[Dict[str, Any]], empty: str) -> str:
    return "%s: %s" % (items[0]["label"], items[0]["why"]) if items else empty


def render(result: Dict[str, Any]) -> str:
    crowded_all = result["clusters"]["angle"]
    top = next((c for c in crowded_all if c["value"] not in (UNCLASSIFIED, NO_TEXT)), None)
    lines = [
        "Most crowded angle: %s." % ("%s, used by %d of %d advertisers" % (top["value"], top["advertisers"], result["advertisers"])
                                     if top else "none (no ad matched an angle)"),
        "Best open ground: %s." % _line(result["open_ground"], "none (every angle is used by two or more advertisers)"),
        "Top worth testing: %s." % _line(result["worth_testing"], "nothing stands out yet"),
        "",
        "%d ads from %d advertisers, as of %s (source: %s)." % (result["ads"], result["advertisers"], result["as_of"],
                                                                result["source"]),
        "Removed %d URLs from the text; images and videos are not downloaded or kept." % result["skipped_urls"],
    ]
    if result["no_text"]:
        lines.append("%d ads have no text: kept for format and longevity only." % result["no_text"])
    undated = sum(1 for r in result["rows"] if r["long_running"] is None)
    if undated:
        lines.append("%d ads have no usable start date: %s." % (undated, MISSING_STARTED))
    lines.append("Long-running (%d or more days; a long run suggests the ad is working for them, it is not proof): %d ads."
                 % (result["settings"]["long_days"], sum(1 for r in result["rows"] if r["long_running"])))
    for title, key in (("Crowded", "crowded"), ("Open ground", "open_ground"), ("Worth testing", "worth_testing"),
                       ("Not to chase", "not_to_chase")):
        lines += ["", title + ":"]
        lines += ["  %s: %s | your side: %s" % (i["label"], i["why"], i["brand"]) for i in result[key]] or ["  none"]
    for dim in DIMENSIONS:
        lines += ["", "By %s (ads, advertisers, long-running):" % dim.replace("_", " ")]
        lines += ["  %s: %d, %d, %d" % (c["value"], c["ads"], c["advertisers"], c["long_running"])
                  for c in result["clusters"][dim]] or ["  none"]
    lines += ["", "The sorting is a keyword first pass, not a verdict: read the ads and correct it."]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cluster rivals' ads and compare them with your own winners.")
    parser.add_argument("path", help="CSV or JSON file of rivals' ads (advertiser and ad text columns required)")
    parser.add_argument("--evidence", help="the evidence script's --json output, to compare with your own concepts")
    parser.add_argument("--as-of", help="date to count days running to, YYYY-MM-DD (default: today)")
    parser.add_argument("--long-days", type=int, default=DEFAULT_LONG_DAYS,
                        help="days running at or above which an ad counts as long-running (arbitrary default; set it from your category)")
    parser.add_argument("--crowded-share", type=float, default=DEFAULT_CROWDED_SHARE,
                        help="percent of advertisers using an angle for it to count as crowded (arbitrary default)")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="where the ads were collected from")
    parser.add_argument("--keep-text", action="store_true", help="keep each ad's text in the rows output")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    try:
        as_of = dt.date.today() if args.as_of is None else dt.date.fromisoformat(args.as_of)
        if args.long_days < 1 or not 0 < args.crowded_share <= 100:
            raise ValueError("--long-days must be at least 1 and --crowded-share between 0 and 100")
        records, skipped = canonical_rows(read_input(args.path))
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")) if args.evidence else None
        result = build_scan(records, skipped, as_of, args.long_days, args.crowded_share, args.source, evidence,
                            args.keep_text)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
