import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "creative-context" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import research_check  # noqa: E402

SCRIPT = SCRIPTS / "research_check.py"
SITE = "https://acme-outdoor.example/"
REV = "https://reviews.example/acme"

CLEAN = f"""# Acme Outdoor Co. profile

## Seeded from public research

### Claims
- Tents are built for wet weather [from the brand's site] ({SITE}tents)

### Proof points
- Reviewers say the poles survive wind [from public reviews] ({REV})

### Tone
- Plain and practical [inferred] (based on: the site's product pages)

## Other
- not checked
"""


def draft(body):
    return ("## Seeded from public research\n\n" + body).splitlines()


def rules(lines):
    return [(p["line"], p["rule"]) for p in research_check.check(lines)["problems"]]


def run(path, *flags):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), str(path), *flags],
                          capture_output=True, text=True)


class ResearchCheckTest(unittest.TestCase):
    def test_clean_draft_has_exact_counts(self):
        report = research_check.check(CLEAN.splitlines())
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["counts"], {"bullets": 3, "from_site": 1, "from_reviews": 1,
                                            "inferred": 1, "problems": 0})
        self.assertEqual(research_check.summary(report["counts"]),
                         "3 bullets checked: 1 from the brand's site, 1 from public reviews, 1 inferred; 0 problems")

    def test_missing_section(self):
        self.assertEqual(rules(["# Profile", "- text"]), [(1, "missing-section")])

    def test_unknown_topic(self):
        found = rules(draft(f"### Slogans\n- x [from the brand's site] ({SITE})"))
        self.assertEqual(found, [(3, "unknown-topic")])

    def test_unlabelled(self):
        self.assertEqual(rules(draft("### Claims\n- Waterproof tents")), [(4, "unlabelled")])

    def test_no_source(self):
        body = ("### Claims\n- a [from the brand's site]\n- b [from public reviews] (not a link)\n"
                "- c [inferred] (https://acme-outdoor.example/)\n- d [inferred]")
        self.assertEqual(rules(draft(body)), [(4, "no-source"), (5, "no-source"),
                                              (6, "no-source"), (7, "no-source")])

    def test_quoted_review_straight_curly_and_single(self):
        body = ("### Proof points\n"
                f'- They said "great poles" [from public reviews] ({REV})\n'
                f"- They said “great poles” [from public reviews] ({REV})\n"
                f"- They said 'great poles every time' [from public reviews] ({REV})\n"
                f"- The brand's poles hold [from public reviews] ({REV})")
        self.assertEqual(rules(draft(body)), [(4, "quoted-review"), (5, "quoted-review"),
                                              (6, "quoted-review")])

    def test_review_number(self):
        body = ("### Proof points\n"
                f"- Rated highly [from public reviews] ({REV})\n"
                f"- Praised by 90% of buyers [from public reviews] ({REV})\n"
                f"- A 4.5 star average [from public reviews] ({REV})\n"
                f"- 9 out of 10 recommend it [from public reviews] ({REV})")
        self.assertEqual(rules(draft(body)), [(5, "review-number"), (6, "review-number"),
                                              (7, "review-number")])

    def test_invented_figure(self):
        body = "### Tone\n- Used by 9 in 18 hikers [inferred] (based on: the blog)\n- Calm [inferred] (based on: copy)"
        self.assertEqual(rules(draft(body)), [(4, "invented-figure")])

    def test_same_domain(self):
        body = ("### Claims\n"
                f"- a [from the brand's site] ({SITE}a)\n- b [from the brand's site] ({SITE}b)\n"
                f"- c [from the brand's site] (https://other.example/c)\n"
                f"- d [from public reviews] ({SITE}reviews)\n- e [from public reviews] ({REV})")
        self.assertEqual(rules(draft(body)), [(7, "same-domain")])

    def test_same_domain_needs_a_site_url(self):
        self.assertEqual(rules(draft(f"### Claims\n- d [from public reviews] ({SITE}reviews)")), [])

    def test_empty_topic(self):
        body = "### Claims\n\n### Tone\n- Calm [inferred] (based on: copy)"
        self.assertEqual(rules(draft(body)), [(3, "empty-topic")])

    def test_nothing_found_is_allowed(self):
        body = "### Objections\n- nothing found [inferred] (based on: search returned nothing)"
        report = research_check.check(draft(body))
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["counts"]["inferred"], 1)

    def test_trailing_period_after_url(self):
        for tail in (f"({SITE}tents).", f"({SITE}tents.)"):
            report = research_check.check(draft(f"### Claims\n- a [from the brand's site] {tail}"))
            self.assertEqual(report["problems"], [])
            self.assertEqual(report["bullets"][0]["source"], SITE + "tents")

    def test_a_clean_check_says_it_does_not_prove_a_paraphrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.md"
            good.write_text(CLEAN, encoding="utf-8")
            ok = run(good)
            self.assertEqual(ok.returncode, 0)
            self.assertIn("does not prove a bullet is a paraphrase of its source", ok.stdout)
            self.assertIn("a human still reads it", json.loads(run(good, "--json").stdout)["limit"])

    def test_cli_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "good.md", Path(tmp) / "bad.md"
            good.write_text(CLEAN, encoding="utf-8")
            bad.write_text("## Seeded from public research\n### Claims\n- plain claim\n", encoding="utf-8")
            ok, fail, gone = run(good), run(bad), run(Path(tmp) / "none.md")
            self.assertEqual(ok.returncode, 0)
            self.assertIn("3 bullets checked", ok.stdout)
            self.assertEqual(fail.returncode, 1)
            self.assertIn("bad.md:3: unlabelled:", fail.stdout)
            self.assertEqual(gone.returncode, 2)
            self.assertIn("Cannot read", gone.stderr)
            self.assertNotIn("Traceback", gone.stderr)
            data = json.loads(run(bad, "--json").stdout)
            self.assertEqual(data["problems"][0]["rule"], "unlabelled")
            self.assertEqual(data["counts"]["problems"], 1)
            self.assertIn("settings", data)


if __name__ == "__main__":
    unittest.main()
