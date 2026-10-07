#!/usr/bin/env python3
"""Copy shared/creative_metrics.py into each skill that carries its own copy.

Every skill must run on its own after install, so the module is duplicated into
skills/<name>/scripts/. A skill gets a copy if it already has one, and
creative-context always does. `--check` copies nothing and exits 1 on drift.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MODULE = "creative_metrics.py"
ALWAYS = ("creative-context",)


def targets(root):
    root = Path(root)
    found = {root / "skills" / name / "scripts" / MODULE for name in ALWAYS}
    found.update((root / "skills").glob("*/scripts/" + MODULE))
    return sorted(found)


def sync(root, check=False):
    """Return the copies that differ from shared/; write them unless check is set."""
    root = Path(root)
    source = root / "shared" / MODULE
    canonical = source.read_bytes()
    drifted = []
    for target in targets(root):
        if not target.exists() or target.read_bytes() != canonical:
            drifted.append(target)
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    return drifted


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if any copy differs from shared/")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    drifted = sync(args.root, check=args.check)
    verb = "out of sync" if args.check else "updated"
    for path in drifted:
        print("%s: %s" % (verb, path))
    if args.check and drifted:
        print("run: python3 tools/sync_shared.py")
        return 1
    if not drifted:
        print("OK: all copies match shared/%s" % MODULE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
