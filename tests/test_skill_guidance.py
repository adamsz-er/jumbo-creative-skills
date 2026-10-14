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

    def test_the_market_never_comes_from_the_signed_in_account(self):
        step = re.search(r"^3\. (.+)$", read("sale-planner", "SKILL.md").split("## Before you start")[1], re.M).group(1)
        self.assertIn("signed-in account's email", step)

    def test_consumer_law_holds_us_and_australian_sources(self):
        text = read("sale-planner", "references", "consumer-law.md")
        intro = text.split("## ")[0]
        self.assertIn("most markets", intro)
        self.assertNotIn("They follow the Australian Competition and Consumer Commission", intro)
        self.assertIn("https://www.govinfo.gov/content/pkg/CFR-2024-title16-vol1/pdf/CFR-2024-title16-vol1-part233.pdf", text)
        self.assertIn("https://www.ftc.gov/legal-library/browse/rules/guide-concerning-use-word-free-similar-representations", text)
        self.assertIn("https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business", text)
        self.assertIn("accc.gov.au", text)

    def test_the_rules_say_they_are_not_legal_advice_and_paraphrase_the_us_test_fairly(self):
        law = read("sale-planner", "references", "consumer-law.md")
        self.assertIn("not legal advice", law.split("## ")[0])
        self.assertIn("not legal advice", read("sale-planner", "SKILL.md"))
        self.assertIn("reasonably substantial period", law)
        self.assertNotIn("sets the same test", law)

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
        self.assertIn("Never count the per-ad `verdict_id` values", read("creative-review", "SKILL.md"))

    def test_no_reader_sees_the_word_iterate_as_a_verdict(self):
        # The id `iterate` may stay in code and data; prose a person reads says Refresh. Backticked ids are allowed.
        paths = (sorted(SKILLS.glob("*/SKILL.md")) + sorted(SKILLS.glob("*/references/*.md"))
                 + sorted((ROOT / "docs").glob("*.md")) + [ROOT / "README.md", ROOT / "CHANGELOG.md"])
        for path in paths:
            if "siblings" in path.parts:
                continue
            text = re.sub(r"`[^`]*`", "", path.read_text(encoding="utf-8"))
            self.assertIsNone(re.search(r"\biterate\b", text, re.I), path)

    def test_the_worked_examples_show_refresh_too(self):
        # In the page and data files the id lives in classes, CSS variables, data attributes and quoted JSON values; strip those.
        ids = re.compile(r'`[^`]*`|class="[^"]*"|data-[\w-]+="[^"]*"|--v-iterate[\w-]*|\.(cr-v-)?iterate\b|"iterate"|\\"iterate\\"')
        examples = ROOT / "examples" / "acme"
        dashboard = examples / "claude-dashboard"
        paths = (sorted(examples.glob("*.md")) + [examples / "report.html", dashboard / "manifest.json"]
                 + sorted((dashboard / "datasets").glob("*.json")))
        for path in paths:
            text = ids.sub("", path.read_text(encoding="utf-8"))
            found = re.search(r".{0,40}\biterate\b.{0,40}", text, re.I)
            self.assertIsNone(found, (path, found and found.group(0)))


class AngleWordsTest(unittest.TestCase):
    def test_every_angle_list_names_the_weakest_in_its_format_bucket(self):
        self.assertIn("weakest in their format", read("persona-builder", "SKILL.md").split("then the angles")[1].split(".")[0])
        how = (ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8")
        self.assertEqual(2, len(re.findall(r"weakest in (?:its|their) format", how)))


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
        self.assertIn("Say \"proven\" only for a winning concept over creative-mix's proven-spend bar", text)
        self.assertIn("Never cite the result of a test that has not run", text)


class TranscriptClaimsTest(unittest.TestCase):
    def test_new_claims_in_a_rewrite_are_flagged_and_experiences_are_never_written(self):
        text = read("ad-transcript", "SKILL.md")
        self.assertIn("new: needs sign-off", text)
        self.assertIn("`[creator's own experience]`", text)
        self.assertIn("invented testimonial", text)
        self.assertNotIn("first-person experience (\"my old jacket let the rain in\") is a new claim", text)


class FatiguePlannerLateFlagTest(unittest.TestCase):
    """The answer marks as many calendar rows late as the script counts."""

    def test_the_answer_leads_with_the_data_window_and_never_starts_on_today_for_old_data(self):
        text = read("fatigue-planner", "SKILL.md")
        self.assertIn("1. Lead with the data window and ad count", text.split("## Present the result")[1])
        self.assertIn("Never pass today's date for older data.", text.split("## Before you start")[1])

    def test_every_shown_row_keeps_the_scripts_late_flag(self):
        text = read("fatigue-planner", "SKILL.md").split("## Present the result")[1]
        self.assertIn("Copy the script's late flag onto every calendar row you show", text)


if __name__ == "__main__":
    unittest.main()
