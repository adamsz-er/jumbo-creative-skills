"""creative-review ends with the two or three skills its own findings point to, chosen by fixed rules."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "creative-review" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import next_steps  # noqa: E402

SKILLS = {p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file()}


def ad(verdict_id, fatiguing=False):
    return {"ad": verdict_id, "verdict_id": verdict_id, "fatiguing": fatiguing}


def skills(verdicts=None, mix=None):
    return [s["skill"] for s in next_steps.next_steps(verdicts, mix)]


class RuleTest(unittest.TestCase):
    def test_every_rule_names_a_real_skill(self):
        for skill, _ in tuple(next_steps.RULES) + tuple(next_steps.FILL):
            self.assertIn(skill, SKILLS)

    def test_unread_names_point_to_the_namer_first(self):
        self.assertEqual(skills({"ads": [ad("scale")]}, {"concepts_unread": True})[0], "ad-namer")

    def test_a_site_check_points_to_funnel_diagnosis(self):
        self.assertEqual(skills({"ads": [ad("check_site")]})[0], "funnel-diagnosis")

    def test_a_pause_with_a_weak_page_points_to_funnel_diagnosis(self):
        paused = dict(ad("pause_fatigued", fatiguing=True), funnel={"weak_steps": ["ctr", "landing_page_view_rate"]})
        self.assertEqual(skills({"ads": [paused]})[0], "funnel-diagnosis")

    def test_a_pause_with_only_weak_attention_steps_does_not(self):
        paused = dict(ad("pause_fatigued"), funnel={"weak_steps": ["ctr"]})
        self.assertNotIn("funnel-diagnosis", skills({"ads": [paused]}))

    def test_a_fatiguing_ad_points_to_the_planner(self):
        self.assertIn("fatigue-planner", skills({"ads": [ad("iterate", fatiguing=True)]}))

    def test_pause_and_scale_point_to_spend_with_both_counts(self):
        steps = next_steps.next_steps({"ads": [ad("pause_never_worked"), ad("scale"), ad("scale")]}, {})
        spend = next(s for s in steps if s["skill"] == "spend-analysis")
        self.assertIn("1 ad judged pause", spend["why"])
        self.assertIn("2 ads earned a scale call", spend["why"])

    def test_mix_gaps_point_to_ideation_with_the_first_gap(self):
        steps = next_steps.next_steps({}, {"gaps": [{"concept": "trail-test", "format": "carousel"}]})
        self.assertEqual(steps[0]["skill"], "creative-ideation")
        self.assertIn("trail-test as a carousel", steps[0]["why"])

    def test_iterate_points_to_hooks(self):
        self.assertIn("hook-writer", skills({"ads": [ad("iterate")]}))

    def test_at_most_three_in_priority_order(self):
        verdicts = {"ads": [ad("check_site"), ad("iterate", fatiguing=True), ad("pause_fatigued"), ad("scale")]}
        self.assertEqual(skills(verdicts, {"gaps": [{"concept": "a", "format": "b"}]}),
                         ["funnel-diagnosis", "fatigue-planner", "spend-analysis"])

    def test_nothing_found_still_gives_two_useful_steps(self):
        self.assertEqual(skills({"ads": [ad("keep")]}, {"gaps": []}), ["creative-ideation", "creative-brief"])

    def test_one_finding_is_topped_up_to_two_without_repeating(self):
        self.assertEqual(skills({}, {"gaps": [{"concept": "a", "format": "b"}]}), ["creative-ideation", "creative-brief"])

    def test_render_numbers_the_steps_and_never_starts_a_line_with_a_bullet(self):
        text = next_steps.render(next_steps.next_steps({"ads": [ad("scale")]}, {}))
        self.assertTrue(text.startswith("Next steps:\n  1. spend-analysis: "))
        self.assertFalse(any(line.startswith("- ") for line in text.splitlines()))


class ReviewSummaryTest(unittest.TestCase):
    def test_demo_review_ends_with_next_steps_and_keeps_three_bullets(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, "-I", str(SCRIPTS / "review.py"), "run", "--demo", "--cache-dir", tmp],
                                  capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len([l for l in done.stdout.splitlines() if l.startswith("- ")]), 3)
        tail = done.stdout.split("Next steps:", 1)[1]
        self.assertIn("1. fatigue-planner:", tail)
        self.assertEqual(len([l for l in tail.splitlines() if l.strip()[:2] in ("1.", "2.", "3.")]), 3)


if __name__ == "__main__":
    unittest.main()
