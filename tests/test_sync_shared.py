import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import sync_shared  # noqa: E402


class SyncSharedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "shared").mkdir()
        (self.root / "shared" / "creative_metrics.py").write_text("VERSION = 1\n")
        (self.root / "shared" / "from_mcp.py").write_text("VERSION = 1\n")
        other = self.root / "skills" / "other-skill" / "scripts"
        other.mkdir(parents=True)
        (other / "creative_metrics.py").write_text("VERSION = 1\n")
        (self.root / "skills" / "no-script-skill").mkdir()

    def test_check_reports_missing_creative_context_copy(self):
        drifted = sync_shared.sync(self.root, check=True)
        self.assertEqual(sorted((p.parts[-3], p.name) for p in drifted),
                         [("creative-context", "creative_metrics.py"), ("creative-context", "from_mcp.py"),
                          ("other-skill", "from_mcp.py")])

    def test_sync_writes_copies_then_check_is_clean(self):
        sync_shared.sync(self.root)
        copy = self.root / "skills" / "creative-context" / "scripts" / "creative_metrics.py"
        self.assertEqual(copy.read_text(), "VERSION = 1\n")
        self.assertEqual(sync_shared.sync(self.root, check=True), [])

    def test_check_detects_drift_and_leaves_files_alone(self):
        sync_shared.sync(self.root)
        drifted_file = self.root / "skills" / "other-skill" / "scripts" / "creative_metrics.py"
        drifted_file.write_text("VERSION = 2\n")
        drifted = sync_shared.sync(self.root, check=True)
        self.assertEqual(drifted, [drifted_file])
        self.assertEqual(drifted_file.read_text(), "VERSION = 2\n")

    def test_skill_without_a_script_copy_is_not_given_one(self):
        sync_shared.sync(self.root)
        self.assertFalse((self.root / "skills" / "no-script-skill" / "scripts").exists())

    def test_cli_check_exit_codes(self):
        script = str(ROOT / "tools" / "sync_shared.py")
        sync_shared.sync(self.root)
        clean = subprocess.run([sys.executable, script, "--check", "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0, clean.stdout)
        (self.root / "shared" / "creative_metrics.py").write_text("VERSION = 3\n")
        dirty = subprocess.run([sys.executable, script, "--check", "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(dirty.returncode, 1)
        self.assertIn("out of sync", dirty.stdout)

    def test_a_missing_demo_source_fails_the_check_when_the_skill_is_present(self):
        (self.root / "skills" / "creative-review").mkdir()
        copy = self.root / "skills" / "creative-review" / "assets" / "demo" / "ads_daily.csv"
        self.assertIn(copy, sync_shared.sync(self.root, check=True))
        sync_shared.sync(self.root)
        self.assertIn(copy, sync_shared.sync(self.root, check=True))

    def test_demo_csv_is_copied_and_drift_is_caught(self):
        (self.root / "examples" / "acme").mkdir(parents=True)
        (self.root / "examples" / "acme" / "ads_daily.csv").write_text("a,b\n1,2\n")
        copy = self.root / "skills" / "creative-review" / "assets" / "demo" / "ads_daily.csv"
        self.assertIn(copy, sync_shared.sync(self.root, check=True))
        sync_shared.sync(self.root)
        self.assertEqual(copy.read_text(), "a,b\n1,2\n")
        self.assertEqual(sync_shared.sync(self.root, check=True), [])
        copy.write_text("drifted\n")
        self.assertEqual(sync_shared.sync(self.root, check=True), [copy])

    def make_sibling(self):
        sibling = self.root / "skills" / "keep-or-kill"
        (sibling / "scripts").mkdir(parents=True)
        (sibling / "SKILL.md").write_text("---\nname: keep-or-kill\n---\n")
        (sibling / "scripts" / "verdicts.py").write_text("VERDICTS = 1\n")
        (sibling / "scripts" / "creative_metrics.py").write_text("VERSION = 0\n")
        (sibling / "references").mkdir()
        (sibling / "references" / "rules.md").write_text("rules\n")
        (self.root / "skills" / "creative-review" / "scripts").mkdir(parents=True)
        (self.root / "examples" / "acme").mkdir(parents=True)
        (self.root / "examples" / "acme" / "ads_daily.csv").write_text("a,b\n1,2\n")
        return self.root / "skills" / "creative-review" / "siblings" / "keep-or-kill"

    def test_siblings_are_bundled_into_creative_review_without_their_skill_md(self):
        bundled = self.make_sibling()
        sync_shared.sync(self.root)
        self.assertEqual((bundled / "scripts" / "verdicts.py").read_text(), "VERDICTS = 1\n")
        self.assertEqual((bundled / "references" / "rules.md").read_text(), "rules\n")
        self.assertFalse((bundled / "SKILL.md").exists())
        self.assertEqual((bundled / "scripts" / "creative_metrics.py").read_text(), "VERSION = 1\n")
        self.assertEqual(sync_shared.sync(self.root, check=True), [])

    def test_a_drifted_or_stale_bundled_file_fails_the_check_and_sync_repairs_it(self):
        bundled = self.make_sibling()
        sync_shared.sync(self.root)
        (bundled / "scripts" / "verdicts.py").write_text("edited in the bundle\n")
        stale = bundled / "scripts" / "removed_upstream.py"
        stale.write_text("old\n")
        self.assertEqual(sorted(sync_shared.sync(self.root, check=True)), sorted([bundled / "scripts" / "verdicts.py", stale]))
        self.assertTrue(stale.exists())
        sync_shared.sync(self.root)
        self.assertFalse(stale.exists())
        self.assertEqual(sync_shared.sync(self.root, check=True), [])

    def test_real_repo_is_in_sync(self):
        self.assertEqual(sync_shared.sync(ROOT, check=True), [])


if __name__ == "__main__":
    unittest.main()
