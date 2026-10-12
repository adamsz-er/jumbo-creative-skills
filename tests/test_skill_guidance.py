"""The answer guidance a skill gives its agent, where a sandbox QA pass found the agent going wrong.

Each test pins the instruction that removes one cause: the wording is the fix, so the wording is what is checked.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def read(*parts):
    return (SKILLS.joinpath(*parts)).read_text(encoding="utf-8")


class SalePlannerMarketTest(unittest.TestCase):
    """The market comes from the profile, then the data, then the user; until then no regulator is named."""

    def test_the_market_is_resolved_before_any_rule_set_applies(self):
        text = read("sale-planner", "SKILL.md")
        step = re.search(r"^3\. (.+)$", text.split("## Before you start")[1], re.M).group(1)
        self.assertIn("\"Markets or regions\"", step)
        self.assertIn("currency", step)
        self.assertIn("market-neutral", step)
        self.assertIn("name no regulator", step)
        self.assertNotIn("**My market is not Australia.**", text)

    def test_consumer_law_holds_us_and_australian_sources(self):
        text = read("sale-planner", "references", "consumer-law.md")
        intro = text.split("## ")[0]
        self.assertIn("most markets", intro)
        self.assertNotIn("They follow the Australian Competition and Consumer Commission", intro)
        self.assertIn("https://www.govinfo.gov/content/pkg/CFR-2024-title16-vol1/pdf/CFR-2024-title16-vol1-part233.pdf", text)
        self.assertIn("https://www.ftc.gov/legal-library/browse/rules/guide-concerning-use-word-free-similar-representations", text)
        self.assertIn("https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business", text)
        self.assertIn("accc.gov.au", text)

    def test_the_calendar_has_a_us_section_and_says_each_is_an_example(self):
        text = read("sale-planner", "references", "sale-calendar.md")
        self.assertIn("## United States", text)
        self.assertIn("Thanksgiving | The fourth Thursday in November", text)
        self.assertIn("examples", text.split("## Australia")[0])


class OneVerdictWordTest(unittest.TestCase):
    def test_answers_use_refresh_and_reconcile_with_the_fatigue_plan(self):
        keep = read("keep-or-kill", "SKILL.md")
        self.assertIn("keep, refresh queued", keep)
        self.assertIn("never recount or paraphrase them", keep)
        self.assertIn("Refresh, not the id `iterate`", keep)
        self.assertIn("never the ids (`iterate`)", read("creative-review", "SKILL.md"))
        for path in sorted(SKILLS.glob("*/SKILL.md")) + sorted(SKILLS.glob("*/references/*.md")):
            if "siblings" not in path.parts:
                self.assertNotIn("Iterate", path.read_text(encoding="utf-8"), path)



class QuoteTheScriptTest(unittest.TestCase):
    """Counts come from the script's output, never from a hand count of a list."""

    def test_grader_quotes_its_counts(self):
        self.assertIn("Quote every count (ads per format, per group, per diagnosis) from the script's output",
                      read("creative-grader", "SKILL.md"))

    def test_mix_counts_ads_not_families_inside_a_format(self):
        text = read("creative-mix", "SKILL.md")
        self.assertIn("count ads, not concept families", text)
        self.assertIn("say \"concepts\" when you count families", text)


class CopyTestsHonestyTest(unittest.TestCase):
    def test_the_budget_base_names_its_ads_and_leaves_out_promos(self):
        text = read("copy-tests", "SKILL.md")
        self.assertIn("name the ads you summed", text)
        self.assertIn("leave out promo ads", text)

    def test_an_unknown_control_is_asked_for_not_invented(self):
        text = read("copy-tests", "SKILL.md")
        self.assertIn("`[your current headline]`", text)
        self.assertIn("never invent the control", text)


class HookWriterFormatTest(unittest.TestCase):
    def test_each_source_ad_is_named_with_its_own_format(self):
        self.assertIn("with the format the evidence prints for it", read("hook-writer", "SKILL.md"))


class IdeationWordsTest(unittest.TestCase):
    def test_proven_is_reserved_and_no_unrun_test_is_cited(self):
        text = read("creative-ideation", "SKILL.md")
        self.assertIn("Say \"proven\" only for a concept over creative-mix's proven-spend bar", text)
        self.assertIn("Never cite the result of a test that has not run", text)

if __name__ == "__main__":
    unittest.main()
