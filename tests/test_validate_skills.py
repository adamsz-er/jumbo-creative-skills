import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_skills  # noqa: E402

GOOD = """---
name: demo-skill
description: Use when you need a demo of a valid skill.
license: MIT
---
# Demo

Body.
"""


class ValidateSkillsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, dirname, text):
        folder = self.root / "skills" / dirname
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "SKILL.md"
        path.write_text(text)
        return path

    def errors(self, dirname, text):
        return validate_skills.validate_skill(self.write(dirname, text))

    def test_valid_skill_passes(self):
        self.assertEqual(self.errors("demo-skill", GOOD), [])

    def test_extra_frontmatter_key_rejected(self):
        errs = self.errors("demo-skill", GOOD.replace("license: MIT", "license: MIT\nwhen_to_use: always"))
        self.assertTrue(any("when_to_use" in e for e in errs), errs)
        self.assertTrue(all(":" in e for e in errs))

    def test_name_must_match_directory(self):
        errs = self.errors("other-dir", GOOD)
        self.assertTrue(any("does not match directory" in e for e in errs), errs)

    def test_description_too_long_rejected(self):
        errs = self.errors("demo-skill", GOOD.replace("Use when you need a demo of a valid skill.", "x" * 1025))
        self.assertTrue(any("description" in e and "1024" in e for e in errs), errs)

    def test_body_over_499_lines_rejected(self):
        errs = self.errors("demo-skill", GOOD + "line\n" * 500)
        self.assertTrue(any("500" in e for e in errs), errs)

    def test_bad_name_rejected(self):
        errs = self.errors("Demo_Skill", GOOD.replace("demo-skill", "Demo_Skill"))
        self.assertTrue(any("name" in e for e in errs), errs)

    def test_missing_frontmatter_rejected(self):
        self.assertTrue(self.errors("demo-skill", "# no frontmatter\n"))

    def test_cli_exits_one_on_failure_and_zero_on_clean_tree(self):
        script = ROOT / "tools" / "validate_skills.py"
        self.write("demo-skill", GOOD)
        ok = subprocess.run([sys.executable, str(script), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.write("bad-skill", GOOD.replace("demo-skill", "bad-skill").replace("license: MIT", "license: MIT\nextra: 1"))
        bad = subprocess.run([sys.executable, str(script), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("SKILL.md:", bad.stdout + bad.stderr)

    def test_real_repo_skills_pass(self):
        self.assertEqual(validate_skills.validate_all(ROOT), [])


if __name__ == "__main__":
    unittest.main()
