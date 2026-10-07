#!/usr/bin/env python3
"""Creative metrics for Meta ad exports (Python 3.9+, standard library only).

Loads an Ads Manager CSV export or Meta API rows, computes the creative metrics
defined in references/metrics.md, aggregates per ad, builds baselines from the
account's own data, and reads fatigue trends. No benchmarks live here: every
judgement is relative to the account's own distribution.

CLI: python3 creative_metrics.py ads.csv [--json]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import statistics
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# metric -> (numerator fields, denominator fields, scale). The first field in a
# tuple that has a value is used; the others are fallbacks.
METRICS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...], float]] = {
    "hook_rate": (("video_views_3s",), ("impressions",), 100.0),
    "hold_rate": (("video_thruplay",), ("video_views_3s",), 100.0),
    "video_completion_rate": (("video_thruplay",), ("impressions",), 100.0),
    "ctr": (("link_clicks", "clicks"), ("impressions",), 100.0),
    "cpm": (("spend",), ("impressions",), 1000.0),
    "cpc": (("spend",), ("link_clicks", "clicks"), 1.0),
    "cpa": (("spend",), ("conversions",), 1.0),
    "roas": (("conversion_value",), ("spend",), 1.0),
    "cvr": (("conversions",), ("clicks", "link_clicks"), 100.0),
    "add_to_cart_rate": (("add_to_carts",), ("clicks", "link_clicks"), 100.0),
    "cost_per_add_to_cart": (("spend",), ("add_to_carts",), 1.0),
    "cost_per_lead": (("spend",), ("leads",), 1.0),
    "engagement_rate": (("engagements",), ("impressions",), 100.0),
    "frequency": (("impressions",), ("reach",), 1.0),
    "mer": (("revenue",), ("spend",), 1.0),
}

# An alias is another name for the same metric, never a second metric.
METRIC_ALIASES = {"thumb_stop_rate": "hook_rate"}

NUMERIC_FIELDS = (
    "spend", "impressions", "reach", "video_views_3s", "video_thruplay",
    "link_clicks", "clicks", "conversions", "conversion_value", "add_to_carts",
    "revenue", "leads", "shares", "saves", "comments",
)
COST_PER_VIEW = "cost_per_action_type:video_view"
DERIVED_3S = "derived: spend / cost per 3-second view"
AGE_FROM_CREATED = "created_time"
AGE_FROM_DELIVERY = "first delivery in window (older ads may be understated)"
# The original positional convention: what a name of exactly this many parts is read as.
LEGACY_PATTERN = ("concept", "format", "creator", "ad_type", "product", "tone", "launch_date")
NAME_FIELDS = LEGACY_PATTERN + ("market", "funnel_stage", "collection", "range")
AD_TYPES = ("bau", "promo", "launch", "hype", "partnership", "retention")
# Words an account uses for the six ad types. A word not here is kept as written, counted, and asked about.
SYNONYMS = {
    "sale": "promo", "promo": "promo", "offer": "promo", "discount": "promo", "bfcm": "promo",
    "bau": "bau", "evergreen": "bau", "always-on": "bau", "aon": "bau",
    "launch": "launch", "drop": "launch", "newin": "launch",
    "hype": "hype", "teaser": "hype", "tease": "hype",
    "collab": "partnership", "partnership": "partnership", "influencer": "partnership", "whitelist": "partnership", "spark": "partnership",
    "retention": "retention", "rtg": "retention", "existing": "retention", "loyalty": "retention",
}
# KEY in a KEY:value name segment -> canonical field. A key that is not listed is read from its
# values (see learn_names); --key-map overrides both.
KEY_MAP = {
    "TYPE": "ad_type", "ADTYPE": "ad_type",
    "ANGLE": "concept", "CONCEPT": "concept", "THEME": "concept",
    "FMT": "format", "FORMAT": "format",
    "SKU": "product", "PROD": "product", "PRODUCT": "product",
    "COLL": "collection", "COLLECTION": "collection",
    "RNG": "range", "RANGE": "range",
    "CR": "creator", "CREATOR": "creator", "TALENT": "creator",
    "MKT": "market", "MARKET": "market", "GEO": "market", "REGION": "market",
    "STG": "funnel_stage", "STAGE": "funnel_stage", "FUNNEL": "funnel_stage",
    "TONE": "tone",
    "LD": "launch_date", "DATE": "launch_date", "LAUNCH": "launch_date",
}
SEPARATORS = (" | ", "|", " _ ", "_", " - ")
FORMAT_WORDS = frozenset(("image", "static", "video", "carousel", "collection", "catalogue", "catalog",
                          "ugc", "reel", "story", "dpa"))
MARKET_CODES = frozenset((
    "AU NZ US UK GB CA IE DE FR ES IT NL SE NO DK FI JP KR CN HK SG IN AE SA ZA BR MX AR CL CO PE PL CH BE PT "
    "TR IL TH MY ID PH VN TW EG NG KE INT ROW ME EU").split())
# Detection asks the user only below this share of names read (an arbitrary default: set it from how
# messy your account's names are), or when a second convention covers at least COEXIST_SHARE percent.
MATCH_RATE_ASK = 85.0
COEXIST_SHARE = 5.0
UNPARSED_SHOWN = 8  # display cap on listed examples (arbitrary)

_ALIASES = {
    "spend": "spend", "amountspent": "spend", "adspend": "spend",
    "impressions": "impressions",
    "reach": "reach",
    "3secondvideoplays": "video_views_3s", "3secvideoplays": "video_views_3s",
    "3secondvideoviews": "video_views_3s", "videoviews3s": "video_views_3s",
    "videoview": "video_views_3s", "videoviews": "video_views_3s",
    "thruplays": "video_thruplay", "thruplay": "video_thruplay",
    "videothruplay": "video_thruplay", "videothruplaywatchedactions": "video_thruplay",
    "linkclicks": "link_clicks", "inlinelinkclicks": "link_clicks",
    "clicksall": "clicks", "clicks": "clicks", "allclicks": "clicks",
    "purchases": "conversions", "websitepurchases": "conversions",
    "purchasesconversionvalue": "conversion_value",
    "websitepurchasesconversionvalue": "conversion_value",
    "purchaseconversionvalue": "conversion_value", "conversionvalue": "conversion_value",
    "addstocart": "add_to_carts", "addtocart": "add_to_carts",
    "addtocarts": "add_to_carts", "websiteaddstocart": "add_to_carts",
    "revenue": "revenue", "storerevenue": "revenue",
    "lead": "leads", "leads": "leads", "postshares": "shares", "postshare": "shares", "shares": "shares",
    "postsave": "saves", "postsaves": "saves", "saves": "saves",
    "comment": "comments", "comments": "comments", "postcomments": "comments",
    "adname": "ad_name", "adid": "ad_id",
    "day": "date", "date": "date", "reportingstarts": "date", "datestart": "date",
    # Meta's hosted Ads MCP field names (not in Meta's documentation as of this writing and may change: check in your own session).
    "linkclick": "link_clicks", "omnipurchase": "conversions",
    "omnipurchasevalues": "conversion_value", "omniaddtocart": "add_to_carts",
    "costperactiontypevideoview": COST_PER_VIEW, "createdtime": "created_time",
}
# `id` and `name` are ad fields only on a row that is marked as an ad row.
_ID_NAME_ALIASES = {"id": "ad_id", "name": "ad_name"}
# "Results" means whatever the campaign objective optimises for, so it only
# fills conversions when no purchases column exists.
_WEAK_ALIASES = {"results": "conversions"}
_STRING_FIELDS = ("ad_name", "ad_id", "date", "created_time")
_API_ACTION_TYPES = {
    "video_view": "video_views_3s",
    "purchase": "conversions",
    "add_to_cart": "add_to_carts",
    "lead": "leads",
    "comment": "comments",
    "post": "shares",
    "onsite_conversion.post_save": "saves",
}
_API_VALUE_TYPES = {"purchase": "conversion_value"}
_API_LIST_FIELDS = {"video_thruplay_watched_actions": "video_thruplay"}


class GroupColumnError(ValueError):
    """A requested --group-by column is not in the data."""


def resolve_metric(name: str) -> str:
    """Return the canonical metric id for a metric name or alias."""
    name = METRIC_ALIASES.get(name, name)
    if name not in METRICS:
        raise KeyError("unknown metric %r (known: %s)" % (name, ", ".join(METRICS)))
    return name


def _norm(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return _num(value.get("value"))
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text = re.sub(r"[,$€£%\s]", "", str(value))
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _list_value(items: Any) -> Optional[float]:
    """Sum the `value` of Meta API action-stat lists; None if there are none."""
    if not isinstance(items, list):
        return _num(items)
    values = [_num(i.get("value")) for i in items if isinstance(i, dict)]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _is_ad_row(raw: Dict[str, Any], level: Optional[str]) -> bool:
    if str(raw.get("level") or level or "").lower() == "ad":
        return True
    return any(_norm(k) == "adname" for k in raw)


def _normalise_row(raw: Dict[str, Any], level: Optional[str] = None) -> Dict[str, Any]:
    passthrough: Dict[str, Any] = {}
    out: Dict[str, Any] = {}
    weak: Dict[str, Any] = {}
    id_name: Dict[str, Any] = {}
    ad_row = _is_ad_row(raw, level)

    def put(target: Dict[str, Any], field: str, value: Any) -> None:
        if value is not None and target.get(field) is None:
            target[field] = value

    for key, value in raw.items():
        if key in ("actions", "action_values") and isinstance(value, list):
            lookup = _API_ACTION_TYPES if key == "actions" else _API_VALUE_TYPES
            for item in value:
                if isinstance(item, dict) and item.get("action_type") in lookup:
                    target = lookup[item["action_type"]]
                    put(out, target, _num(item.get("value")))
                    if target == "conversions" and "conversions_source" not in out:
                        out["conversions_source"] = "actions:purchase"
            continue
        if key in _API_LIST_FIELDS:
            put(out, _API_LIST_FIELDS[key], _list_value(value))
            continue
        norm = _norm(key)
        field = _ALIASES.get(norm) or ("spend" if norm.startswith("amountspent") else None)
        if field is None and ad_row and norm in _ID_NAME_ALIASES:
            text = "" if value is None else str(value).strip()
            if text:
                id_name[_ID_NAME_ALIASES[norm]] = text
        elif field in _STRING_FIELDS:
            text = "" if value is None else str(value).strip()
            put(out, field, text or None)
        elif field:
            number = _num(value)
            if field == "conversions" and number is not None and "conversions_source" not in out:
                out["conversions_source"] = str(key)
            put(out, field, number)
        elif norm in _WEAK_ALIASES:
            number = _num(value)
            if number is not None:
                weak[_WEAK_ALIASES[norm]] = (number, str(key))
        elif norm in METRICS or norm in METRIC_ALIASES:
            passthrough["reported_" + norm] = value
        else:
            passthrough[key] = value
    for field, (value, source) in weak.items():
        if out.get(field) is None:
            out[field] = value
            out["conversions_source"] = source
    for field, text in id_name.items():
        if out.get(field) is None:
            out[field] = text
    if out.get("video_views_3s") is not None:
        kept = raw.get("video_views_3s_source")
        out["video_views_3s_source"] = str(kept) if kept else "reported"
    else:
        spend, per_view = out.get("spend"), out.get(COST_PER_VIEW)
        if spend is not None and per_view is not None and per_view > 0:
            out["video_views_3s"] = spend / per_view
            out["video_views_3s_source"] = DERIVED_3S
    passthrough.update(out)
    return passthrough


def load_rows(path_or_rows: Union[str, "os.PathLike[str]", Iterable[Dict[str, Any]]],
              level: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load an Ads Manager CSV (path), a .json file of rows, or Meta API rows (list of dicts).

    A .json path holds a list of row dicts, or an API response with a "data" list.

    Column names are mapped to canonical fields through an alias map, ignoring
    case and punctuation. Numeric fields become floats (blank cells become
    None). Columns that Meta computes itself (ctr, cpm, frequency, ...) are kept
    as `reported_<name>` and never used: every metric is recomputed from counts.
    Unknown columns pass through untouched. `conversions_source` records which
    column fed conversions: "Purchases" wins over "Results" when both exist, so
    a non-purchase objective's Results never silently become purchases.

    Meta's hosted Ads MCP names are mapped too (link_click, omni_purchase,
    omni_purchase_values, omni_add_to_cart, date_start, created_time). Its `id`
    and `name` fields are ad fields only on an ad row: pass level="ad", or the
    row carries `level` == "ad" or an `ad_name`. Amounts shaped like
    {"value": x, "unit": ...} read as x. When 3-second plays are missing but
    spend and `cost_per_action_type:video_view` exist, plays are derived as
    spend / cost per view and `video_views_3s_source` says so.
    """
    if isinstance(path_or_rows, (str, bytes)) or hasattr(path_or_rows, "__fspath__"):
        if str(path_or_rows).lower().endswith(".json"):
            with open(path_or_rows, encoding="utf-8-sig") as handle:
                loaded = json.load(handle)
            raw_rows = loaded.get("data") or loaded.get("rows") or [] if isinstance(loaded, dict) else loaded
        else:
            with open(path_or_rows, newline="", encoding="utf-8-sig") as handle:
                raw_rows = list(csv.DictReader(handle))
    else:
        raw_rows = path_or_rows
    return [_normalise_row(dict(r), level) for r in raw_rows]


