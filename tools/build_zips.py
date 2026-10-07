#!/usr/bin/env python3
"""Build one zip per skill, plus one bundle of all skills.

Usage: python3 tools/build_zips.py [--out dist]

Each skills/<name>/ becomes <out>/<name>.zip with a single top-level folder
<name>/ holding SKILL.md and everything beside it, ready for Claude desktop or
claude.ai (Customize > Skills > Upload). <out>/jumbo-creative-skills-all.zip
holds every skill folder. Entries are sorted and carry a fixed timestamp, so the
same tree always gives the same bytes. Every skill is validated first; one
invalid skill stops the build before anything is written.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_skills  # noqa: E402

BUNDLE = "jumbo-creative-skills-all"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
SKIP_NAMES = {".DS_Store"}
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = (".pyc",)


def skill_files(skill_dir):
    """Every file under a skill folder worth shipping, in sorted order."""
    files = []
    base = skill_dir.resolve()
    for path in skill_dir.rglob("*"):
        rel = path.relative_to(skill_dir)
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            continue
        if not path.is_file() or path.name in SKIP_NAMES or path.name.endswith(SKIP_SUFFIXES):
            continue
        if SKIP_DIRS.intersection(rel.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(skill_dir).as_posix())


def _write_zip(target, skill_dirs):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        count = 0
        for skill_dir in skill_dirs:
            for path in skill_files(skill_dir):
                info = zipfile.ZipInfo(skill_dir.name + "/" + path.relative_to(skill_dir).as_posix(), FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
                archive.writestr(info, path.read_bytes())
                count += 1
    return count


def build(root, out):
    """Write the zips; return a list of (path, bytes, file count)."""
    root, out = Path(root), Path(out)
    errors = validate_skills.validate_all(root)
    if errors:
        raise ValueError("\n".join(errors))
    skill_dirs = sorted(p.parent for p in (root / "skills").glob("*/SKILL.md"))
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for name, dirs in [(d.name, [d]) for d in skill_dirs] + [(BUNDLE, skill_dirs)]:
        target = out / (name + ".zip")
        count = _write_zip(target, dirs)
        built.append((target, target.stat().st_size, count))
    return built


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", default="dist")
    args = parser.parse_args(argv)
    try:
        built = build(args.root, args.out)
    except ValueError as error:
        print("refusing to build, invalid skill(s):\n%s" % error, file=sys.stderr)
        return 1
    for path, size, count in built:
        print("%s  %d bytes  %d files" % (path.name, size, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
