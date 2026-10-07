"""What changed since the last review of the same account, as plain sentences.

Standard library only. compare() reads the latest earlier run folder (its
ads.csv copy and verdicts.json) and sets it against the run in hand: verdict
changes per ad, new ads, ads no longer present, and the account's spend, ROAS
and CPA (each a ratio of sums, never an average of per-ad ratios), sorted by
the spend at stake. With no earlier run it returns {"first_run": true}.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

# Below this share (percent) of the larger run's ads appearing in both, two runs are taken to be
# different accounts, whatever folder they were filed under. Arbitrary default.
OVERLAP_FLOOR = 18
DIFFERENT_ACCOUNT = "This looks like a different account from the last review filed here: not compared."
DIFFERENT_SCOPE = "The last review covered a different window or filter: not compared."
RUN_FILE = "run.json"
FIRST_RUN_TEXT = "First review of this account: next time this shows what changed."


def money(value: float, currency: Optional[str]) -> str:
    text = "{:,.0f}".format(value)
    return "%s %s" % (currency, text) if currency else text


def totals(rows: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Summed spend, purchases and purchase value; None when no row carries the field."""
    out: Dict[str, Optional[float]] = {}
    for field in ("spend", "conversions", "conversion_value"):
        values = [r[field] for r in rows if r.get(field) is not None]
        out[field] = sum(values) if values else None
    return out


def roas(t: Dict[str, Optional[float]]) -> Optional[float]:
    if t["conversion_value"] is None or not t["spend"]:
        return None
    return t["conversion_value"] / t["spend"]


def cpa(t: Dict[str, Optional[float]]) -> Optional[float]:
    if t["spend"] is None or not t["conversions"]:
        return None
    return t["spend"] / t["conversions"]


def _percent(before: float, after: float) -> Optional[float]:
    return None if not before else (after - before) / before * 100


def _move(label: str, before: Optional[float], after: Optional[float], show, missing: str) -> Dict[str, Any]:
    if before is None or after is None:
        return {"metric": label, "previous": before, "current": after, "change_pct": None,
                "sentence": "%s: n/a (missing %s)" % (label, missing)}
    pct = _percent(before, after)
    if pct is None:
        return {"metric": label, "previous": before, "current": after, "change_pct": None,
                "sentence": "%s is now %s (the last review had none to compare)" % (label, show(after))}
    word = "up" if pct > 0 else "down" if pct < 0 else "unchanged"
    short = label + " " + word + ("" if word == "unchanged" else " %.0f%%" % abs(pct))
    sentence = ("%s at %s" % (short, show(after))) if word == "unchanged" else "%s, to %s (was %s)" % (short, show(after), show(before))
    return {"metric": label, "previous": before, "current": after, "change_pct": pct, "short": short, "sentence": sentence}


def account_moves(previous: Sequence[Dict[str, Any]], current: Sequence[Dict[str, Any]],
                  currency: Optional[str]) -> List[Dict[str, Any]]:
    before, after = totals(previous), totals(current)
    cash = lambda v: money(v, currency)  # noqa: E731
    return [
        _move("Spend", before["spend"], after["spend"], cash, "spend"),
        _move("ROAS", roas(before), roas(after), lambda v: "%.2f" % v, "purchase value or spend"),
        _move("Cost per purchase", cpa(before), cpa(after), lambda v: ("%s %.2f" % (currency or "", v)).strip(), "purchases or spend"),
    ]


def ads_file(folder: Path) -> Optional[Path]:
    """The copy of the data a run folder keeps: ads.csv, or ads.json when the run used a date window."""
    return next((p for p in (folder / "ads.csv", folder / "ads.json") if p.exists()), None)


