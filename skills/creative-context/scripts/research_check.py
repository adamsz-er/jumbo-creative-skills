#!/usr/bin/env python3
"""Check a drafted "Seeded from public research" profile section before it is saved.

Usage: python3 research_check.py profile-draft.md [--json]

Standard library only, no network. Reads the section that starts at the heading
"## Seeded from public research" and runs to the next "## " heading. Inside it,
"### <Topic>" subheadings (Claims, Proof points, Objections, Tone, Category words,
Products) hold bullets shaped "- <text> [<label>] (<source>)". The label is one of
"from the brand's site", "from public reviews" or "inferred". Site and review
bullets cite a URL; an inferred bullet names what it rests on, "(based on: ...)",
and carries no figure. Review bullets are paraphrased, never quoted, and a review
page is not the brand's own site.

Prints each problem as "<file>:<line>: <rule>: <detail>", then a summary. Exit 0
when clean, 1 when any problem is found, 2 when the file cannot be read. The check
has no numeric settings; there are no thresholds to tune.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

SECTION = "## Seeded from public research"
TOPICS = ("Claims", "Proof points", "Objections", "Tone", "Category words", "Products")
SITE, REVIEWS, INFERRED = "from the brand's site", "from public reviews", "inferred"
LABELS = (SITE, REVIEWS, INFERRED)
LIMIT = ("A clean check does not prove a bullet is a paraphrase of its source, only that the checks it runs found "
         "nothing; a human still reads it.")

BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
LABEL = re.compile(r"\[(%s)\]" % "|".join(re.escape(l) for l in LABELS))
SOURCE = re.compile(r"^\s*\((.*)\)\s*[.,;]?\s*$")
DOUBLE_QUOTE = re.compile(r"[\"“”]")
SINGLE_QUOTED = re.compile(r"(?<!\w)['‘](\S+(?:\s+\S+){2,})['’](?!\w)")
REVIEW_FIGURE = re.compile(
    r"%|\bpercent\b|\bstars?\b|\d(?:\.\d)?\s*/\s*\d|\b\d+\s+out\s+of\s+\d+\b", re.IGNORECASE)


def section_lines(lines: List[str]) -> List[tuple]:
    """(line number, text) for the lines inside the seeded section."""
    inside, found = False, []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == SECTION:
            inside = True
        elif inside and line.startswith("## "):
            break
        elif inside:
            found.append((number, line))
    return found if inside else []


def parse_bullet(number: int, topic: str, body: str) -> Dict[str, object]:
    """Split one bullet into text, label and source (label None when absent)."""
    match = LABEL.search(body)
    if not match:
        return {"line": number, "topic": topic, "text": body.strip(), "label": None, "source": ""}
    source = SOURCE.match(body[match.end():])
    cleaned = source.group(1).strip().rstrip(".,;") if source else ""
    return {"line": number, "topic": topic, "text": body[:match.start()].strip(),
            "label": match.group(1), "source": cleaned}


def host(url: str) -> str:
    name = urlparse(url).hostname or ""
    return name[4:] if name.startswith("www.") else name


def is_url(text: str) -> bool:
    return text.startswith(("https://", "http://"))


def source_problem(bullet: Dict[str, object]) -> Optional[str]:
    label, source = bullet["label"], str(bullet["source"])
    if label == INFERRED:
        basis = source[len("based on:"):].strip() if source.startswith("based on:") else ""
        if not basis or is_url(basis):
            return "an inferred line needs (based on: <what it was inferred from>), not a URL"
    elif not is_url(source):
        return "a '%s' line needs a URL source in brackets, https:// or http://" % label
    return None


def check_bullet(bullet: Dict[str, object]) -> List[Dict[str, object]]:
    """Problems for one bullet, rules 3 to 7."""
    line, label, text = bullet["line"], bullet["label"], str(bullet["text"])
    if label is None:
        return [{"line": line, "rule": "unlabelled",
                 "detail": "add one label: [from the brand's site], [from public reviews] or [inferred]"}]
    found = []
    detail = source_problem(bullet)
    if detail:
        found.append({"line": line, "rule": "no-source", "detail": detail})
    if label == REVIEWS:
        if DOUBLE_QUOTE.search(text) or SINGLE_QUOTED.search(text):
            found.append({"line": line, "rule": "quoted-review",
                          "detail": "paraphrase public reviews, never quote them"})
        if REVIEW_FIGURE.search(text):
            found.append({"line": line, "rule": "review-number",
                          "detail": "check: a figure from reviews needs its source and date"})
    if label == INFERRED and re.search(r"\d", text):
        found.append({"line": line, "rule": "invented-figure",
                      "detail": "an inference cannot produce a number; drop the figure or find its source"})
    return found


def check_same_domain(bullets: List[Dict[str, object]]) -> List[Dict[str, object]]:
    sites = [host(str(b["source"])) for b in bullets if b["label"] == SITE and is_url(str(b["source"]))]
    if not sites:
        return []
    own = Counter(sites).most_common(1)[0][0]
    return [{"line": b["line"], "rule": "same-domain",
             "detail": "%s is the brand's own site, not a public review" % own}
            for b in bullets
            if b["label"] == REVIEWS and is_url(str(b["source"])) and host(str(b["source"])) == own]


def check(lines: List[str]) -> Dict[str, object]:
    """Bullets, problems and counts for a draft given as lines."""
    body = section_lines(lines)
    if not body:
        problem = {"line": 1, "rule": "missing-section", "detail": "no '%s' heading" % SECTION}
        return result([], [problem])
    bullets: List[Dict[str, object]] = []
    problems: List[Dict[str, object]] = []
    topic, topic_line, topic_bullets = "", 0, 0

    def close_topic() -> None:
        if topic and topic in TOPICS and topic_bullets == 0:
            problems.append({"line": topic_line, "rule": "empty-topic",
                             "detail": "'%s' has no bullets: leave it out or write 'nothing found'" % topic})

    for number, line in body:
        if line.startswith("### "):
            close_topic()
            topic, topic_line, topic_bullets = line[4:].strip(), number, 0
            if topic not in TOPICS:
                problems.append({"line": number, "rule": "unknown-topic",
                                 "detail": "'%s' is not one of: %s" % (topic, ", ".join(TOPICS))})
            continue
        match = BULLET.match(line)
        if match:
            bullet = parse_bullet(number, topic, match.group(1))
            bullets.append(bullet)
            topic_bullets += 1
            problems.extend(check_bullet(bullet))
    close_topic()
    problems.extend(check_same_domain(bullets))
    return result(bullets, problems)


def result(bullets: List[Dict[str, object]], problems: List[Dict[str, object]]) -> Dict[str, object]:
    labels = Counter(b["label"] for b in bullets)
    return {"bullets": bullets,
            "problems": sorted(problems, key=lambda p: p["line"]),
            "counts": {"bullets": len(bullets), "from_site": labels[SITE],
                       "from_reviews": labels[REVIEWS], "inferred": labels[INFERRED],
                       "problems": len(problems)},
            "limit": LIMIT,
            "settings": {"topics": list(TOPICS), "labels": list(LABELS)}}


def summary(counts: Dict[str, int]) -> str:
    return ("%d bullets checked: %d from the brand's site, %d from public reviews, %d inferred; %d problems"
            % (counts["bullets"], counts["from_site"], counts["from_reviews"],
               counts["inferred"], counts["problems"]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("draft", help="markdown profile draft containing the seeded section")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)
    try:
        lines = Path(args.draft).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print("Cannot read %s: %s" % (args.draft, exc), file=sys.stderr)
        return 2
    report = check(lines)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for p in report["problems"]:
            print("%s:%d: %s: %s" % (args.draft, p["line"], p["rule"], p["detail"]))
        print(summary(report["counts"]))
        print(LIMIT)
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
