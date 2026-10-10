"""The two or three skills a review's own findings point to next, by fixed rules in priority order.

Each rule reads the review's verdicts and mix output and fires only on a finding in this run; the first
MAX_STEPS rules that fire are the answer. When fewer than MIN_STEPS fire, the always-useful steps fill in.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

MAX_STEPS = 3
MIN_STEPS = 2


def _ads(verdicts: Dict[str, Any], *ids: str) -> List[Dict[str, Any]]:
    return [a for a in verdicts.get("ads") or [] if a.get("verdict_id") in ids or
            any(a.get("verdict_id", "").startswith(i.rstrip("*")) for i in ids if i.endswith("*"))]


def _count(n: int, noun: str) -> str:
    return "%d %s%s" % (n, noun, "" if n == 1 else "s")


def _unread_names(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    if mix.get("concepts_unread"):
        return "your ad names could not be read for concepts: audit them and get a rename plan, so the next review can compare ideas"
    return None


SITE_STEPS = ("landing_page_view_rate", "add_to_cart_rate", "cart_to_checkout_rate")


def _site(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    ads = _ads(verdicts, "check_site")
    if ads:
        return "%s would be paused but %s to the landing page or checkout: check the site before cutting" % (
            _count(len(ads), "ad"), "points" if len(ads) == 1 else "point")
    paused = [a for a in _ads(verdicts, "pause_*")
              if any(s in SITE_STEPS for s in (a.get("funnel") or {}).get("weak_steps") or [])]
    if paused:
        return "%s judged pause also %s a weak landing page or checkout step: fix the page before the replacement runs" % (
            _count(len(paused), "ad"), "shows" if len(paused) == 1 else "show")
    return None


def _fatigue(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    ads = [a for a in verdicts.get("ads") or [] if a.get("fatiguing")]
    if ads:
        return "%s %s wearing out: see how many days each has left and plan the refreshes to your capacity" % (
            _count(len(ads), "ad"), "is" if len(ads) == 1 else "are")
    return None


def _spend(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    paused, scaled = _ads(verdicts, "pause_*"), _ads(verdicts, "scale")
    if paused and scaled:
        return "money sits on %s judged pause while %s earned a scale call: size the move" % (
            _count(len(paused), "ad"), _count(len(scaled), "ad"))
    if paused:
        return "%s judged pause still hold spend: see where that money should go" % _count(len(paused), "ad")
    if scaled:
        return "%s earned a scale call: check their room to grow before moving budget" % _count(len(scaled), "ad")
    return None


def _gaps(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    gaps = mix.get("gaps") or []
    if gaps:
        first = gaps[0]
        return "the mix has %s, starting with %s as a %s: turn them into concepts" % (
            _count(len(gaps), "untried idea and format pairing"), first.get("concept"), first.get("format"))
    return None


def _hooks(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    ads = _ads(verdicts, "iterate")
    if ads:
        return "%s %s a new opening on a concept that still pays: write one-change hook variants" % (
            _count(len(ads), "ad"), "needs" if len(ads) == 1 else "need")
    return None


def _test(verdicts: Dict[str, Any], mix: Dict[str, Any]) -> Optional[str]:
    if _ads(verdicts, "scale"):
        return "test one change on a winner and check first whether the account can power the test"
    return None


RULES: Sequence[tuple] = (
    ("ad-namer", _unread_names),
    ("funnel-diagnosis", _site),
    ("fatigue-planner", _fatigue),
    ("spend-analysis", _spend),
    ("creative-ideation", _gaps),
    ("hook-writer", _hooks),
    ("copy-tests", _test),
)
FILL = (
    ("creative-ideation", "turn what worked into new concepts"),
    ("creative-brief", "brief the next ad with the evidence from this review"),
)


def next_steps(verdicts: Optional[Dict[str, Any]], mix: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """[{skill, why}] in priority order, at most MAX_STEPS, at least MIN_STEPS."""
    verdicts, mix = verdicts or {}, mix or {}
    steps: List[Dict[str, str]] = []
    for skill, rule in RULES:
        why = rule(verdicts, mix)
        if why and len(steps) < MAX_STEPS:
            steps.append({"skill": skill, "why": why})
    for skill, why in FILL:
        if len(steps) >= MIN_STEPS:
            break
        if all(s["skill"] != skill for s in steps):
            steps.append({"skill": skill, "why": why})
    return steps


def render(steps: Sequence[Dict[str, str]]) -> str:
    return "\n".join(["Next steps:"] + ["  %d. %s: %s." % (n, s["skill"], s["why"]) for n, s in enumerate(steps, 1)])