def read_run(folder: Path) -> Optional[Dict[str, Any]]:
    """A run folder's run.json, or None when it is missing or unreadable."""
    try:
        info = json.loads((folder / RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) else None


def made_at(info: Dict[str, Any]) -> Optional[dt.datetime]:
    """When a run was made, from its run.json; None when the time is missing, unreadable or has no time zone."""
    try:
        made = dt.datetime.fromisoformat(info["created_at"])
    except (KeyError, ValueError, TypeError):
        return None
    return made if made.tzinfo is not None else None


def latest_earlier_run(account_dir: Path, created_at: str) -> Optional[Path]:
    """The newest finished run in `account_dir` made strictly before `created_at` (ISO), or None.

    Order comes from run.json, never from the folder name. A run that did not finish
    (no "complete": true) is skipped, so a failed run is never compared against.
    """
    if not account_dir.is_dir():
        return None
    before = dt.datetime.fromisoformat(created_at)
    found = []
    for folder in account_dir.iterdir():
        info = read_run(folder) if folder.is_dir() else None
        made = made_at(info) if info else None
        if made and info.get("complete") is True and ads_file(folder) and (folder / "verdicts.json").exists():
            if made < before:
                found.append((made, folder))
    return max(found, key=lambda pair: pair[0])[1] if found else None


def _ids(rows: Sequence[Dict[str, Any]]) -> set:
    return {str(r.get("ad_id") or r.get("ad_name")) for r in rows if r.get("ad_id") or r.get("ad_name")}


def overlap_percent(previous: Sequence[Dict[str, Any]], current: Sequence[Dict[str, Any]]) -> float:
    a, b = _ids(previous), _ids(current)
    larger = max(len(a), len(b))
    return 100.0 * len(a & b) / larger if larger else 0.0


def _entries(verdicts: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(e.get("ad")): e for e in (verdicts or {}).get("ads") or []}


def _stake(entry: Dict[str, Any]) -> float:
    return float(entry.get("spend_at_stake") or 0.0)


def verdict_name(entry: Dict[str, Any]) -> str:
    """The verdict's short name: "Scale" from "Scale: raise budget in steps"."""
    return str(entry.get("verdict") or "no verdict").split(":")[0].strip()


def ad_moves(previous: Dict[str, Dict[str, Any]], current: Dict[str, Dict[str, Any]],
             currency: Optional[str]) -> List[Dict[str, Any]]:
    moves = []
    for ad, now in current.items():
        label = now.get("ad_name") or ad
        if ad not in previous:
            moves.append({"kind": "new", "ad": ad, "name": label, "stake": _stake(now),
                          "sentence": "New ad %s: %s (%s at stake)" % (label, verdict_name(now), money(_stake(now), currency))})
        elif previous[ad].get("verdict_id") != now.get("verdict_id"):
            moves.append({"kind": "verdict", "ad": ad, "name": label, "stake": _stake(now),
                          "sentence": "%s: was %s, now %s (%s at stake)" % (label, verdict_name(previous[ad]), verdict_name(now), money(_stake(now), currency))})
    for ad, old in previous.items():
        if ad not in current:
            label = old.get("ad_name") or ad
            moves.append({"kind": "gone", "ad": ad, "name": label, "stake": _stake(old),
                          "sentence": "%s is no longer in the data (was %s)" % (label, verdict_name(old))})
    return sorted(moves, key=lambda m: (-m["stake"], m["name"]))


def compare(previous_run_dir: Optional[Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Set the run in hand against the previous run folder.

    `current` holds "rows" (the rows analysed: after --from, --to and --where), "verdicts" (the
    verdicts.json dict), "currency", "window_days" (how many days the window spans), "where" (a normalised list or
    None) and "scope" (a function that applies the same --where to the previous run's saved data).
    The comparison is refused when the two runs share too few ads (a different account) or when
    their window length or filter differ, so what is compared is always like for like. A rolling
    window (the last N days, run again later) has the same length, so it still compares.
    """
    if previous_run_dir is None:
        return {"first_run": True}
    folder = Path(previous_run_dir)
    info = read_run(folder) or {}
    base = {"first_run": False, "previous_run": folder.name, "previous_at": info.get("created_at")}
    if info.get("window_days") != current.get("window_days") or info.get("where") != current.get("where"):
        return dict(base, not_compared=DIFFERENT_SCOPE)
    before_rows = cm.load_rows(str(ads_file(folder)))
    before_rows = current["scope"](before_rows) if current.get("scope") else before_rows
    if overlap_percent(before_rows, current["rows"]) < OVERLAP_FLOOR:
        return dict(base, not_compared=DIFFERENT_ACCOUNT)
    before_verdicts = json.loads((folder / "verdicts.json").read_text(encoding="utf-8"))
    currency = current.get("currency")
    return dict(base, not_compared=None,
                account=account_moves(before_rows, current["rows"], currency),
                ads=ad_moves(_entries(before_verdicts), _entries(current.get("verdicts")), currency))
