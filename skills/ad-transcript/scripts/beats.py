#!/usr/bin/env python3
"""Break a video ad transcript into beats and flag structural problems.

Usage: python3 beats.py transcript.txt [--product "rain shell,Acme"] [--json]

Standard library only. Reads plain text (lines starting with # are notes and are skipped), SRT or VTT. Beats are labelled by
keyword and position, so the table is a first pass: read it, then apply
judgement. Timings appear only when the file carries timestamps. Nothing here
is a benchmark: it describes this one script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

HOOK_WINDOW = 3.0  # seconds; sentences starting inside it count as the hook
STRUCTURE = ("problem", "solution", "proof", "offer", "cta")

_TIME = r"(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3}"
_CUE = re.compile(r"(%s)\s*-->\s*(%s)" % (_TIME, _TIME))
_SPLIT = re.compile(r"(?<=[.!?])\s+")

CTA = re.compile(r"^(?:(?:so|and|now|then|just|go)\s+)*(?:shop|get|try|tap|click|order|buy|grab|visit|claim|"
                 r"start|join|download|swipe|book|sign up|learn more)\b|"
                 r"\b(?:link (?:below|in bio)|tap the|click the|shop now|order today|order now)\b", re.I)
OFFER = re.compile(r"%|\$|\bfree\b|\bcode\b|\boff\b|\bdiscount|\bsale\b|\bprice|\bbundle\b|\bshipping\b|"
                   r"\bsave\b|\bdeal\b", re.I)
PROOF = re.compile(r"\breviews?\b|\brated\b|\bstars?\b|\btested\b|\bcustomers?\b|\bi'?ve (?:used|worn|had)\b|"
                   r"\bafter \d+|\b\d[\d,]*\s*(?:years?|weeks?|months?|days?|people|reviews|miles)\b|"
                   r"\b(?:one|two|three|four|five|six|seven|eight|nine)\s+(?:years?|weeks?|months?)\b", re.I)
SOLUTION = re.compile(r"\bintroducing\b|\bmeet (?:the|our)\b|\bthat'?s why\b|\bso (?:i|we) (?:made|built|found|"
                      r"switched)|\bhere'?s how\b|\bthe fix\b|\bfinally\b|\bwe (?:made|built|designed)\b|"
                      r"\bour new\b|\bit'?s (?:made|built|designed)\b|\bis (?:welded|built|made|designed)\b", re.I)
AGITATION = re.compile(r"\bworse\b|\bimagine\b|\bevery (?:single )?time\b|\band then\b|\bkeeps?\b|\bruin|"
                       r"\bwast(?:e|ed|ing)\b|\bagain and again\b|\bsoaked\b|\bstuck\b|\bcost you\b", re.I)
PROBLEM = re.compile(r"\bused to\b|\bblame\b|\btired of\b|\bstruggl|\bproblem\b|\bhate\b|\bsick of\b|\bwhy do\b|\bnever\b|\bcan'?t\b|"
                     r"\bdoesn'?t\b|\bdon'?t\b|\bfail|\bleak|\bworst\b|\bannoying\b|\bfrustrat|\bwish\b|"
                     r"\bmost\b.*\b(?:fail|break|let)\b", re.I)
CLAIMS = ("best", "guaranteed", "guarantee", "cure", "cures", "clinically", "#1", "number one",
          "proven", "miracle")


def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    return total


def _sentences(text: str) -> List[str]:
    out = []
    for chunk in re.split(r"\n+", text):
        chunk = chunk.strip()
        if chunk:
            out.extend(s.strip() for s in _SPLIT.split(chunk) if s.strip())
    return out


def parse_transcript(text: str) -> List[Dict[str, Any]]:
    """Return cues as {start, end, text}. Plain text gives one untimed cue per line."""
    if _CUE.search(text):
        cues = []
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
        for block in blocks:
            lines = [l for l in block.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                match = _CUE.search(line)
                if match:
                    body = " ".join(re.sub(r"<[^>]+>", "", l).strip() for l in lines[i + 1:])
                    if body:
                        cues.append({"start": _seconds(match.group(1)), "end": _seconds(match.group(2)),
                                     "text": body})
                    break
        return cues
    return [{"start": None, "end": None, "text": line.strip()}
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#") and line.strip().upper() != "WEBVTT"]


def _split_cues(cues: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per sentence; a timed cue's span is shared by word count."""
    out = []
    for cue in cues:
        parts = _sentences(cue["text"])
        words = [max(len(p.split()), 1) for p in parts]
        total = sum(words)
        cursor = cue["start"]
        for part, count in zip(parts, words):
            if cue["start"] is None:
                start = end = None
            else:
                span = (cue["end"] - cue["start"]) * count / total
                start, end = cursor, cursor + span
                cursor = end
            out.append({"start": start, "end": end, "text": part})
    return out


