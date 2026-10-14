import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "copy-tests" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import copy_check  # noqa: E402

SCRIPT = str(SCRIPTS / "copy_check.py")
LIMITS = copy_check.parse_limits(copy_check.DEFAULT_LIMITS)


def variant(name, test="t1", persona="hikers", hook="question", primary="Boots that last the whole trail",
            headline="Built for wet trails", description="", changed=""):
    rows = []
    for field, text in (("primary_text", primary), ("headline", headline), ("description", description)):
        if text:
            rows.append({"test": test, "variant": name, "persona": persona, "hook": hook, "field": field,
                         "text": text, "changed": changed})
    return rows


def good_test():
    return variant("control") + variant("b", headline="Dry feet, long miles", changed="headline")


def findings(rows, limits=LIMITS, rule=None, status=None):
    found = copy_check.check_variants(rows, limits)
    return [f for f in found if (rule is None or f["rule"] == rule) and (status is None or f["status"] == status)]


def messages(rows, **kwargs):
    return [f["message"] for f in findings(rows, **kwargs)]


def write(directory, rows):
    path = Path(directory) / "variants.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(copy_check.COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def run(*args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True)


class RuleTest(unittest.TestCase):
    def test_clean_test_has_no_failures(self):
        self.assertEqual(findings(good_test(), status="fail"), [])

    def test_two_changes_name_both(self):
        rows = variant("control") + variant("b", headline="Dry feet, long miles",
                                            primary="Stay dry on every trail", changed="headline")
        (fail,) = findings(rows, rule="one-variable", status="fail")
        self.assertIn("changes 2 things", fail["message"])
        self.assertIn("primary_text", fail["message"])
        self.assertIn("headline", fail["message"])
        self.assertIn("could not say which one mattered", fail["message"])

    def test_identical_variant_tests_nothing(self):
        rows = variant("control") + variant("b", changed="headline")
        self.assertEqual(messages(rows, rule="one-variable", status="fail"), ["same as control: tests nothing"])

    def test_changed_column_must_name_the_difference(self):
        rows = variant("control") + variant("b", headline="Dry feet, long miles", changed="hook")
        self.assertEqual(messages(rows, rule="one-variable", status="fail"),
                         ["changed column says hook but headline differs"])

    def test_persona_change_counts_as_the_one_variable(self):
        rows = variant("control") + variant("b", persona="families", changed="persona")
        self.assertEqual(findings(rows, rule="one-variable", status="fail"), [])

    def test_primary_text_151_characters_is_over_by_one(self):
        rows = variant("control", primary="a" * 151) + variant("b", primary="b" * 100, changed="primary_text")
        fails = findings(rows, rule="length-limit", status="fail")
        self.assertEqual(len(fails), 1)
        self.assertIn("over by 1 characters", fails[0]["message"])
        self.assertIn("Meta's guidance, not a rule of this package", fails[0]["message"])
        self.assertEqual(findings(variant("control", primary="a" * 150) + variant("b", headline="x", changed="headline"),
                                  rule="length-limit", status="fail"), [])

    def test_headline_27_passes_28_fails(self):
        ok = variant("control", headline="h" * 27) + variant("b", primary="p" * 60, headline="h" * 27, changed="primary_text")
        bad = variant("control", headline="h" * 28) + variant("b", primary="p" * 60, headline="h" * 28, changed="primary_text")
        self.assertEqual(findings(ok, rule="length-limit", status="fail"), [])
        self.assertEqual(len(findings(bad, rule="length-limit", status="fail")), 2)

    def test_length_counts_after_strip(self):
        rows = variant("control", headline="  " + "h" * 27 + "  ") + variant("b", headline="x", changed="headline")
        with tempfile.TemporaryDirectory() as tmp:
            read = copy_check.read_variants(write(tmp, rows))
        self.assertEqual(findings(read, rule="length-limit", status="fail"), [])

    def test_short_primary_text_passes(self):
        rows = variant("control", primary="Short") + variant("b", headline="x", changed="headline")
        self.assertIn("5 of 150 characters", messages(rows, rule="length-limit", status="pass"))
        self.assertEqual(findings(rows, rule="length-limit", status="fail"), [])

    def test_description_has_no_guidance_by_default(self):
        rows = variant("control", description="d" * 200) + variant("b", headline="x", description="d" * 200, changed="headline")
        self.assertIn(copy_check.NO_GUIDANCE, messages(rows, rule="length-limit", status="note"))
        self.assertEqual(findings(rows, rule="length-limit", status="fail"), [])

    def test_description_limit_when_passed(self):
        limits = copy_check.parse_limits("description=18")
        ok = variant("control", description="d" * 18) + variant("b", description="d" * 18, headline="x", changed="headline")
        bad = variant("control", description="d" * 19) + variant("b", description="d" * 19, headline="x", changed="headline")
        self.assertEqual(findings(ok, limits, rule="length-limit", status="fail"), [])
        self.assertIn("over by 1 characters", findings(bad, limits, rule="length-limit", status="fail")[0]["message"])

    def test_missing_persona_or_hook(self):
        rows = variant("control") + variant("b", persona="", hook="", headline="Dry feet, long miles", changed="headline")
        fails = findings(rows, rule="persona-and-hook", status="fail")
        self.assertTrue(fails)
        self.assertIn("tie the variant to a persona and a hook", fails[0]["message"])
        self.assertIn("persona and hook", fails[0]["message"])

    def test_missing_control(self):
        rows = variant("a") + variant("b", headline="Dry feet, long miles", changed="headline")
        self.assertIn("no control variant", messages(rows, rule="control", status="fail")[0])

    def test_only_a_control(self):
        self.assertEqual(messages(variant("control"), rule="control", status="fail"), ["no variant to test"])

    def test_tests_are_checked_separately(self):
        rows = good_test() + variant("control", test="t2") + variant("b", test="t2", changed="headline")
        fails = findings(rows, status="fail")
        self.assertEqual({f["test"] for f in fails}, {"t2"})

    def test_parse_limits_rejects_junk(self):
        for bad in ("headline", "headline=x", "caption=9"):
            with self.assertRaises(ValueError):
                copy_check.parse_limits(bad)


