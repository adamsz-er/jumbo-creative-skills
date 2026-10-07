import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "build_zips.py"
ALL_ZIP = "jumbo-creative-skills-all.zip"


def run_build(root, out):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), "--out", str(out)],
                          capture_output=True, text=True)


class BuildZipsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "dist"
        cls.result = run_build(ROOT, cls.out)
        cls.skills = sorted(p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_build_succeeds_and_reports_each_zip(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        for name in self.skills + ["jumbo-creative-skills-all"]:
            self.assertIn(name + ".zip", self.result.stdout)

    def test_every_skill_gets_a_zip_plus_the_bundle(self):
        built = sorted(p.name for p in self.out.glob("*.zip"))
        self.assertEqual(built, sorted([s + ".zip" for s in self.skills] + [ALL_ZIP]))

    def test_top_level_dir_is_the_skill_name_and_holds_skill_md(self):
        for skill in self.skills:
            with zipfile.ZipFile(self.out / (skill + ".zip")) as z:
                names = z.namelist()
            self.assertEqual({n.split("/")[0] for n in names}, {skill})
            self.assertIn(skill + "/SKILL.md", names)

    def test_zip_carries_everything_in_the_skill_folder(self):
        skill = "creative-grader"
        expected = sorted(skill + "/" + p.relative_to(ROOT / "skills" / skill).as_posix()
                          for p in (ROOT / "skills" / skill).rglob("*")
                          if p.is_file() and "__pycache__" not in p.parts)
        with zipfile.ZipFile(self.out / (skill + ".zip")) as z:
            self.assertEqual(sorted(z.namelist()), expected)
        self.assertTrue(any(n.endswith("scripts/grade.py") for n in expected))

    def test_bundle_holds_every_skill(self):
        with zipfile.ZipFile(self.out / ALL_ZIP) as z:
            tops = {n.split("/")[0] for n in z.namelist()}
        self.assertEqual(tops, set(self.skills))

    def test_no_cache_files(self):
        for path in self.out.glob("*.zip"):
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    self.assertNotIn("__pycache__", name)
                    self.assertFalse(name.endswith((".pyc", ".DS_Store")), name)

    def test_cache_files_in_the_tree_are_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(ROOT / "skills" / "creative-grader", root / "skills" / "creative-grader")
            junk = root / "skills" / "creative-grader" / "scripts" / "__pycache__"
            junk.mkdir(exist_ok=True)
            (junk / "x.cpython-311.pyc").write_bytes(b"x")
            (root / "skills" / "creative-grader" / ".DS_Store").write_bytes(b"x")
            result = run_build(root, Path(tmp) / "dist")
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(Path(tmp) / "dist" / "creative-grader.zip") as z:
                self.assertFalse([n for n in z.namelist() if "__pycache__" in n or n.endswith(".DS_Store")])

    def test_symlinks_are_not_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(ROOT / "skills" / "creative-grader", root / "skills" / "creative-grader")
            outside = Path(tmp) / "secret.txt"
            outside.write_text("outside the skill")
            (root / "skills" / "creative-grader" / "link.txt").symlink_to(outside)
            result = run_build(root, Path(tmp) / "dist")
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(Path(tmp) / "dist" / "creative-grader.zip") as z:
                self.assertNotIn("creative-grader/link.txt", z.namelist())
                self.assertIn("creative-grader/SKILL.md", z.namelist())

    def test_two_builds_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            second = Path(tmp) / "dist"
            self.assertEqual(run_build(ROOT, second).returncode, 0)
            for path in sorted(self.out.glob("*.zip")):
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes(), path.name)

    def test_timestamps_are_fixed(self):
        with zipfile.ZipFile(self.out / "creative-grader.zip") as z:
            self.assertEqual({i.date_time for i in z.infolist()}, {(1980, 1, 1, 0, 0, 0)})

    def test_invalid_skill_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(ROOT / "skills" / "creative-grader", root / "skills" / "creative-grader")
            skill_md = root / "skills" / "creative-grader" / "SKILL.md"
            text = skill_md.read_text(encoding="utf-8").replace("\n---\n", "\nbogus-key: nope\n---\n", 1)
            skill_md.write_text(text, encoding="utf-8")
            result = run_build(root, Path(tmp) / "dist")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("bogus-key", result.stdout + result.stderr)
            self.assertFalse(list((Path(tmp) / "dist").glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
