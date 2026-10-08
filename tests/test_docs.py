"""The docs cannot drift from the package: skills named, questions mirrored, links resolved, flags listed."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "creative-review" / "scripts"))

import errors  # noqa: E402

SKILLS = sorted(p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())
README = ROOT / "README.md"
HOW = ROOT / "docs" / "how-it-works.md"
FAQ = ROOT / "docs" / "faq.md"
TROUBLE = ROOT / "docs" / "troubleshooting.md"
AGENT_FAQ = ROOT / "skills" / "creative-context" / "references" / "faq.md"

README_HEADINGS = [
    "What you get", "Install", "Quick start", "How it fits together", "Which skill do I use?",
    "A typical workflow", "Connect your ad data", "What the numbers mean", "Known limits", "Learn more",
    "Privacy", "Updating", "Contributing", "License",
]
FAQ_GROUPS = [
    "Getting started", "Data and connections", "Metrics and grading", "Decisions", "Making creative",
    "The report", "Privacy and safety", "Installing and updating",
]
REQUIRED_QUESTIONS = [
    "Do I need the Meta MCP?", "Why is hook rate missing or marked derived?",
    "Why don't you tell me what a good hook rate is?", "Why does an ad say too early to judge?",
    "Can I use this for TikTok or Google?", "Does my data leave my machine?",
    "What if my ad names don't follow a convention?", "Can I change the thresholds?",
    "Why was my pull reconciled", "How do I update?", "Can I use it in ChatGPT?",
]


def read(path):
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def questions(path):
    found = []
    for line in read(path).splitlines():
        if line.startswith("### "):
            found.append(line[4:].strip())
        elif line.startswith("**Q"):
            found.append(re.sub(r"^\*\*Q\d*[.:]?\s*", "", line).rstrip("*").strip())
    return found


def headings(text, level):
    prefix = "#" * level + " "
    return [line[len(prefix):].strip() for line in text.splitlines() if line.startswith(prefix)]


def flags_in(path):
    text = path.read_text(encoding="utf-8")
    found = set()
    for call in re.finditer(r"add_argument\(\s*((?:\"[^\"]*\"\s*,\s*)+)", text):
        found.update(re.findall(r"\"(--[a-z][a-z0-9-]*)\"", call.group(1)))
    return found


def script_flags():
    """(script file name, flag), each synced module once from shared/, then every other skill script."""
    shared = {p.name for p in (ROOT / "shared").glob("*.py")}
    pairs = {(path.name, flag) for path in (ROOT / "shared").glob("*.py") for flag in flags_in(path)}
    for path in sorted((ROOT / "skills").glob("*/scripts/*.py")):
        if path.name not in shared:
            pairs.update((path.name, flag) for flag in flags_in(path))
    return pairs


class ReadmeTests(unittest.TestCase):
    def test_mermaid_block_names_every_skill(self):
        text = read(README)
        match = re.search(r"```mermaid\n(.*?)```", text, re.S)
        self.assertIsNotNone(match, "README.md has no mermaid block")
        self.assertEqual(len(SKILLS), 12)
        missing = [name for name in SKILLS if name not in match.group(1)]
        self.assertEqual(missing, [], "skills missing from the diagram")

    def test_section_headings(self):
        have = headings(read(README), 2)
        self.assertEqual([h for h in README_HEADINGS if h not in have], [])

    def test_every_skill_has_a_row_in_the_which_skill_table(self):
        text = read(README)
        section = text.split("## Which skill do I use?", 1)[-1].split("\n## ", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(rows), 14)
        for name in SKILLS:
            self.assertTrue(any("`%s`" % name in row for row in rows), name)

    def test_workflow_chain_is_numbered(self):
        section = read(README).split("## A typical workflow", 1)[-1].split("\n## ", 1)[0]
        self.assertGreaterEqual(len(re.findall(r"^\d+\. ", section, re.M)), 4)


class FaqTests(unittest.TestCase):
    def test_at_least_twenty_questions(self):
        self.assertGreaterEqual(len(questions(FAQ)), 20)

    def test_groups_present(self):
        have = headings(read(FAQ), 2)
        self.assertEqual([g for g in FAQ_GROUPS if g not in have], [])

    def test_required_questions_present(self):
        qs = questions(FAQ)
        for needle in REQUIRED_QUESTIONS:
            self.assertTrue(any(needle in q for q in qs), needle)

    def test_agent_faq_questions_are_in_the_human_faq(self):
        agent, human = questions(AGENT_FAQ), set(questions(FAQ))
        self.assertGreaterEqual(len(agent), 20)
        self.assertEqual([q for q in agent if q not in human], [])

    def test_agent_faq_is_shorter(self):
        self.assertLess(len(read(AGENT_FAQ)), len(read(FAQ)))


class TroubleshootingTests(unittest.TestCase):
    def rows(self):
        return [l for l in read(TROUBLE).splitlines() if l.startswith("|") and not set(l) <= set("|- ")]

    def test_at_least_twelve_rows(self):
        self.assertGreaterEqual(len(self.rows()) - 1, 12)

    def test_every_error_code_and_fix_is_listed(self):
        text = read(TROUBLE)
        for code in errors.TABLE:
            self.assertIn(code, text)

    def test_named_symptoms(self):
        text = read(TROUBLE).lower()
        for needle in ["pillow", "/reload-plugins", "npx", "authenticat", "unclassified", "low volume", "fonts"]:
            self.assertIn(needle, text)


class SkillSectionTests(unittest.TestCase):
    def test_every_skill_has_how_to_use_and_common_questions(self):
        for name in SKILLS:
            text = read(ROOT / "skills" / name / "SKILL.md")
            lines = text.splitlines()
            self.assertIn("## How to use", lines, name)
            self.assertIn("## Common questions", lines, name)
            self.assertLess(len(lines), 500, name)
            self.assertIn("references/faq.md", text.split("## Common questions", 1)[-1], name)

    def test_frontmatter_untouched_by_the_sections(self):
        for name in SKILLS:
            head = read(ROOT / "skills" / name / "SKILL.md").split("---", 2)[1]
            keys = set(re.findall(r"^([a-z-]+):", head, re.M))
            self.assertLessEqual(keys, {"name", "description", "license", "metadata", "version", "role", "compatibility"}, name)


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        for path in [README] + sorted((ROOT / "docs").glob("*.md")):
            for target in re.findall(r"\]\(([^)\s]+)\)", read(path)):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                file_part = target.split("#", 1)[0]
                self.assertTrue((path.parent / file_part).exists(), "%s -> %s" % (path.name, target))


class FlagTableTests(unittest.TestCase):
    def test_every_flag_is_in_the_table(self):
        rows = [l for l in read(HOW).splitlines() if l.startswith("|")]
        self.assertTrue(rows, "no table in how-it-works.md")
        missing = [(script, flag) for script, flag in sorted(script_flags())
                   if not any("`%s`" % script in row and "`%s`" % flag in row for row in rows)]
        self.assertEqual(missing, [])

    def test_synced_copies_have_the_same_flags_as_shared(self):
        for shared in sorted((ROOT / "shared").glob("*.py")):
            for copy in sorted((ROOT / "skills").glob("*/scripts/" + shared.name)):
                self.assertEqual(flags_in(copy), flags_in(shared), str(copy.relative_to(ROOT)))

    def test_table_says_defaults_are_arbitrary(self):
        text = read(HOW).lower()
        self.assertIn("arbitrary", text)
        self.assertIn("your own account", text)


if __name__ == "__main__":
    unittest.main()