def _pick(row: Dict[str, Any], fields: Sequence[str]) -> Tuple[str, Optional[float]]:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return field, value
    return fields[0], None


ENGAGEMENT_PARTS = ("shares", "saves", "comments")


def _with_engagements(row: Dict[str, Any]) -> Dict[str, Any]:
    """The row plus `engagements` = shares + saves + comments, None unless all three are present."""
    parts = [row.get(f) for f in ENGAGEMENT_PARTS]
    return dict(row, engagements=None if any(p is None for p in parts) else sum(parts))


def compute_metrics(row: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Compute every metric in METRICS from a row's base fields.

    A missing operand or a zero denominator gives None, never 0. Engagement rate
    needs shares, saves and comments all present.
    """
    row = _with_engagements(row)
    result: Dict[str, Optional[float]] = {}
    for name, (num_fields, den_fields, scale) in METRICS.items():
        _, num = _pick(row, num_fields)
        _, den = _pick(row, den_fields)
        result[name] = None if num is None or den is None or den == 0 else num / den * scale
    return result


def metric_basis(row: Dict[str, Any], metric: str) -> Dict[str, Optional[str]]:
    """Say which fields fed a metric, e.g. whether ctr used link or all clicks."""
    num_fields, den_fields, _ = METRICS[resolve_metric(metric)]
    row = _with_engagements(row)
    num_field, num = _pick(row, num_fields)
    den_field, den = _pick(row, den_fields)
    return {
        "numerator": num_field if num is not None else None,
        "denominator": den_field if den is not None else None,
    }


def describe_missing(row: Dict[str, Any], metric: str) -> Optional[str]:
    """Why a metric is unavailable for a row, or None when it can be computed."""
    metric = resolve_metric(metric)
    num_fields, den_fields, _ = METRICS[metric]
    row = _with_engagements(row)
    if metric == "engagement_rate" and row["engagements"] is None:
        return "missing " + " and ".join(f for f in ENGAGEMENT_PARTS if row.get(f) is None)
    for fields in (num_fields, den_fields):
        if _pick(row, fields)[1] is None:
            return "missing " + " or ".join(fields)
    den_field, den = _pick(row, den_fields)
    if den == 0:
        return "zero " + den_field
    return None


def format_value(row: Dict[str, Any], metric: str, digits: int = 2) -> str:
    """Render a metric for a row or aggregated ad: a number or "n/a (reason)"."""
    metric = resolve_metric(metric)
    value = row[metric] if metric in row else compute_metrics(row)[metric]
    if value is None:
        return "n/a (%s)" % describe_missing(row, metric)
    return "%.*f" % (digits, value)


def _parse_date(value: Any) -> Optional[dt.date]:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _sum_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Sum each base field over rows; a field with no values stays None."""
    totals: Dict[str, Optional[float]] = {}
    for field in NUMERIC_FIELDS:
        values = [r[field] for r in rows if r.get(field) is not None]
        totals[field] = sum(values) if values else None
    return totals


def _delivered(row: Dict[str, Any]) -> bool:
    return (row.get("impressions") or 0) > 0


def _snake(key: Any) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return "adset_name" if name == "ad_set_name" else name


def _most_common_text(values: Iterable[Any], skip_numbers: bool = False) -> Optional[str]:
    counts: Dict[str, int] = {}
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        if skip_numbers and _num(text) is not None:
            continue
        counts[text] = counts.get(text, 0) + 1
    return max(counts, key=counts.__getitem__) if counts else None


def aggregate_by_ad(rows: Sequence[Dict[str, Any]],
                    key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Sum base fields per ad (by ad id, else ad name) and compute metrics.

    Adds first_date, last_date, active_days (days with delivery), age_days and
    age_basis. With a `created_time` on the rows (and no later than first
    delivery), age is the days from creation to the latest date in the data.
    Without one it is the days from first
    delivery in the window, so an ad older than the window looks as young as the
    window start, and age_basis says so. Reach is summed across rows, so with
    daily rows `frequency` is an average per-row frequency, not lifetime
    frequency; export a lifetime row for that. `video_views_3s_source` is
    "derived: ..." when any row's 3-second plays were derived from a cost per
    view, else "reported", else None.

    Name fields come from a column of that name when the data has one (market,
    ad type, ...), else from the ad name (see parse_name; `key_map` extends the
    KEY:value keys). Every other text column (objective, campaign name, placement,
    country, ...) is carried through under its snake_case heading, taking the
    most common value per ad, so any of them can be a --group-by column.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = row.get("ad_id") or row.get("ad_name")
        if key is None:
            raise ValueError("row has neither ad_id nor ad_name: %r" % (row,))
        groups.setdefault(key, []).append(row)

    all_dates = [d for d in (_parse_date(r.get("date")) for r in rows) if d]
    data_end = max(all_dates) if all_dates else None

    learned = learn_names([n for n in (next((r["ad_name"] for r in g if r.get("ad_name")), None)
                                       for g in groups.values()) if n], key_map)
    ads = []
    for group in groups.values():
        ad: Dict[str, Any] = {
            "ad_id": next((r["ad_id"] for r in group if r.get("ad_id")), None),
            "ad_name": next((r["ad_name"] for r in group if r.get("ad_name")), None),
        }
        ad.update(_sum_rows(group))
        delivered = [d for d in (_parse_date(r.get("date")) for r in group if _delivered(r)) if d]
        dated = delivered or [d for d in (_parse_date(r.get("date")) for r in group) if d]
        ad["first_date"] = min(dated).isoformat() if dated else None
        ad["last_date"] = max(dated).isoformat() if dated else None
        ad["active_days"] = len(set(delivered)) if delivered else None
        created = next((d for d in (_parse_date(r.get("created_time")) for r in group) if d), None)
        first = min(dated) if dated else None
        if created and first and created > first:
            created = None
        start = created or first
        ad["age_days"] = (data_end - start).days if start and data_end else None
        ad["age_basis"] = (AGE_FROM_CREATED if created else AGE_FROM_DELIVERY) if ad["age_days"] is not None else None
        sources = {r["video_views_3s_source"] for r in group if r.get("video_views_3s_source")}
        derived = sorted(x for x in sources if x.startswith("derived"))
        ad["video_views_3s_source"] = derived[0] if derived else ("reported" if sources else None)
        parsed = parse_name(ad["ad_name"], key_map=key_map, learned=learned) if ad["ad_name"] else {}
        ad["conversions_source"] = next((r["conversions_source"] for r in group
                                         if r.get("conversions_source")), None)
        columns: Dict[str, List[Any]] = {}
        for row in group:
            seen = set()
            for key, value in row.items():
                name = _snake(key)
                if name and name not in seen:
                    seen.add(name)
                    columns.setdefault(name, []).append(value)
        for field in NAME_FIELDS:
            carried = _most_common_text(columns.get(field, ()))
            ad[field] = carried or parsed.get(field)
        if ad.get("ad_type"):
            ad["ad_type"] = normalise_ad_type(ad["ad_type"])
        ad.update(compute_metrics(ad))
        for name, values in columns.items():
            if name in ad or name in _ROW_INTERNALS or name.startswith("reported_"):
                continue
            text = _most_common_text(values, skip_numbers=True)
            if text is not None:
                ad[name] = text
        ads.append(ad)
    return ads


# Row keys that are the loader's own bookkeeping, never carried as grouping columns.
_ROW_INTERNALS = frozenset(("date", "created_time", "level", "conversions_source", "video_views_3s_source",
                            _snake(COST_PER_VIEW)))

# Keys of an aggregated ad that are not columns to group by.
_NOT_GROUPABLE = frozenset(("ad_id", "ad_name", "first_date", "last_date", "age_basis", "video_views_3s_source",
                            "conversions_source", "created_time", "date", "spend_unit"))


def groupable_columns(ads: Sequence[Dict[str, Any]]) -> List[str]:
    """Columns of aggregated ads that hold text for at least one ad, sorted."""
    return sorted({k for a in ads for k, v in a.items()
                   if isinstance(v, str) and v and k not in _NOT_GROUPABLE})


def resolve_group_by(ads: Sequence[Dict[str, Any]], group_by: Sequence[str]) -> Tuple[str, ...]:
    """Canonical column names for a --group-by list; GroupColumnError when one is absent.

    A column is absent when no ad carries a value for it. `format` (the default
    grouping) is always accepted: where names do not parse it reads as "unknown".
    """
    available = groupable_columns(ads)
    resolved = []
    for column in group_by:
        name = _snake(column)
        if name != "format" and name not in available:
            raise GroupColumnError("column %s not in the data; available: %s"
                                   % (column, ", ".join(available) or "none"))
        resolved.append(name)
    return tuple(resolved)


def _stats(values: Sequence[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"n": 0, "median": None, "p25": None, "p75": None}
    if len(values) == 1:
        return {"n": 1, "median": values[0], "p25": values[0], "p75": values[0]}
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"n": len(values), "median": statistics.median(values), "p25": q1, "p75": q3}


def baseline(ads: Sequence[Dict[str, Any]], metric: str,
             group_by: Sequence[str] = ("format",), min_impressions: int = 1000) -> Dict[str, Any]:
    """The account's own median and quartiles for a metric, per group.

    Only ads with at least `min_impressions` and a value for the metric count.
    A group with fewer than 5 ads falls back to the account-wide numbers, and
    its `basis` field says so; `n_group` is the real group size.
    """
    metric = resolve_metric(metric)
    eligible = [a for a in ads if a.get(metric) is not None and (a.get("impressions") or 0) >= min_impressions]
    account = _stats([a[metric] for a in eligible])
    buckets: Dict[str, List[float]] = {}
    for ad in eligible:
        key = " / ".join(str(ad.get(g) or "unknown") for g in group_by)
        buckets.setdefault(key, []).append(ad[metric])
    groups = {}
    for key, values in buckets.items():
        if len(values) >= 5:
            groups[key] = dict(_stats(values), n_group=len(values), basis="group")
        else:
            groups[key] = dict(account, n_group=len(values),
                               basis="account-wide (group n=%d < 5)" % len(values))
    return {
        "metric": metric,
        "group_by": list(group_by),
        "min_impressions": min_impressions,
        "account": dict(account, basis="account-wide"),
        "groups": groups,
    }


def _pct_change(first: Optional[float], last: Optional[float]) -> Optional[float]:
    if first is None or last is None or first == 0:
        return None
    return (last - first) / abs(first) * 100


def fatigue_trend(rows: Sequence[Dict[str, Any]], ad_key: str, metric: str = "ctr",
                  window: int = 6) -> Dict[str, Any]:
    """Compare an ad's first `window` delivery days with its last `window`.

    The default window of 6 days is arbitrary: set it from your own account's
    typical time to stabilise, not from this default.

    `ad_key` is the ad id or ad name. Returns the metric in each window, its
    percent change, and the change in frequency (average per-row frequency, see
    aggregate_by_ad). With fewer than 2 * window delivery days it returns
    {"status": "insufficient_data"}.
    """
    metric = resolve_metric(metric)
    by_day: Dict[dt.date, List[Dict[str, Any]]] = {}
    for row in rows:
        if str(ad_key) not in (str(row.get("ad_id")), str(row.get("ad_name"))):
            continue
        day = _parse_date(row.get("date"))
        if day and _delivered(row):
            by_day.setdefault(day, []).append(row)
    days = sorted(by_day)
    if len(days) < 2 * window:
        return {"status": "insufficient_data", "ad": ad_key,
                "delivery_days": len(days), "needed": 2 * window}

    def window_stats(chosen: Sequence[dt.date]) -> Dict[str, Any]:
        total = _sum_rows([r for d in chosen for r in by_day[d]])
        values = compute_metrics(total)
        return {"start": chosen[0].isoformat(), "end": chosen[-1].isoformat(),
                "value": values[metric], "frequency": values["frequency"]}

    first, last = window_stats(days[:window]), window_stats(days[-window:])
    return {
        "status": "ok", "ad": ad_key, "metric": metric, "window": window,
        "first": first, "last": last,
        "pct_change": _pct_change(first["value"], last["value"]),
        "frequency_pct_change": _pct_change(first["frequency"], last["frequency"]),
    }


def normalise_ad_type(value: Any) -> str:
    """Map an ad-type word to one of AD_TYPES through SYNONYMS; an unknown word is kept, lowercased."""
    text = str(value).strip().lower()
    return SYNONYMS.get(text, text)


def parse_key_map(text: str) -> Dict[str, str]:
    """Read "PX=concept,KND=ad_type" into {"PX": "concept", "KND": "ad_type"}."""
    result: Dict[str, str] = {}
    for pair in (text or "").split(","):
        if not pair.strip():
            continue
        key, sep, field = pair.partition("=")
        if not sep or not key.strip() or not field.strip():
            raise ValueError("bad --key-map entry %r: write KEY=field, for example PX=concept" % pair)
        result[key.strip()] = field.strip()
    return result


_KEYED = re.compile(r"^([A-Za-z]{2,10})\s*[:=]\s*(.+)$")
_ISO_DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_DAY_FIRST = re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$")
_READ_FIELDS = ("format", "concept", "ad_type")
_NUMBERISH = re.compile(r"^[A-Za-z]?\d+$")
# Keys that usually name a person; their values are never guessed to be the concept.
_PERSON_KEYS = frozenset(("WHO", "PERSON", "NAME"))


def _person_like(key: str, taken: Sequence[str]) -> bool:
    """A key that looks like a creator or person field, or whose values include format or ad-type words."""
    return key in _PERSON_KEYS or any(v.lower() in FORMAT_WORDS or v.lower() in SYNONYMS for v in taken)


def _name_date(text: str, order: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Read a date in a name: (ISO date or None, status).

    Status is "ok", "ambiguous" (day and month could swap and `order` - "dmy" or
    "mdy" - is not known), "invalid" (looks like a date but is not one) or "no"
    (not date-shaped). Year-first dates are never ambiguous.
    """
    text = text.strip()
    try:
        iso = _ISO_DATE.match(text)
        if iso:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).isoformat(), "ok"
        dmy = _DAY_FIRST.match(text)
        if not dmy:
            return None, "no"
        first, second, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        if first > 12 and second > 12:
            return None, "invalid"
        if first > 12:
            day, month = first, second
        elif second > 12:
            day, month = second, first
        elif first == second or order:
            day, month = (second, first) if order == "mdy" else (first, second)
        else:
            return None, "ambiguous"
        return dt.date(year, month, day).isoformat(), "ok"
    except ValueError:
        return None, "invalid"


def _merged_key_map(key_map: Optional[Dict[str, str]],
                    learned: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Built-in keys, then keys read from values, then the user's own map (which wins)."""
    merged = dict(KEY_MAP)
    merged.update((learned or {}).get("key_map", {}))
    merged.update({str(k).strip().upper(): str(v).strip() for k, v in (key_map or {}).items()})
    return merged


def _split(name: str, separator: str) -> List[str]:
    return [p.strip() for p in name.split(separator)]


def _pick_separator(name: str) -> Optional[str]:
    """The separator a single name uses: the one that yields the most KEY:value segments, else the first present."""
    best, best_score = None, -1
    for separator in SEPARATORS:
        if separator in name:
            score = sum(1 for part in _split(name, separator) if _KEYED.match(part))
            if score > best_score:
                best, best_score = separator, score
    return best


def learn_names(names: Sequence[str], key_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Read what a whole set of names says about itself, so a single name can be read correctly.

    Returns `key_map` (KEY -> field for keys that are not built in, read from the
    values the key takes: a field is chosen when most of a key's values are
    format words, ad-type words, market codes or dates), `inferred` (the field,
    the computed share of values and the evidence, for each such key),
    `market_positions` (positions where most names carry a market code: a bare
    code elsewhere is not read as a market) and `date_order` ("dmy" or "mdy"
    when some date in the names settles day-versus-month order, else None).
    When nothing is read as the concept, the one unmapped key with free-text
    values (more than one distinct value, none of the kinds above) is read as the
    concept; with two or more such keys none is, and `concept_candidates` lists
    them so the agent asks one question. A key only counts when more than half of
    all names carry it, counted over the names as given (its `coverage` is
    reported), a key whose values are mostly numbers (3, v2) is never a concept
    candidate, and a key that looks like a person field (WHO, PERSON, NAME) or
    whose values include format or ad-type words is never assigned the concept:
    it stays in `concept_candidates` for the one question.
    Nothing is stored. `key_map` entries override the reading.
    """
    names = [str(n).strip() for n in names if n is not None and str(n).strip()]
    known = _merged_key_map(key_map)
    values: Dict[str, List[str]] = {}
    hits: Dict[str, int] = {}
    positions: Dict[int, int] = {}
    seen_orders = set()
    concept_keyed = False
    counted = 0
    for name in names:
        separator = _pick_separator(name)
        if separator is None:
            continue
        counted += 1
        in_name = set()
        for position, part in enumerate(_split(name, separator), start=1):
            match = _KEYED.match(part)
            value = match.group(2).strip() if match else part
            if match and match.group(1).upper() not in known:
                key = match.group(1).upper()
                values.setdefault(key, []).append(value)
                if key not in in_name:
                    in_name.add(key)
                    hits[key] = hits.get(key, 0) + 1
            elif match and known[match.group(1).upper()] == "concept":
                concept_keyed = True
            elif not match and part.upper() in MARKET_CODES:
                positions[position] = positions.get(position, 0) + 1
            dmy = _DAY_FIRST.match(value)
            if dmy and int(dmy.group(1)) > 12 >= int(dmy.group(2)):
                seen_orders.add("dmy")
            elif dmy and int(dmy.group(2)) > 12 >= int(dmy.group(1)):
                seen_orders.add("mdy")
    order = next(iter(seen_orders)) if len(seen_orders) == 1 else None
    checks = (
        ("format", "format words", lambda v: v.lower() in FORMAT_WORDS),
        ("ad_type", "ad-type words", lambda v: v.lower() in SYNONYMS),
        ("market", "market codes", lambda v: v.upper() in MARKET_CODES),
        ("launch_date", "dates", lambda v: _name_date(v, order)[1] in ("ok", "ambiguous")),
    )
    inferred: Dict[str, Dict[str, Any]] = {}
    # A key counts only when more than half of all names carry it.
    common = {k for k, n in hits.items() if n * 2 > len(names)}
    coverage = {k: n / len(names) * 100 for k, n in hits.items()}
    for key, taken in values.items():
        if key not in common:
            continue
        best = max(((sum(1 for v in taken if test(v)) / len(taken), -i, field, basis)
                    for i, (field, basis, test) in enumerate(checks)))
        if best[0] > 0.5:
            inferred[key] = {"field": best[2], "share": best[0] * 100, "basis": best[3], "count": len(taken),
                             "coverage": coverage[key]}
    candidates: List[str] = []
    if not concept_keyed and not any(v["field"] == "concept" for v in inferred.values()):
        candidates = sorted(
            k for k, taken in values.items()
            if k in common and k not in inferred and len(set(taken)) > 1
            and sum(1 for v in taken if _NUMBERISH.match(v)) * 2 <= len(taken))
        if len(candidates) == 1 and not _person_like(candidates[0], values[candidates[0]]):
            key = candidates[0]
            inferred[key] = {"field": "concept", "share": None, "basis": "the only free-text key",
                             "count": len(values[key]), "coverage": coverage[key]}
            candidates = []
    return {
        "key_map": {k: v["field"] for k, v in inferred.items()}, "inferred": inferred,
        "concept_candidates": candidates,
        "market_positions": {p for p, c in positions.items() if c * 2 > counted} if counted else None,
        "date_order": order,
    }


def _shape_field(part: str, position: int, learned: Dict[str, Any]) -> Optional[str]:
    if _name_date(part, learned.get("date_order"))[1] != "no":
        return "launch_date"
    allowed = learned.get("market_positions")
    if part.upper() in MARKET_CODES:
        # An upper-case code is read anywhere unless markets are known to sit elsewhere; a lower-case
        # one (it, no, me are also words) only where most names carry a market.
        if part == part.upper():
            if allowed is None or position in allowed:
                return "market"
        elif allowed is not None and position in allowed:
            return "market"
    if part.lower() in FORMAT_WORDS:
        return "format"
    return None


def _read_name(ad_name: Optional[str], pattern: Optional[Sequence[str]] = None,
               key_map: Optional[Dict[str, str]] = None,
               learned: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Read one name: fields, the separator, the style, the keys used and any dates it could not read.

    None when the name has no separator. style is "keyed" (KEY:value segments),
    "positional" (an exact-length name or an explicit pattern) or "shape"
    (unkeyed segments recognised by what they look like). A name is keyed only
    when at least half its parts are KEY:value or one key is in the key map.
    """
    if not ad_name or not str(ad_name).strip():
        return None
    learned = learned or {}
    name = str(ad_name).strip()
    keys = _merged_key_map(key_map, learned)
    separator = _pick_separator(name)
    if separator is None:
        return None
    parts = _split(name, separator)
    result: Dict[str, Any] = {"separator": separator, "fields": {}, "keys": [], "leftover": [], "bad_dates": []}
    fields = result["fields"]

    def assign(field: str, value: str, position: int) -> None:
        original = value
        if field == "launch_date":
            iso, status = _name_date(value, learned.get("date_order"))
            if iso is None:
                result["bad_dates"].append((value, status))
                field = None
            else:
                value = iso
        elif field in ("format", "tone"):
            value = value.lower()
        elif field == "market" and value.upper() in MARKET_CODES:
            value = value.upper()
        elif field == "ad_type":
            value = normalise_ad_type(value)
        if field is None or field in fields:
            fields["segment_%d" % position] = original
            result["leftover"].append((position, original))
        else:
            fields[field] = value

    if pattern:
        if len(parts) != len(pattern):
            return None
        result["style"] = "positional"
        for position, (field, part) in enumerate(zip(pattern, parts), start=1):
            assign(field, part, position)
        return result
    matches = [_KEYED.match(p) for p in parts]
    keyed = sum(1 for m in matches if m)
    is_keyed = any(m and m.group(1).upper() in keys for m in matches) or (keyed > 0 and keyed * 2 >= len(parts))
    if not is_keyed and len(parts) == len(LEGACY_PATTERN):
        result["style"] = "positional"
        for position, (field, part) in enumerate(zip(LEGACY_PATTERN, parts), start=1):
            assign(field, part, position)
        return result
    result["style"] = "keyed" if is_keyed else "shape"
    for position, (part, match) in enumerate(zip(parts, matches), start=1):
        if not part:
            continue
        if match and is_keyed:
            key = match.group(1).upper()
            field = keys.get(key, key.lower())
            result["keys"].append((key, field, key in keys))
            assign(field, match.group(2).strip(), position)
        else:
            assign(_shape_field(part, position, learned), part, position)
    return result


def _is_read(fields: Dict[str, Any]) -> bool:
    """The one rule for a name that counts as read: it yields a format, concept or ad type."""
    return any(fields.get(f) for f in _READ_FIELDS)


def parse_name(ad_name: Optional[str], pattern: Optional[Sequence[str]] = None,
               key_map: Optional[Dict[str, str]] = None,
               learned: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Split an ad name into naming-convention fields; {} unless it yields a format, concept or ad type.

    Names split on " | ", "|", " _ ", "_" or " - " (whichever the name uses).
    Segments written KEY:value or KEY=value (KEY is 2-10 letters) are read through
    KEY_MAP, which `key_map` extends or overrides, case-insensitively; a name is
    keyed only when at least half its parts are KEY:value or one key is mapped.
    An unmapped key takes the field its values suggest when `learned` (from
    learn_names, over all the names) is given, else keeps its lowercase name.
    Other segments are read by shape: a date, a market code (US, UK, ... and,
    when `learned` says where markets sit, only in that position) or a format
    word; anything else is kept as segment_<position>. A date is labelled
    launch_date only when it parses; day-versus-month order must be known or
    obvious. A name with no key and exactly the original seven parts
    (LEGACY_PATTERN) reads positionally, as does any name when `pattern` (an
    ordered field list) is given, which then needs an exact part count. An
    ad_type goes through SYNONYMS; a type that is not known is kept as written.
    """
    read = _read_name(ad_name, pattern, key_map, learned)
    if read is None or (not pattern and not _is_read(read["fields"])):
        return {}
    return dict(read["fields"])


def _choose_separator(names: Sequence[str]) -> Optional[str]:
    """The separator that splits the most names into the same number of parts."""
    best, best_score = None, 0
    for separator in SEPARATORS:
        counts: Dict[int, int] = {}
        for name in names:
            if separator in name:
                size = len(_split(name, separator))
                counts[size] = counts.get(size, 0) + 1
        if counts and max(counts, key=counts.__getitem__) >= 2:
            score = max(counts.values())
            if score > best_score:
                best, best_score = separator, score
    return best


_STYLE_WORDS = {"keyed": "KEY:value segments", "positional": "fixed positions",
                "shape": "unlabelled segments recognised by what they look like"}


def detect_convention(names: Sequence[str], key_map: Optional[Dict[str, str]] = None,
                      min_match_rate: float = MATCH_RATE_ASK,
                      coexist_share: float = COEXIST_SHARE) -> Dict[str, Any]:
    """Test how a set of ad names is structured, against ALL of them. Pure: nothing is stored.

    A name is matched when at least a format, a concept or an ad type is read
    from it (the same rule parse_name applies). Returns the dominant separator,
    each field's coverage (percent of all names), the KEY:value keys seen, the
    fields inferred for unlisted keys from their values (`inferred_keys`, with the
    computed share), the conventions in use with counts, the overall `match_rate`,
    the first UNPARSED_SHOWN names (a display cap, arbitrary) that did not match,
    dates that were ambiguous or unparseable (`date_issues`), and a plain-English
    `description`. `ask` is True, with `ask_reasons`, only when the match rate is
    under `min_match_rate` or a second convention covers at least `coexist_share`
    percent of names; a few stray names are listed, not asked about. Both
    thresholds are arbitrary defaults: set them from your account.
    """
    names = [str(n).strip() for n in names if n is not None and str(n).strip()]
    total = len(names)
    learned = learn_names(names, key_map)
    result: Dict[str, Any] = {
        "names": total, "separator": _choose_separator(names), "match_rate": None, "matched": 0,
        "fields": {}, "keys": {}, "unknown_keys": {}, "inferred_keys": learned["inferred"],
        "concept_candidates": learned["concept_candidates"],
        "conventions": [], "coexisting": False, "unlabelled": [], "unparsed": [], "unparsed_count": 0,
        "ad_types": {}, "unknown_ad_types": {},
        "date_issues": {"order": learned["date_order"], "ambiguous": [], "unparseable": [],
                        "ambiguous_count": 0, "unparseable_count": 0},
        "ask": True, "ask_reasons": [], "min_match_rate": min_match_rate, "coexist_share": coexist_share,
    }
    if not total:
        result["ask_reasons"] = ["no ad names to test"]
        result["description"] = "There are no ad names to read, so no naming convention can be tested."
        return result

    field_counts: Dict[str, int] = {}
    field_sources: Dict[str, set] = {}
    conventions: Dict[Tuple[str, str], int] = {}
    unparsed: List[str] = []
    unlabelled: Dict[int, List[str]] = {}
    issues = result["date_issues"]
    for name in names:
        read = _read_name(name, None, key_map, learned)
        if read:
            for value, status in read["bad_dates"]:
                bucket = issues["ambiguous" if status == "ambiguous" else "unparseable"]
                if value not in bucket:
                    bucket.append(value)
        fields = {f: v for f, v in read["fields"].items() if not f.startswith("segment_")} if read else {}
        if not read or not _is_read(fields):
            unparsed.append(name)
            continue
        result["matched"] += 1
        signature = (read["separator"], read["style"])
        conventions[signature] = conventions.get(signature, 0) + 1
        keyed_fields = {field for _, field, _ in read["keys"]}
        for field in fields:
            field_counts[field] = field_counts.get(field, 0) + 1
            field_sources.setdefault(field, set()).add("keyed" if field in keyed_fields else "by position or shape")
        for key, field, known in read["keys"]:
            entry = result["keys"].setdefault(key, {"field": field, "count": 0})
            entry["count"] += 1
            if not known:
                result["unknown_keys"][key] = result["unknown_keys"].get(key, 0) + 1
        for position, value in read["leftover"]:
            unlabelled.setdefault(position, []).append(value)
        kind = fields.get("ad_type")
        if kind:
            bucket = "ad_types" if kind in AD_TYPES else "unknown_ad_types"
            result[bucket][kind] = result[bucket].get(kind, 0) + 1
    issues["ambiguous_count"], issues["unparseable_count"] = len(issues["ambiguous"]), len(issues["unparseable"])
    issues["ambiguous"] = issues["ambiguous"][:UNPARSED_SHOWN]
    issues["unparseable"] = issues["unparseable"][:UNPARSED_SHOWN]

    result["match_rate"] = result["matched"] / total * 100
    result["fields"] = {f: {"count": c, "coverage": c / total * 100, "source": " and ".join(sorted(field_sources[f]))}
                        for f, c in sorted(field_counts.items(), key=lambda kv: -kv[1])}
    result["conventions"] = [{"separator": sep, "style": style, "count": c, "share": c / total * 100}
                             for (sep, style), c in sorted(conventions.items(), key=lambda kv: -kv[1])]
    result["coexisting"] = len(conventions) > 1
    result["unlabelled"] = [{"position": p, "count": len(v), "examples": sorted(set(v))[:3]}
                            for p, v in sorted(unlabelled.items())]
    result["unparsed"] = unparsed[:UNPARSED_SHOWN]
    result["unparsed_count"] = len(unparsed)

    reasons = []
    if result["match_rate"] < min_match_rate:
        reasons.append("only %.0f%% of names could be read (under %g%%)" % (result["match_rate"], min_match_rate))
    for convention in result["conventions"][1:]:
        if convention["share"] >= coexist_share:
            reasons.append("two conventions coexist: %s" % "; ".join(
                "%d names use %s with %s" % (c["count"], _sep_label(c["separator"]), _STYLE_WORDS[c["style"]])
                for c in result["conventions"]))
            break
    result["ask_reasons"] = reasons
    result["ask"] = bool(reasons)
    result["description"] = _describe(result)
    return result


def _sep_label(separator: Optional[str]) -> str:
    return "no separator" if separator is None else "'%s'" % separator


def _describe(found: Dict[str, Any]) -> str:
    total, matched = found["names"], found["matched"]
    parts = ["%d of %d ad names (%.0f%%) could be read" % (matched, total, found["match_rate"])]
    if found["conventions"]:
        parts[0] += ": " + "; ".join(
            "%d use %s with %s" % (c["count"], _sep_label(c["separator"]), _STYLE_WORDS[c["style"]])
            for c in found["conventions"])
    text = parts[0] + "."
    if found["fields"]:
        shown = ", ".join("%s (%.0f%%)" % (f, v["coverage"]) for f, v in list(found["fields"].items())[:8])
        text += " Fields found, with the share of all names carrying each: %s." % shown
    if found["unparsed_count"]:
        text += " %d names could not be read and are listed below, not guessed." % found["unparsed_count"]
    for key, info in sorted(found["inferred_keys"].items()):
        text += (" Key %s was read as %s because %.0f%% of its values are %s (key in %.0f%% of names)." % (
            key, info["field"], info["share"], info["basis"], info["coverage"]) if info["share"] is not None else
            " Key %s was read as %s: %s (key in %.0f%% of names)." % (
                key, info["field"], info["basis"], info["coverage"]))
    if found["concept_candidates"]:
        text += " No key was read as the concept; any of %s could be it, so ask the user which." % ", ".join(
            found["concept_candidates"])
    issues = found["date_issues"]
    if issues["ambiguous_count"] or issues["unparseable_count"]:
        text += " Dates left unlabelled: %d ambiguous (day and month could swap), %d unparseable." % (
            issues["ambiguous_count"], issues["unparseable_count"])
    if found["unknown_ad_types"]:
        text += " Ad types not in the six known types: %s." % ", ".join(
            "%s (%d)" % kv for kv in sorted(found["unknown_ad_types"].items()))
    return text


BAND_TOP, BAND_MID, BAND_BOTTOM = "top quartile", "middle", "bottom quartile"
HIGHER_IS_BETTER = ("hook_rate", "hold_rate", "video_completion_rate", "ctr", "cvr",
                    "add_to_cart_rate", "roas", "engagement_rate")
LOWER_IS_BETTER = ("cpm", "cpc", "cpa", "cost_per_add_to_cart", "cost_per_lead")
# Fewer comparable ads than this is not enough to grade against. An arbitrary
# default, not a statistical rule: set your own from how many ads you run per format.
MIN_GROUP = 5


def percentile_rank(value: Optional[float], values: Sequence[float]) -> Optional[float]:
    """Where `value` sits among `values`, 0-100 (ties count half).

    None when the value is missing or fewer than 5 values are given.
    """
    if value is None or len(values) < MIN_GROUP:
        return None
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / len(values) * 100


def group_key(ad: Dict[str, Any], group_by: Sequence[str]) -> str:
    return " / ".join(str(ad.get(g) or "unknown") for g in group_by)


def grade_against(ad: Dict[str, Any], ads: Sequence[Dict[str, Any]], metric: str,
                  group_by: Sequence[str] = ("format",), min_impressions: int = 1000) -> Dict[str, Any]:
    """Grade one ad's metric against the account's own distribution.

    Returns value, group, basis, percentile and band. The comparison set is the
    ad's own group (for example its format); a group with fewer than 5 ads falls
    back to the whole account, and `basis` says so. Higher-is-better metrics
    band top quartile at or above p75 and bottom quartile at or below p25;
    lower-is-better metrics (costs) are inverted. The band reads "not graded
    (<reason>)" for a missing value, low volume or too little comparison data,
    and "not banded" for frequency. The 1000-impression volume floor is an
    arbitrary default: set it from your own spend per ad.
    """
    metric = resolve_metric(metric)
    group = group_key(ad, group_by)
    result: Dict[str, Any] = {"metric": metric, "value": ad.get(metric), "group": group,
                              "basis": None, "percentile": None, "band": None}

    def not_graded(reason: str) -> Dict[str, Any]:
        result["band"] = "not graded (%s)" % reason
        return result

    if metric == "frequency":
        result["band"] = "not banded"
        return result
    if result["value"] is None:
        return not_graded(describe_missing(ad, metric) or "no value")
    if metric in LOWER_IS_BETTER and "spend" in ad and not ad["spend"]:
        return not_graded("missing spend")
    if (ad.get("impressions") or 0) < min_impressions:
        return not_graded("low volume")
    base = baseline(ads, metric, group_by=group_by, min_impressions=min_impressions)
    stats = base["groups"].get(group, base["account"])
    result["basis"] = stats["basis"]
    eligible = [a for a in ads if a.get(metric) is not None
                and (a.get("impressions") or 0) >= min_impressions]
    if stats["basis"] == "group":
        pool = [a[metric] for a in eligible if group_key(a, group_by) == group]
    else:
        pool = [a[metric] for a in eligible]
    result["n_comparable"] = len(pool)
    if len(pool) < MIN_GROUP:
        return not_graded("too little comparison data: %d comparable ads, need %d" % (len(pool), MIN_GROUP))
    result["percentile"] = percentile_rank(result["value"], pool)
    result["p25"], result["median"], result["p75"] = stats["p25"], stats["median"], stats["p75"]
    if stats["p25"] == stats["p75"]:
        return not_graded("no spread in group")
    high = result["value"] >= stats["p75"]
    low = result["value"] <= stats["p25"]
    if metric in LOWER_IS_BETTER:
        high, low = low, high
    result["band"] = BAND_TOP if high else BAND_BOTTOM if low else BAND_MID
    return result


def _comparable(ad: Dict[str, Any], ads: Sequence[Dict[str, Any]], metric: str,
                group_by: Sequence[str], min_impressions: int) -> int:
    key = group_key(ad, group_by)
    return sum(1 for a in ads if a.get(metric) is not None and (a.get("impressions") or 0) >= min_impressions
               and group_key(a, group_by) == key)


def grade_with_fallback(ad: Dict[str, Any], ads: Sequence[Dict[str, Any]], metric: str,
                        group_by: Sequence[str] = ("format",), min_impressions: int = 1000) -> Dict[str, Any]:
    """Grade against the narrowest group with at least MIN_GROUP comparable ads.

    Tries every prefix of `group_by` from the whole list down to its first
    column, then the whole of `ads`. The result is grade_against's, plus
    `group_by` (the columns actually used, empty for account-wide), `group_value`
    (the ad's group, e.g. "static / promo"), `group_size`
    (comparable ads in that group, None when nothing could be graded) and
    `fallback` (one line per narrower grouping that was too small, or None).
    A grouping is too small when it has fewer than MIN_GROUP comparable ads.
    """
    metric = resolve_metric(metric)
    levels = [tuple(group_by[:k]) for k in range(len(group_by), 0, -1)] + [()]
    skipped: List[str] = []
    grade: Dict[str, Any] = {}
    for level in levels:
        grade = grade_against(ad, ads, metric, level, min_impressions)
        if grade["basis"] is None:
            break
        if grade["basis"] == "group":
            break
        skipped.append("%s has %d comparable ads, under %d" % (
            " / ".join(level) or "account-wide", _comparable(ad, ads, metric, level, min_impressions), MIN_GROUP))
    grade["group_by"] = list(level)
    grade["group_value"] = group_key(ad, level) if level else "account-wide"
    grade["group_size"] = grade.get("n_comparable")
    grade["fallback"] = "; ".join(skipped) or None
    return grade


def is_thin(group_size: Optional[int]) -> bool:
    """A group big enough to grade but too small to act on alone: under twice MIN_GROUP."""
    return group_size is not None and group_size < 2 * MIN_GROUP


OBJECTIVES = {
    "sales": ("sales", "conversions", "productcatalogsales"),
    "traffic": ("traffic", "linkclicks"),
    "awareness": ("awareness", "reach", "brandawareness", "videoviews"),
    "leads": ("leads", "leadgeneration"),
    "engagement": ("engagement", "postengagement"),
}
# objective -> (payback metrics, plain name of what they measure)
PAYBACK = {
    "sales": (("cpa", "roas"), "cost per sale and return on ad spend"),
    "traffic": (("cpc", "ctr"), "cost per click and click-through rate"),
    "awareness": (("cpm", "hook_rate"), "cost per 1,000 impressions and hook rate"),
    "leads": (("cost_per_lead",), "cost per lead"),
    "engagement": (("engagement_rate", "cpm"), "engagement rate and cost per 1,000 impressions"),
}


def objective_class(value: Any) -> Optional[str]:
    """sales, traffic, awareness, leads or engagement for a Meta campaign objective; None when unknown or absent.

    Reads Meta's current (OUTCOME_SALES) and legacy (CONVERSIONS, LINK_CLICKS, ...) names,
    ignoring case and punctuation.
    """
    if not isinstance(value, str):
        return None
    text = re.sub(r"[^a-z]", "", value.lower())
    for name, words in OBJECTIVES.items():
        if text in words or text.replace("outcome", "", 1) in words:
            return name
    return None


def payback_metrics(objective: Any) -> Dict[str, Any]:
    """The metrics that decide payback for a campaign objective.

    An unknown or absent objective is treated as sales and `assumed` says so,
    with a `note` to print.
    """
    known = objective_class(objective)
    name = known or "sales"
    metrics, what = PAYBACK[name]
    note = None
    if known is None:
        note = ("objective %s: judged as sales" % ("%r is not one of the known objectives" % objective
                                                   if objective else "not in the data"))
    return {"objective": name, "metrics": metrics, "what": what, "assumed": known is None, "note": note}


def detect_currency(path: Any) -> Optional[str]:
    """The currency code in an export's spend header, e.g. "Amount spent (USD)"; None when it is not stated."""
    if not path or str(path).lower().endswith(".json"):
        return None
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            header = handle.readline()
    except OSError:
        return None
    found = re.search(r"amount spent\s*\(([A-Za-z]{3})\)", header, re.I)
    return found.group(1).upper() if found else None


DEFAULT_GROUP_BY = ("format", "ad_type")


def default_group_by(ads: Sequence[Dict[str, Any]], group_by: Optional[Sequence[str]] = None) -> Tuple[Tuple[str, ...], Optional[str]]:
    """Resolve --group-by, returning (columns, note).

    With no list given the default is format then ad type; a default column the
    data does not carry drops out and `note` says so. A column the user named
    that is absent still raises GroupColumnError.
    """
    if group_by:
        return resolve_group_by(ads, group_by), None
    available = groupable_columns(ads)
    kept = tuple(c for c in DEFAULT_GROUP_BY if c == "format" or c in available)
    dropped = [c for c in DEFAULT_GROUP_BY if c not in kept]
    note = ("%s not in the data, so grouped by %s only" % (", ".join(dropped), ", ".join(kept))) if dropped else None
    return kept, note


def data_window(rows: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """First and last date (ISO) found in the rows, or (None, None)."""
    days = [d for d in (_parse_date(r.get("date")) for r in rows) if d]
    return (min(days).isoformat(), max(days).isoformat()) if days else (None, None)


def window_aggregate(rows: Sequence[Dict[str, Any]], window: int = 6,
                     which: str = "first",
                     key_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Aggregate each ad over its first or last `window` delivery days.

    `which` is "first" or "last". An ad with fewer than `window` delivery days
    is left out, so it is never graded on a window it does not have. The default
    window of 6 days is arbitrary: set it from your own account.
    """
    if which not in ("first", "last"):
        raise ValueError("which must be 'first' or 'last'")
    by_ad: Dict[str, Dict[dt.date, List[Dict[str, Any]]]] = {}
    for row in rows:
        key = row.get("ad_id") or row.get("ad_name")
        day = _parse_date(row.get("date"))
        if key is None or day is None or not _delivered(row):
            continue
        by_ad.setdefault(key, {}).setdefault(day, []).append(row)
    chosen: List[Dict[str, Any]] = []
    for days in by_ad.values():
        ordered = sorted(days)
        if len(ordered) < window:
            continue
        keep = ordered[:window] if which == "first" else ordered[-window:]
        chosen.extend(r for d in keep for r in days[d])
    return aggregate_by_ad(chosen, key_map=key_map) if chosen else []


def spend_share(ads: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ads sorted by spend, each with its share and the running cumulative share (%)."""
    spent = [a for a in ads if a.get("spend")]
    total = sum(a["spend"] for a in spent)
    if not total:
        return []
    out, running = [], 0.0
    for ad in sorted(spent, key=lambda a: a["spend"], reverse=True):
        running += ad["spend"]
        out.append({"ad": ad.get("ad_id") or ad.get("ad_name"), "spend": ad["spend"],
                    "share": ad["spend"] / total * 100, "cumulative": running / total * 100})
    return out


def concentration(ads: Sequence[Dict[str, Any]], top_n: int = 3) -> Optional[float]:
    """Share of spend (%) held by the top `top_n` ads; None when there is no spend.

    top_n=3 is an arbitrary default: set your own from how many ads you run.
    """
    shares = spend_share(ads)
    return shares[min(top_n, len(shares)) - 1]["cumulative"] if shares else None


def _cell(value: Optional[float], digits: int = 2) -> str:
    return "n/a" if value is None else "%.*f" % (digits, value)


def _signed(value: Optional[float]) -> str:
    return "n/a" if value is None else "%+.0f%%" % value


def _ad_flags(ad: Dict[str, Any], low_ctr: Optional[float]) -> List[str]:
    flags = []
    if ad["age_days"] is not None and ad["age_days"] < 5:
        flags.append("young(%dd)" % ad["age_days"])
    if ad["video_views_3s"] is not None and ad["video_thruplay"] is None:
        flags.append("no-thruplay")
    if low_ctr is not None and ad["ctr"] is not None and ad["ctr"] < low_ctr:
        flags.append("ctr<p25")
    return flags


def build_report(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-ad rows for the CLI: metrics, ctr trend and flags (relative to the account)."""
    ads = aggregate_by_ad(rows)
    ctr_base = baseline(ads, "ctr", group_by=("format",))
    report = []
    for ad in ads:
        stats = ctr_base["groups"].get(str(ad.get("format") or "unknown"))
        low = stats["p25"] if stats else ctr_base["account"]["p25"]
        trend = fatigue_trend(rows, ad["ad_id"] or ad["ad_name"], "ctr")
        entry = dict(ad)
        entry["ctr_trend_pct"] = trend.get("pct_change")
        entry["frequency_trend_pct"] = trend.get("frequency_pct_change")
        entry["trend_status"] = trend["status"]
        entry["flags"] = _ad_flags(ad, low)
        report.append(entry)
    return report


def _video_notes(report: Sequence[Dict[str, Any]]) -> List[str]:
    notes = []
    for ad in report:
        if ad["video_views_3s"] is None:
            continue
        for metric in ("hold_rate", "video_completion_rate"):
            if ad[metric] is None:
                notes.append("%s  %s: %s" % (ad["ad_id"] or ad["ad_name"], metric,
                                             format_value(ad, metric)))
    return notes


def render_table(report: Sequence[Dict[str, Any]]) -> str:
    header = ["ad", "format", "type", "age", "days", "spend", "impr", "hook%", "hold%",
              "ctr%", "ctr trend", "freq trend", "cpm", "cpa", "roas", "flags"]
    lines = []
    for ad in report:
        lines.append([
            str(ad["ad_id"] or ad["ad_name"]), str(ad.get("format") or "-"),
            str(ad.get("ad_type") or "-"),
            "n/a" if ad["age_days"] is None else str(ad["age_days"]),
            "n/a" if ad["active_days"] is None else str(ad["active_days"]),
            _cell(ad["spend"], 0), _cell(ad["impressions"], 0), _cell(ad["hook_rate"], 1),
            _cell(ad["hold_rate"], 1), _cell(ad["ctr"], 2), _signed(ad["ctr_trend_pct"]),
            _signed(ad["frequency_trend_pct"]), _cell(ad["cpm"], 2), _cell(ad["cpa"], 2),
            _cell(ad["roas"], 2), ",".join(ad["flags"]) or "-",
        ])
    widths = [max(len(header[i]), *(len(r[i]) for r in lines)) if lines else len(header[i])
              for i in range(len(header))]
    out = ["  ".join(h.ljust(w) for h, w in zip(header, widths))]
    out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in lines]
    notes = _video_notes(report)
    if notes:
        out += ["", "Notes (video metrics that could not be computed):"] + ["  " + n for n in notes]
    out += ["", "n/a = missing or zero operand, never 0. Trends compare an ad's first and last 7 "
                "delivery days (an arbitrary default: set the window from your account's own time to "
                "stabilise); ctr<p25 is relative to this account's own format baseline."]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Per-ad creative metrics from an Ads Manager export.")
    parser.add_argument("path", help="CSV export (daily rows recommended)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    report = build_report(load_rows(args.path))
    print(json.dumps(report, indent=2) if args.json else render_table(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
