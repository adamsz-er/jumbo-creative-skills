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
    "cpc": (("spend",), ("clicks", "link_clicks"), 1.0),
    "cpa": (("spend",), ("conversions",), 1.0),
    "roas": (("conversion_value",), ("spend",), 1.0),
    "cvr": (("conversions",), ("clicks", "link_clicks"), 100.0),
    "add_to_cart_rate": (("add_to_carts",), ("clicks", "link_clicks"), 100.0),
    "cost_per_add_to_cart": (("spend",), ("add_to_carts",), 1.0),
    "frequency": (("impressions",), ("reach",), 1.0),
    "mer": (("revenue",), ("spend",), 1.0),
}

# An alias is another name for the same metric, never a second metric.
METRIC_ALIASES = {"thumb_stop_rate": "hook_rate"}

NUMERIC_FIELDS = (
    "spend", "impressions", "reach", "video_views_3s", "video_thruplay",
    "link_clicks", "clicks", "conversions", "conversion_value", "add_to_carts",
    "revenue",
)
NAME_FIELDS = ("concept", "format", "creator", "ad_type", "product", "tone", "launch_date")

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
    "adname": "ad_name", "adid": "ad_id",
    "day": "date", "date": "date", "reportingstarts": "date", "datestart": "date",
}
# "Results" means whatever the campaign objective optimises for, so it only
# fills conversions when no purchases column exists.
_WEAK_ALIASES = {"results": "conversions"}
_STRING_FIELDS = ("ad_name", "ad_id", "date")
_API_ACTION_TYPES = {
    "video_view": "video_views_3s",
    "purchase": "conversions",
    "add_to_cart": "add_to_carts",
}
_API_VALUE_TYPES = {"purchase": "conversion_value"}
_API_LIST_FIELDS = {"video_thruplay_watched_actions": "video_thruplay"}


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
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[,$€£%\s]", "", str(value))
    try:
        return float(text)
    except ValueError:
        return None


def _list_value(items: Any) -> Optional[float]:
    """Sum the `value` of Meta API action-stat lists; None if there are none."""
    if not isinstance(items, list):
        return _num(items)
    values = [_num(i.get("value")) for i in items if isinstance(i, dict)]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _normalise_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    passthrough: Dict[str, Any] = {}
    out: Dict[str, Any] = {}
    weak: Dict[str, Any] = {}

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
        if field in _STRING_FIELDS:
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
    passthrough.update(out)
    return passthrough


