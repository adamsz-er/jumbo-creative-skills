"""Shared helpers for the creative-review tests: run the script in a scratch directory, make fixture variants."""
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "skills" / "creative-review" / "scripts" / "review.py"
FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
FLIP_AD = "120000000021"  # a Scale ad in the fixture; with no purchases it reads Check before cutting


def run(args, cwd, script=REVIEW):
    return subprocess.run([sys.executable, "-I", str(script)] + [str(a) for a in args], cwd=str(cwd), capture_output=True, text=True)


def write_variant(path, change=None, drop_columns=(), keep_ids=None, id_offset=0):
    """Copy the Acme CSV with edits: `change(row)` per row, columns removed, only some ads kept, ad ids shifted."""
    with open(FIXTURE, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        names = [n for n in reader.fieldnames if n not in drop_columns]
        rows = list(reader)
    out = []
    for row in rows:
        if keep_ids is not None and row["Ad ID"] not in keep_ids:
            continue
        if change:
            change(row)
        if id_offset:
            row["Ad ID"] = str(int(row["Ad ID"]) + id_offset)
        out.append({n: row[n] for n in names})
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(out)
    return Path(path)


def flip_scale_ad(row):
    if row["Ad ID"] == FLIP_AD:
        row["Purchases"] = "0"
        row["Purchases conversion value"] = "0"


def make_repo_copy(destination, leave_out=()):
    """A copy of skills/ and shared/ without some skills, to show a missing sibling."""
    shutil.copytree(ROOT / "skills", Path(destination) / "skills",
                    ignore=shutil.ignore_patterns("__pycache__", *leave_out))
    return Path(destination) / "skills" / "creative-review" / "scripts" / "review.py"


class Scratch:
    """A temp directory that cleans itself up with the test case."""

    def __init__(self, case):
        self._tmp = tempfile.TemporaryDirectory()
        case.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name)
