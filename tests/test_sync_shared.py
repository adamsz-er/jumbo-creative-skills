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
        other = self.root / "skills" / "other-skill" / "scripts"
        other.mkdir(parents=True)
        (other / "creative_metrics.py").write_text("VERSION = 1\n")
        (self.root / "skills" / "no-script-skill").mkdir()

    def test_check_reports_missing_creative_context_copy(self):
        drifted = sync_shared.sync(self.root, check=True)
        self.assertEqual([p.parts[-3] for p in drifted], ["creative-context"])

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

    def test_real_repo_is_in_sync(self):
        self.assertEqual(sync_shared.sync(ROOT, check=True), [])


if __name__ == "__main__":
    unittest.main()