def load_rows(path_or_rows: Union[str, "os.PathLike[str]", Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Load an Ads Manager CSV (path), a .json file of rows, or Meta API rows (list of dicts).

    A .json path holds a list of row dicts, or an API response with a "data" list.

    Column names are mapped to canonical fields through an alias map, ignoring
    case and punctuation. Numeric fields become floats (blank cells become
    None). Columns that Meta computes itself (ctr, cpm, frequency, ...) are kept
    as `reported_<name>` and never used: every metric is recomputed from counts.
    Unknown columns pass through untouched. `conversions_source` records which
    column fed conversions: "Purchases" wins over "Results" when both exist, so
    a non-purchase objective's Results never silently become purchases.
    """
    if isinstance(path_or_rows, (str, bytes)) or hasattr(path_or_rows, "__fspath__"):
        if str(path_or_rows).lower().endswith(".json"):
            with open(path_or_rows, encoding="utf-8-sig") as handle:
                loaded = json.load(handle)
            raw_rows = loaded.get("data", []) if isinstance(loaded, dict) else loaded
        else:
            with open(path_or_rows, newline="", encoding="utf-8-sig") as handle:
                raw_rows = list(csv.DictReader(handle))
    else:
        raw_rows = path_or_rows
    return [_normalise_row(dict(r)) for r in raw_rows]


def _pick(row: Dict[str, Any], fields: Sequence[str]) -> Tuple[str, Optional[float]]:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return field, value
    return fields[0], None


def compute_metrics(row: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Compute every metric in METRICS from a row's base fields.

    A missing operand or a zero denominator gives None, never 0.
    """
    result: Dict[str, Optional[float]] = {}
    for name, (num_fields, den_fields, scale) in METRICS.items():
        _, num = _pick(row, num_fields)
        _, den = _pick(row, den_fields)
        result[name] = None if num is None or den is None or den == 0 else num / den * scale
    return result


def metric_basis(row: Dict[str, Any], metric: str) -> Dict[str, Optional[str]]:
    """Say which fields fed a metric, e.g. whether ctr used link or all clicks."""
    num_fields, den_fields, _ = METRICS[resolve_metric(metric)]
    num_field, num = _pick(row, num_fields)
    den_field, den = _pick(row, den_fields)
    return {
        "numerator": num_field if num is not None else None,
        "denominator": den_field if den is not None else None,
    }


def describe_missing(row: Dict[str, Any], metric: str) -> Optional[str]:
    """Why a metric is unavailable for a row, or None when it can be computed."""
    num_fields, den_fields, _ = METRICS[resolve_metric(metric)]
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


def aggregate_by_ad(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sum base fields per ad (by ad id, else ad name) and compute metrics.

    Adds first_date, last_date, active_days (days with delivery) and age_days
    (days from first delivery to the latest date in the data). Reach is summed
    across rows, so with daily rows `frequency` is an average per-row frequency,
    not lifetime frequency; export a lifetime row for that. Age is measured
    inside the export window, so an ad older than the window looks as young as
    the window start.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = row.get("ad_id") or row.get("ad_name")
        if key is None:
            raise ValueError("row has neither ad_id nor ad_name: %r" % (row,))
        groups.setdefault(key, []).append(row)

    all_dates = [d for d in (_parse_date(r.get("date")) for r in rows) if d]
    data_end = max(all_dates) if all_dates else None

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
        ad["age_days"] = (data_end - min(dated)).days if dated and data_end else None
        parsed = parse_name(ad["ad_name"]) if ad["ad_name"] else {}
        ad["conversions_source"] = next((r["conversions_source"] for r in group
                                         if r.get("conversions_source")), None)
        for field in NAME_FIELDS:
            carried = next((r[field] for r in group if r.get(field)), None)
            ad[field] = carried or parsed.get(field)
        ad.update(compute_metrics(ad))
        ads.append(ad)
    return ads


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


def parse_name(ad_name: Optional[str], pattern: Optional[Sequence[str]] = None) -> Dict[str, str]:
    """Split an ad name into naming-convention fields; {} when it does not fit.

    Names split on " | " or on "_". `pattern` is the ordered list of field
    names (default: NAME_FIELDS). The part count must match exactly.
    """
    fields = tuple(pattern) if pattern else NAME_FIELDS
    if not ad_name:
        return {}
    separator = " | " if " | " in ad_name else "_" if "_" in ad_name else None
    if separator is None:
        return {}
    parts = [p.strip() for p in ad_name.split(separator)]
    if len(parts) != len(fields):
        return {}
    parsed = dict(zip(fields, parts))
    for field in ("format", "ad_type", "tone"):
        if field in parsed:
            parsed[field] = parsed[field].lower()
    return parsed


BAND_TOP, BAND_MID, BAND_BOTTOM = "top quartile", "middle", "bottom quartile"
HIGHER_IS_BETTER = ("hook_rate", "hold_rate", "video_completion_rate", "ctr", "cvr",
                    "add_to_cart_rate", "roas")
LOWER_IS_BETTER = ("cpm", "cpc", "cpa", "cost_per_add_to_cart")
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
    if len(pool) < MIN_GROUP:
        return not_graded("too little comparison data: %d comparable ads, need %d" % (len(pool), MIN_GROUP))
    result["percentile"] = percentile_rank(result["value"], pool)
    result["p25"], result["median"], result["p75"] = stats["p25"], stats["median"], stats["p75"]
    if stats["p25"] == stats["p75"]:
        result["band"] = BAND_MID
        return result
    high = result["value"] >= stats["p75"]
    low = result["value"] <= stats["p25"]
    if metric in LOWER_IS_BETTER:
        high, low = low, high
    result["band"] = BAND_TOP if high else BAND_BOTTOM if low else BAND_MID
    return result


def data_window(rows: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """First and last date (ISO) found in the rows, or (None, None)."""
    days = [d for d in (_parse_date(r.get("date")) for r in rows) if d]
    return (min(days).isoformat(), max(days).isoformat()) if days else (None, None)


def window_aggregate(rows: Sequence[Dict[str, Any]], window: int = 6,
                     which: str = "first") -> List[Dict[str, Any]]:
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
    return aggregate_by_ad(chosen) if chosen else []


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
