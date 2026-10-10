#!/usr/bin/env python3
"""Copy the shared modules into each skill that carries its own copy.

Every skill must run on its own after install, so shared/creative_metrics.py and
shared/from_mcp.py are duplicated into skills/<name>/scripts/, and the Acme example CSV
into creative-review's demo folder. A skill gets the
copies if it already has creative_metrics.py, and creative-context always does.
shared/evidence.py goes to the skills in EVIDENCE (the make skills that read account evidence).
`--check` copies nothing and exits 1 on drift.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MODULE = "creative_metrics.py"
MODULES = (MODULE, "from_mcp.py")
ALWAYS = ("creative-context",)
EVIDENCE_MODULE = "evidence.py"
EVIDENCE = ("creative-brief", "creative-ideation", "hook-writer", "persona-builder")
DEMO = (Path("examples/acme/ads_daily.csv"), Path("skills/creative-review/assets/demo/ads_daily.csv"))


def targets(root):
    """(source, copy) pairs: the shared modules for each skill that carries them, and the demo CSV."""
    root = Path(root)
    scripts = {root / "skills" / name / "scripts" for name in ALWAYS}
    scripts.update(root / "skills" / name / "scripts" for name in EVIDENCE if (root / "skills" / name).is_dir())
    scripts.update(p.parent for p in (root / "skills").glob("*/scripts/" + MODULE))
    pairs = [(root / "shared" / module, folder / module) for folder in sorted(scripts) for module in MODULES]
    pairs += [(root / "shared" / EVIDENCE_MODULE, root / "skills" / name / "scripts" / EVIDENCE_MODULE)
              for name in EVIDENCE if (root / "skills" / name).is_dir()]
    if (root / "skills" / "creative-review").is_dir() or (root / DEMO[0]).exists():
        pairs.append((root / DEMO[0], root / DEMO[1]))
    return sorted(pairs, key=lambda pair: pair[1])


def sync(root, check=False):
    """Return the copies that differ from shared/; write them unless check is set."""
    root = Path(root)
    drifted = []
    for source, target in targets(root):
        if not source.exists():
            drifted.append(target)
            continue
        if not target.exists() or target.read_bytes() != source.read_bytes():
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
        print("OK: all copies match shared/ (%s) and the demo CSV" % ", ".join(MODULES + (EVIDENCE_MODULE,)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