def _mentions(sentence: str, products: Sequence[str]) -> bool:
    return any(re.search(r"\b%s\b" % re.escape(p.strip()), sentence, re.I) for p in products if p.strip())


def _tags(sentence: str, products: Sequence[str]) -> List[str]:
    tags = []
    if CTA.search(sentence):
        tags.append("cta")
    if OFFER.search(sentence):
        tags.append("offer")
    if PROOF.search(sentence):
        tags.append("proof")
    if SOLUTION.search(sentence) or _mentions(sentence, products):
        tags.append("solution")
    if AGITATION.search(sentence):
        tags.append("agitation")
    if PROBLEM.search(sentence):
        tags.append("problem")
    return tags


def analyse(text: str, products: Sequence[str] = ()) -> Dict[str, Any]:
    """Label beats and compute timings and flags for one transcript."""
    sentences = _split_cues(parse_transcript(text))
    timed = bool(sentences) and all(s["start"] is not None for s in sentences)
    for index, sentence in enumerate(sentences):
        tags = _tags(sentence["text"], products)
        sentence["tags"] = tags
        sentence["mentions_product"] = _mentions(sentence["text"], products) or "solution" in tags
        in_hook = index == 0 or (timed and sentence["start"] < HOOK_WINDOW)
        if "cta" in tags:
            sentence["beat"] = "cta"
        elif in_hook:
            sentence["beat"] = "hook"
        else:
            sentence["beat"] = next((t for t in tags), "unlabelled")
    present = {t for s in sentences for t in s["tags"]}
    missing = [b for b in STRUCTURE if b not in present]
    product_hits = [s for s in sentences if s["mentions_product"]]
    cta_hits = [s for s in sentences if "cta" in s["tags"]]
    time_to_product = product_hits[0]["start"] if product_hits and timed else None
    time_to_cta = cta_hits[0]["start"] if cta_hits and timed else None
    words = sum(len(s["text"].split()) for s in sentences)
    duration = (sentences[-1]["end"] - sentences[0]["start"]) if timed else None
    flags: List[str] = []
    if timed and (time_to_product is None or time_to_product >= HOOK_WINDOW):
        when = "never" if time_to_product is None else "first at %.1f s" % time_to_product
        flags.append("no product in the first %g s (%s)" % (HOOK_WINDOW, when))
    if not cta_hits:
        flags.append("CTA missing")
    elif len(cta_hits) > 1:
        flags.append("more than one CTA")
    low = text.lower()
    for word in CLAIMS:
        pattern = r"(?<![\w])%s(?![\w])" % re.escape(word) if word[0].isalnum() else re.escape(word)
        if re.search(pattern, low):
            flags.append('claim needs substantiation: "%s"' % word)
    return {"timed": timed, "sentences": sentences, "missing": missing,
            "time_to_product": time_to_product, "time_to_cta": time_to_cta,
            "words": words, "duration": duration,
            "words_per_second": words / duration if duration else None, "flags": flags,
            "products": [p for p in products if p.strip()]}


def _t(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.1f s" % value


def render(result: Dict[str, Any]) -> str:
    out = ["Basis: heuristic labels from keywords and position. A first pass, not a verdict: read it and apply judgement.",
           "Timed: %s. Product words: %s." % ("yes" if result["timed"] else "no (plain text: no timings)",
                                              ", ".join(result["products"]) or "none given (weak guess from wording)"),
           ""]
    header = ["#", "start", "beat", "text"]
    rows = [[str(i + 1), _t(s["start"]), s["beat"], s["text"]] for i, s in enumerate(result["sentences"])]
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i]) for i in range(3)]
    out.append("  ".join(h.ljust(w) for h, w in zip(header[:3], widths)) + "  " + header[3])
    out += ["  ".join(c.ljust(w) for c, w in zip(r[:3], widths)) + "  " + r[3] for r in rows]
    out += ["",
            "Time to product mention: %s" % _t(result["time_to_product"]),
            "Time to first CTA: %s" % _t(result["time_to_cta"]),
            "Words per second: %s" % ("n/a (no timestamps)" if result["words_per_second"] is None
                                      else "%.1f" % result["words_per_second"]),
            "Beats not found: %s" % (", ".join(result["missing"]) or "none"),
            "Flags: %s" % ("; ".join(result["flags"]) or "none")]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Break an ad transcript into beats.")
    parser.add_argument("path", help="transcript: .txt, .srt or .vtt")
    parser.add_argument("--product", default="",
                        help="comma-separated product or brand words, used to find the first product mention")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8-sig") as handle:
        text = handle.read()
    result = analyse(text, [p for p in args.product.split(",") if p.strip()])
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