class RowShapeTest(unittest.TestCase):
    def read_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "variants.csv"
            path.write_text(text, encoding="utf-8")
            return copy_check.read_variants(str(path))

    HEADER = "test,variant,persona,hook,field,text,changed\n"

    def test_a_row_with_more_fields_than_the_header_names_its_line(self):
        text = self.HEADER + "t1,control,p,h,headline,Dry feet,\nt1,b,p,h,headline,Tested in a creek, an hour,headline\n"
        with self.assertRaisesRegex(ValueError, "line 3 has more fields than the header"):
            self.read_text(text)

    def test_the_same_text_quoted_is_read(self):
        text = self.HEADER + 't1,b,p,h,headline,"Tested in a creek, an hour",headline\n'
        self.assertEqual(self.read_text(text)[0]["text"], "Tested in a creek, an hour")

    def test_an_unknown_changed_value_names_its_line(self):
        text = self.HEADER + "t1,control,p,h,headline,Dry feet,\nt1,b,p,h,headline,Wet feet,colour\n"
        with self.assertRaisesRegex(ValueError, "line 3: changed must be empty or one of .*not 'colour'"):
            self.read_text(text)


class CliTest(unittest.TestCase):
    def test_exit_zero_when_every_check_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run(write(tmp, good_test()))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Every check passed.", done.stdout)

    def test_exit_one_prints_failures_first(self):
        rows = variant("control", description="Free returns") + variant("b", description="Free returns", changed="headline")
        with tempfile.TemporaryDirectory() as tmp:
            done = run(write(tmp, rows))
        self.assertEqual(done.returncode, 1)
        self.assertIn("same as control: tests nothing", done.stdout)
        self.assertTrue(done.stdout.startswith("1 check(s) failed."))
        self.assertLess(done.stdout.index("Failures:"), done.stdout.index("Notes:"))

    def test_json_output(self):
        rows = variant("control") + variant("b", changed="headline")
        with tempfile.TemporaryDirectory() as tmp:
            done = run(write(tmp, rows), "--json", "--limits", "headline=18")
        result = json.loads(done.stdout)
        self.assertFalse(result["passed"])
        self.assertEqual(result["settings"]["limits"], {"headline": 18})

    def test_exit_two_on_unreadable_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.csv"
            empty.write_text("test,variant,persona,hook,field,text,changed\n")
            nocol = Path(tmp) / "nocol.csv"
            nocol.write_text("test,variant\nt,a\n")
            cases = [[str(Path(tmp) / "nope.csv")], [str(empty)], [str(nocol)],
                     [write(tmp, good_test()), "--limits", "headline"]]
            codes = [run(*c) for c in cases]
        for done in codes:
            self.assertEqual(done.returncode, 2)
            self.assertNotIn("Traceback", done.stderr)

    def test_unknown_field_exits_two(self):
        rows = variant("control")
        rows[0]["field"] = "caption"
        with tempfile.TemporaryDirectory() as tmp:
            done = run(write(tmp, rows))
        self.assertEqual(done.returncode, 2)
        self.assertIn("field must be one of", done.stderr)


if __name__ == "__main__":
    unittest.main()
