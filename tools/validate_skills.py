#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md against the open Agent Skills spec.

Checks frontmatter keys, name rules, name == directory, description length
and body length.
Exits 1 and prints file:line for each problem.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME, MAX_DESCRIPTION, MAX_BODY_LINES = 64, 1024, 500


def _parse_frontmatter(lines):
    """Return (keys, values, body_start_index) or None when there is no frontmatter."""
    if not lines or lines[0].strip() != "---":
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            keys, values, current = [], {}, None
            for line in lines[1:end]:
                match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
                if match and not line.startswith((" ", "\t")):
                    current = match.group(1)
                    keys.append(current)
                    values[current] = match.group(2).strip().strip("\"'")
                elif current and line.strip():
                    values[current] = (values[current] + " " + line.strip()).strip()
            return keys, values, end + 1
    return None


def validate_skill(skill_md):
    """Return a list of "file:line: problem" strings for one SKILL.md and its folder."""
    skill_md = Path(skill_md)
    errors = []
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    parsed = _parse_frontmatter(lines)
    if parsed is None:
        errors.append("%s:1: missing frontmatter (--- block at top of file)" % skill_md)
    else:
        keys, values, body_start = parsed
        for key in keys:
            if key not in ALLOWED_KEYS:
                line = next(i for i, text in enumerate(lines, 1) if text.startswith(key + ":"))
                errors.append("%s:%d: frontmatter key %r is not in the spec (allowed: %s)"
                              % (skill_md, line, key, ", ".join(sorted(ALLOWED_KEYS))))
        name = values.get("name", "")
        if not name:
            errors.append("%s:1: frontmatter is missing name" % skill_md)
        else:
            if len(name) > MAX_NAME or not NAME_RE.match(name):
                errors.append("%s:1: name %r must be lowercase letters, digits and single hyphens, at most %d chars"
                              % (skill_md, name, MAX_NAME))
            if name != skill_md.parent.name:
                errors.append("%s:1: name %r does not match directory %r" % (skill_md, name, skill_md.parent.name))
        description = values.get("description", "")
        if not description:
            errors.append("%s:1: frontmatter is missing description" % skill_md)
        elif len(description) > MAX_DESCRIPTION:
            errors.append("%s:1: description is %d chars, limit is %d" % (skill_md, len(description), MAX_DESCRIPTION))
        body_lines = len(lines) - body_start
        if body_lines >= MAX_BODY_LINES:
            errors.append("%s:1: body is %d lines, must be under %d" % (skill_md, body_lines, MAX_BODY_LINES))
    return errors


def validate_all(root):
    """Validate every skills/*/SKILL.md under root."""
    root = Path(root)
    errors = []
    for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
        errors.extend(validate_skill(skill_md))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    errors = validate_all(args.root)
    for error in errors:
        print(error)
    if errors:
        return 1
    count = len(list((Path(args.root) / "skills").glob("*/SKILL.md")))
    print("OK: %d skill(s) valid" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
