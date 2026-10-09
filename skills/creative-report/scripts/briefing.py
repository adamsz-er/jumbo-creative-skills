"""Brief cards for the Briefing tab: briefs.json validation and the copy-ready prompts. No HTML.

A briefs file is a JSON list the agent writes with the creative-brief and hook-writer
skills. Unknown keys are ignored, a missing key reads "not stated", and a metric id that
the metric library does not define is shown as written and flagged. The prompts carry
labels only (concept, format and gap names), never a figure from the data. Standard
library only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import creative_metrics as cm  # noqa: E402

BRIEF_KEYS = ("title", "objective", "persona", "stage", "message", "format", "specs")
LIST_KEYS = ("hooks", "reference_ads", "judged_by")
NOT_STATED = "not stated"
STARTER_GAPS = 3  # arbitrary default: how many coverage gaps become a brief starter
STARTER_ITERATE = 2  # arbitrary default: how many Iterate ads become a brief starter
STARTERS_PER_FORMAT = 2  # arbitrary default: most brief starters one format gets, so the tab does not read as one idea
HOOKS_PLACEHOLDER = "Hooks: ask the hook-writer skill"


def _text(value: Any) -> str:
    text = "" if value is None or isinstance(value, (dict, list)) else str(value).strip()
    return text or NOT_STATED


def _items(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip()]


def metric_status(metric_id: str) -> Dict[str, Any]:
    """{"id", "defined"}: defined when the metric library knows the id (or its alias)."""
    try:
        cm.resolve_metric(metric_id)
        return {"id": metric_id, "defined": True}
    except KeyError:
        return {"id": metric_id, "defined": False}


def validate_briefs(data: Any) -> List[Dict[str, Any]]:
    """A briefs file's JSON as cards: every key present, "not stated" where it was missing, metric ids checked."""
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("--briefs must be a JSON list of brief objects (title, objective, persona, stage, message, hooks, "
                         "format, specs, reference_ads, judged_by)")
    briefs = []
    for item in data:
        brief: Dict[str, Any] = {key: _text(item.get(key)) for key in BRIEF_KEYS}
        brief["hooks"] = _items(item.get("hooks"))
        brief["reference_ads"] = _items(item.get("reference_ads"))
        brief["judged_by"] = [metric_status(m) for m in _items(item.get("judged_by"))]
        briefs.append(brief)
    return briefs


def _list(names: Sequence[str]) -> str:
    return ", ".join(names) if names else "none read yet (too few to rank)"


def _plain(slug: Any) -> str:
    return str(slug).replace("-", " ").replace("_", " ")


def gap_label(concept: Any, fmt: Any) -> str:
    return "%s in %s" % (_plain(concept), _plain(fmt))


def ideation_prompt(concepts: Sequence[str], formats: Sequence[str], gaps: Sequence[str]) -> str:
    return ("Use the creative-ideation skill for this account.\n"
            "Concepts that already work: %s.\n"
            "Formats that already work: %s.\n"
            "Gaps worth testing: %s.\n"
            "Suggest new concepts that fit the gaps, each with one reason it could work. "
            "Do not repeat the concepts above." % (_list([_plain(c) for c in concepts]), _list([_plain(f) for f in formats]), _list(gaps)))


def hook_prompt(concepts: Sequence[str], gaps: Sequence[str]) -> str:
    return ("Use the hook-writer skill for this account.\n"
            "Write hook options for these gaps: %s.\n"
            "Concepts that already work, for tone: %s.\n"
            "Change one thing per variant and say what each variant tests." % (_list(gaps), _list([_plain(c) for c in concepts])))


def brief_prompt(gaps: Sequence[str], formats: Sequence[str]) -> str:
    return ("Use the creative-brief skill for this account, and the hook-writer skill for the hook options.\n"
            "Write a production-ready brief for the first gap: %s.\n"
            "Formats that already work, for reference: %s.\n"
            "Say how it will be judged against this account's own similar ads."
            % (gaps[0] if gaps else "none read yet (pick one from the gap list)", _list([_plain(f) for f in formats])))


def starter_prompt(subject: str, reason: str) -> str:
    """The prompt on a brief starter: what to make and why, in words, never a figure."""
    return ("Use the creative-brief and hook-writer skills to write the full brief and hook options for this.\n"
            "Make: %s.\n"
            "Why: %s\n"
            "Judge it against this account's own similar ads." % (subject, reason))
