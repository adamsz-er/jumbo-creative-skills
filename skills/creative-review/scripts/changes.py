"""What changed since the last review of the same account, as plain sentences.

Standard library only. compare() reads the latest earlier run folder (its
ads.csv copy and verdicts.json) and sets it against the run in hand: verdict
changes per ad, new ads, ads no longer present, and the account's spend, ROAS
and CPA (each a ratio of sums, never an average of per-ad ratios), sorted by
the spend at stake. With no earlier run it returns {"first_run": true}.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

# Below this share (percent) of the smaller run's ads appearing in both, two runs filed under the
# bare fallback name are taken to be different accounts. Arbitrary default.
OVERLAP_FLOOR = 18
DIFFERENT_ACCOUNT = "This looks like a different account from the last review filed here: not compared."
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


def latest_earlier_run(account_dir: Path, current_name: str) -> Optional[Path]:
    """The newest run folder in `account_dir` that sorts before `current_name`, or None."""
    if not account_dir.is_dir():
        return None
    earlier = sorted(p for p in account_dir.iterdir() if p.is_dir() and p.name < current_name
                     and ads_file(p) and (p / "verdicts.json").exists())
    return earlier[-1] if earlier else None


def _ids(rows: Sequence[Dict[str, Any]]) -> set:
    return {str(r.get("ad_id") or r.get("ad_name")) for r in rows if r.get("ad_id") or r.get("ad_name")}


def overlap_percent(previous: Sequence[Dict[str, Any]], current: Sequence[Dict[str, Any]]) -> float:
    a, b = _ids(previous), _ids(current)
    smaller = min(len(a), len(b))
    return 100.0 * len(a & b) / smaller if smaller else 0.0


def _entries(verdicts: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(e.get("ad")): e for e in (verdicts or {}).get("ads") or []}


def _stake(entry: Dict[str, Any]) -> float:
    return float(entry.get("spend_at_stake") or 0.0)


def verdict_name(entry: Dict[str, Any]) -> str:
    """The verdict's short name: "Scale" from "Scale: raise budget in steps"."""
    return str(entry.get("verdict") or "no verdict").split(":")[0]


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
                          "sentence": "%s: %s to %s (%s at stake)" % (label, previous[ad].get("verdict"), verdict_name(now), money(_stake(now), currency))})
    for ad, old in previous.items():
        if ad not in current:
            label = old.get("ad_name") or ad
            moves.append({"kind": "gone", "ad": ad, "name": label, "stake": _stake(old),
                          "sentence": "%s is no longer in the data (was %s)" % (label, verdict_name(old))})
    return sorted(moves, key=lambda m: (-m["stake"], m["name"]))


def compare(previous_run_dir: Optional[Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Set the run in hand against the previous run folder.

    `current` holds "rows" (normalised), "verdicts" (the verdicts.json dict), "currency" and, for a run filed
    under the bare fallback name, "fallback_slug": True, which makes the comparison refuse when the two runs
    share too few ads.
    """
    if previous_run_dir is None:
        return {"first_run": True}
    folder = Path(previous_run_dir)
    before_rows = cm.load_rows(str(ads_file(folder)))
    if current.get("fallback_slug") and overlap_percent(before_rows, current["rows"]) < OVERLAP_FLOOR:
        return {"first_run": False, "previous_run": folder.name, "not_compared": DIFFERENT_ACCOUNT}
    before_verdicts = json.loads((folder / "verdicts.json").read_text(encoding="utf-8"))
    currency = current.get("currency")
    return {"first_run": False, "previous_run": folder.name, "not_compared": None,
            "account": account_moves(before_rows, current["rows"], currency),
            "ads": ad_moves(_entries(before_verdicts), _entries(current.get("verdicts")), currency)}
