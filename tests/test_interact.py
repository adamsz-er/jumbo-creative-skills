import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
ASSETS = ROOT / "skills" / "creative-report" / "assets"
sys.path.insert(0, str(SCRIPT))

import creative_metrics as cm  # noqa: E402
import interact  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
PUBLIC_VERDICTS = {"scale", "keep", "iterate", "check", "pause", "too-early", "cant-judge"}
HAS_NODE = shutil.which("node") is not None


def run_json(skill, script, path=FIXTURE):
    out = subprocess.run([sys.executable, str(ROOT / "skills" / skill / "scripts" / script), str(path), "--json"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def record(ad_id, spend, **extra):
    base = {"id": str(ad_id), "label": "ad %s" % ad_id, "name": "ad %s" % ad_id, "verdict": None, "verdict_id": None, "confidence": None,
            "format": None, "ad_type": None, "concept": None, "market": None, "funnel_stage": None, "creator": None, "objective": None,
            "spend": float(spend), "conversions": None, "conversion_value": None, "impressions": None, "link_clicks": None, "clicks": None,
            "video_views_3s": None, "video_thruplay": None, "fatiguing": None, "age_days": None, "stake": float(spend), "weak": None}
    base.update(extra)
    return base


def page_data(html):
    block = re.search(r'<script type="application/json" id="ad-data">(.*?)</script>', html, re.S)
    assert block, "no ad-data block"
    return block.group(1), json.loads(block.group(1))


def node_run(html, body):
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.js"
        path.write_text("var module = {exports: {}};\n" + script + "\nvar CR = module.exports;\n" + body)
        done = subprocess.run(["node", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = run_json("keep-or-kill", "verdicts.py")
        cls.grade = run_json("creative-grader", "grade.py")
        cls.html = report.build_html(rows=cls.rows, verdicts=cls.verdicts, grade=cls.grade, currency="USD", title="Acme")
        cls.ctx = panels.Ctx(rows=cls.rows, verdicts=cls.verdicts, grade=cls.grade, currency="USD")


class LogoTest(Fixture):
    def lockup_spans(self, region, label):
        return re.findall(r'<span class="logo-(light|dark)" role="img" aria-label="%s">(.*?)</span>' % label, region, re.S)

    def test_header_and_footer_each_carry_both_brands_in_both_variants(self):
        header = re.search(r'<header class="top">.*?</header>', self.html, re.S).group(0)
        footer = re.search(r"<footer>.*?</footer>", self.html, re.S).group(0)
        for region in (header, footer):
            for label in ("Jumbo", "Elephant Room"):
                self.assertEqual(sorted(v for v, _ in self.lockup_spans(region, label)), ["dark", "light"], label)
        self.assertLess(header.index('aria-label="Jumbo"'), header.index('aria-label="Elephant Room"'))
        self.assertIn("by", re.search(r'<span class="brand-by">(.*?)</span>', header).group(1))

    def test_the_dark_variant_swaps_the_two_gradient_stops(self):
        header = re.search(r'<header class="top">.*?</header>', self.html, re.S).group(0)
        spans = dict(self.lockup_spans(header, "Jumbo"))
        self.assertIn("#1A00FF", spans["light"])
        self.assertIn("#8F62F9", spans["light"])
        self.assertNotIn("#C4B5FD", spans["light"])
        self.assertIn("#C4B5FD", spans["dark"])
        self.assertIn("#8F62F9", spans["dark"])
        self.assertNotIn("#1A00FF", spans["dark"])

    def test_asset_files_are_the_same_drawing_with_only_the_stops_changed(self):
        light = (ASSETS / "jumbo-logo.svg").read_text()
        dark = (ASSETS / "jumbo-logo-dark.svg").read_text()
        self.assertEqual(light.replace("#8F62F9", "@@").replace("#1A00FF", "#8F62F9").replace("@@", "#C4B5FD"), dark)

    def test_no_gradient_or_clip_id_repeats_anywhere_in_the_page(self):
        ids = re.findall(r'<(?:linearGradient|clipPath) id="([^"]+)"', self.html)
        self.assertEqual(len(re.findall(r"<linearGradient id=", self.html)), 4)
        self.assertEqual(len(ids), len(set(ids)))
        for gradient in re.findall(r'fill="url\(#([^)]+)\)"', self.html):
            self.assertEqual(self.html.count('id="%s"' % gradient), 1, gradient)

    def test_logo_heights_are_28px_in_the_header_and_20px_in_the_footer(self):
        self.assertRegex(self.html, r"\.brand svg \{[^}]*height: 28px")
        self.assertRegex(self.html, r"footer \.by svg \{[^}]*height: 20px")


class PayloadTest(Fixture):
    def test_every_ad_is_in_the_payload_with_the_card_id_and_label(self):
        _, data = page_data(self.html)
        ids = [a["id"] for a in data["ads"]]
        self.assertEqual(len(ids), len(self.verdicts["ads"]))
        self.assertEqual(set(ids), {e["ad"] for e in self.verdicts["ads"]})
        first = next(a for a in data["ads"] if a["id"] == "120000000001")
        self.assertEqual(first["label"], "durability-test · creator-01 · UGC video · BAU")
        self.assertEqual(first["spend"], 9061.59)
        self.assertEqual(first["weak"], "hook")
        self.assertEqual(first["verdict"], "iterate")
        self.assertIs(first["fatiguing"], True)

    def test_money_is_rounded_so_float_sums_cannot_differ_by_python_version(self):
        ten_tenths = 0.0
        for _ in range(10):
            ten_tenths += 0.1
        self.assertNotEqual(ten_tenths, 1.0)
        recs = interact.ad_records([{"ad_id": "x", "ad_name": "x", "spend": ten_tenths, "conversion_value": ten_tenths,
                                     "conversions": 3}], None, None)
        self.assertEqual(recs[0]["spend"], 1.0)
        self.assertEqual(recs[0]["conversion_value"], 1.0)
        self.assertIsInstance(recs[0]["conversions"], int)
        _, data = page_data(report.build_html(rows=[{"ad_id": "x", "ad_name": "x", "spend": ten_tenths}], verdicts=None, currency="USD", title="T"))
        self.assertEqual(data["ads"][0]["spend"], 1.0)
        sub = interact.totals_of(recs + recs, None)
        self.assertEqual(sub["spend"], 2.0)
        self.assertEqual(interact.totals_of([{"spend": 1.0, "conversion_value": 1.0 / 3}], None)["roas"], 0.3333)
        near = interact.totals_of([{"spend": 10000.0, "conversion_value": 28749.7}], None)
        self.assertEqual(near["roas"], 2.875)
        self.assertEqual(near["roas_text"], "2.87x")

    def test_unknowns_are_null_never_zero(self):
        _, data = page_data(self.html)
        first = data["ads"][0]
        for key in ("market", "funnel_stage", "objective"):
            self.assertIsNone(first[key], key)
        rows = [{"ad_id": "1", "ad_name": "a | static | c | bau | p | t | 2026-03-01", "date": "2026-03-01", "spend": 5.0, "impressions": 5000.0}]
        _, bare = page_data(report.build_html(rows=rows))
        ad = bare["ads"][0]
        for key in ("conversions", "conversion_value", "link_clicks", "video_views_3s", "video_thruplay", "fatiguing", "weak", "confidence", "verdict"):
            self.assertIsNone(ad[key], key)

    def test_data_cannot_close_the_script_tag_and_parses_back(self):
        nasty = "</script><script>alert(1)</script> & > <b>"
        rows = [{"ad_id": "7", "ad_name": nasty, "date": "2026-03-01", "spend": 5.0, "impressions": 5000.0}]
        html = report.build_html(rows=rows)
        raw, data = page_data(html)
        for char in "<>&":
            self.assertNotIn(char, raw)
        self.assertEqual(data["ads"][0]["name"], nasty)
        self.assertNotIn("<script>alert(1)", html)
        self.assertEqual(html.count('id="ad-data"'), 1)

    def test_no_internal_word_for_the_pause_verdict_reaches_the_payload_or_a_link(self):
        raw, data = page_data(self.html)
        self.assertLessEqual({a["verdict"] for a in data["ads"] if a["verdict"]}, PUBLIC_VERDICTS)
        self.assertNotIn('"kill"', raw)
        self.assertNotRegex(json.dumps(data["presets"]), r"kill")
        chips = re.findall(r'data-value="([^"]+)"', self.html)
        self.assertTrue(chips)
        self.assertNotIn("kill", chips)

    def test_the_payload_is_the_only_data_the_script_reads(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        self.assertIn('getElementById("ad-data")', script)
        self.assertIn("JSON.parse", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)


class FacetTest(unittest.TestCase):
    def ads(self, values):
        return [record(i, 100 - i, format=v) for i, v in enumerate(values)]

    def keys(self, records):
        return [f["key"] for f in interact.facets(records)]

    def test_a_facet_needs_two_values(self):
        self.assertNotIn("format", self.keys(self.ads(["static"] * 10)))
        self.assertIn("format", self.keys(self.ads(["static"] * 5 + ["video"] * 5)))

    def test_a_facet_needs_three_in_five_ads_known(self):
        five = ["static", "video", None, None, None]
        self.assertNotIn("format", self.keys(self.ads(five)))
        self.assertIn("format", self.keys(self.ads(["static", "video", "static", None, None])))
        self.assertNotIn("format", self.keys(self.ads(["static", "video"] + [None] * 8)))
        self.assertIn("format", self.keys(self.ads(["static", "video"] * 3 + [None] * 4)))

    def test_values_are_sorted_by_spend_and_carry_their_ad_count(self):
        recs = [record(1, 5, format="carousel"), record(2, 50, format="static"), record(3, 60, format="static"), record(4, 20, format="video")]
        facet = next(f for f in interact.facets(recs) if f["key"] == "format")
        self.assertEqual([(v["value"], v["count"]) for v in facet["values"]], [("static", 2), ("video", 1), ("carousel", 1)])

    def test_verdict_values_carry_the_board_label_and_the_public_id(self):
        recs = [record(1, 5, verdict="pause"), record(2, 9, verdict="too-early"), record(3, 4, verdict="cant-judge")]
        facet = next(f for f in interact.facets(recs) if f["key"] == "verdict")
        self.assertEqual({v["value"]: v["label"] for v in facet["values"]}, {"pause": "Pause", "too-early": "Too early", "cant-judge": "Can't judge"})

    def test_all_nine_facets_are_the_ones_named(self):
        self.assertEqual([k for k, _ in interact.FACETS],
                         ["verdict", "confidence", "format", "ad_type", "concept", "market", "funnel_stage", "creator", "objective"])


class PresetTest(unittest.TestCase):
    def test_the_five_smart_views(self):
        presets = {p["id"]: p for p in interact.PRESETS}
        self.assertEqual([p["label"] for p in interact.PRESETS],
                         ["Money at risk", "Ready to scale", "Tiring out", "Can't judge yet", "Biggest spenders"])
        self.assertEqual(presets["money"]["filters"], {"verdict": ["pause", "check"]})
        self.assertEqual(presets["money"]["sort"], "stake")
        self.assertEqual(presets["scale"]["filters"], {"verdict": ["scale"]})
        self.assertIs(presets["tiring"]["fatiguing"], True)
        self.assertEqual(presets["cant"]["filters"], {"verdict": ["cant-judge", "too-early"]})
        self.assertEqual(presets["spenders"]["top"], interact.BIGGEST_N)
        self.assertIn(str(interact.BIGGEST_N), presets["spenders"]["note"])

    def test_the_default_n_avoids_the_round_numbers(self):
        self.assertNotIn(interact.BIGGEST_N, (4, 10, 12, 14, 15, 20, 25, 30, 50))


class SubtotalTest(unittest.TestCase):
    def test_roas_and_cpa_are_ratios_of_sums_not_averages_of_ratios(self):
        recs = [record(1, 100, verdict="keep", conversions=10.0, conversion_value=300.0),
                record(2, 300, verdict="keep", conversions=5.0, conversion_value=300.0)]
        (group,) = interact.group_subtotals(recs, "verdict")
        self.assertEqual((group["ads"], group["spend"]), (2, 400.0))
        self.assertAlmostEqual(group["roas"], 600 / 400)
        self.assertEqual(group["cpa"], round(400 / 15, 2))
        self.assertAlmostEqual(group["share"], 100.0)

    def test_share_is_of_the_whole_account_and_groups_follow_the_board_order(self):
        recs = [record(1, 100, verdict="pause"), record(2, 300, verdict="scale"), record(3, 100, verdict=None)]
        groups = interact.group_subtotals(recs, "verdict")
        self.assertEqual([g["key"] for g in groups], ["scale", "pause", None])
        self.assertAlmostEqual(groups[0]["share"], 60.0)

    def test_a_missing_operand_reads_na_not_zero(self):
        (group,) = interact.group_subtotals([record(1, 100, verdict="keep")], "verdict")
        self.assertIsNone(group["roas"])
        self.assertIsNone(group["cpa"])
        self.assertEqual(group["roas_text"], "n/a (missing purchase value)")
        self.assertEqual(group["cpa_text"], "n/a (missing purchases)")
        (zero,) = interact.group_subtotals([record(1, 0, verdict="keep", conversions=2.0, conversion_value=5.0)], "verdict")
        self.assertEqual(zero["roas_text"], "n/a (zero spend)")

    def test_other_group_keys_sort_by_spend_and_put_unknown_last(self):
        recs = [record(1, 10, format="static"), record(2, 90, format="video"), record(3, 500)]
        self.assertEqual([g["key"] for g in interact.group_subtotals(recs, "format")], ["video", "static", None])


class ImprovementTest(unittest.TestCase):
    def grade(self, step, action, also=()):
        return {"diagnosis": {"step": step, "metrics": [], "also_weak": list(also), "action": action, "summary": step}}

    def test_each_weak_step_leads_with_the_verdict_step_then_the_fix_then_also_weak(self):
        for step in ("hook", "hold", "click", "post-click", "reach cost", "pays back"):
            text = interact.improvement(self.grade(step, "FIX FOR " + step, ["hold_rate", "ctr"]), {"verdict_id": "iterate"})
            self.assertEqual(text["lead"], panels.NEXT_STEP["iterate"], step)
            self.assertEqual(text["fix"], "FIX FOR " + step, step)
            self.assertEqual(text["also"], "Also weak: hold rate, CTR.")
            self.assertTrue(text["has_data"])

    def test_the_templates_are_plain_and_carry_no_numbers(self):
        self.assertEqual(set(interact.STEP_FIX), {"hook", "hold", "click", "post-click", "reach cost", "pays back"})
        for step, line in list(interact.STEP_FIX.items()) + list(interact.STEP_WORDS.items()):
            self.assertNotRegex(line, r"\d", step)

    def test_a_missing_action_falls_back_to_the_step_template(self):
        grade = {"diagnosis": {"step": "hold", "metrics": ["hold_rate"], "also_weak": []}}
        self.assertEqual(interact.improvement(grade, None)["fix"], interact.STEP_FIX["hold"])

    def test_no_grade_data_never_invents_a_fix(self):
        for grade in (None, {}, {"diagnosis": {"step": "not graded", "action": "Too few impressions"}}):
            text = interact.improvement(grade, {"verdict_id": "scale"})
            self.assertFalse(text["has_data"])
            self.assertIsNone(text["fix"])
            self.assertEqual(text["note"], "Not enough data to suggest a fix.")

    def test_nothing_weak_says_so(self):
        text = interact.improvement(self.grade("none", "Nothing in the funnel reads weak against this account."), None)
        self.assertTrue(text["has_data"])
        self.assertIn("Nothing", text["fix"])

    def test_the_next_version_prompt_names_the_ad_what_worked_and_what_to_change(self):
        rec = record(1, 10, label="durability-test · ugc-video", format="ugc-video", verdict="iterate", weak="hook")
        grade = {"grades": {"cvr": {"band": "top quartile"}, "hook_rate": {"band": "bottom quartile"}, "ctr": {"band": "middle"}},
                 "diagnosis": {"step": "hook", "metrics": ["hook_rate"], "also_weak": [], "action": "x"}}
        prompt = interact.next_version_prompt(rec, grade)
        for text in ("hook-writer", "creative-brief", "durability-test · ugc-video", "UGC video", "CVR", "among your best", "opening"):
            self.assertIn(text, prompt)
        self.assertNotIn("CTR", prompt.split("What worked")[1].split("What to change")[0])


class BandTest(unittest.TestCase):
    def test_bands_read_in_plain_words_with_values_and_units(self):
        grade = {"grades": {"hook_rate": {"value": 25.5, "band": "bottom quartile"}, "cpa": {"value": 30.7, "band": "top quartile"},
                            "roas": {"value": 3.39, "band": "middle"}, "cost_per_lead": {"value": None, "band": "not graded (missing leads)"}}}
        rows = {r["metric"]: r for r in interact.band_rows(grade, lambda v, d=0: "USD %.*f" % (d, v))}
        self.assertEqual(rows["hook_rate"]["band"], "among your weakest")
        self.assertEqual(rows["hook_rate"]["value"], "25.50%")
        self.assertEqual(rows["cpa"]["band"], "among your best")
        self.assertEqual(rows["cpa"]["value"], "USD 30.70")
        self.assertEqual(rows["roas"]["band"], "middle")
        self.assertEqual(rows["roas"]["value"], "3.39x")
        self.assertEqual(rows["cost_per_lead"]["band"], "not graded: missing leads")
        self.assertEqual(rows["cost_per_lead"]["value"], "n/a (missing leads)")

    def test_no_grade_gives_one_honest_row_not_an_empty_list(self):
        self.assertEqual(interact.band_rows(None, str), [])


class WaysToImproveTest(Fixture):
    def test_spend_per_step_sums_to_the_account_and_is_sorted_largest_first(self):
        html, state = panels.ways_to_improve(self.ctx)
        self.assertEqual(state, "data")
        steps = interact.weak_groups(self.ctx.records)
        total = sum(g["spend"] for g in steps)
        self.assertAlmostEqual(total, sum(r["spend"] for r in self.ctx.records))
        self.assertEqual(sum(g["ads"] for g in steps), len(self.ctx.records))
        actionable = [g for g in steps if g["step"] not in (None, "none")]
        self.assertEqual([g["spend"] for g in actionable], sorted((g["spend"] for g in actionable), reverse=True))
        self.assertIn("Show these ads", html)
        self.assertIn('data-weak="hook"', html)
        self.assertIn('href="#panel-all-ads"', html)

    def test_ads_without_a_diagnosis_are_listed_with_their_count_never_dropped(self):
        grade = json.loads(json.dumps(self.grade))
        gone = grade["ads"].pop(0)
        ctx = panels.Ctx(rows=self.rows, verdicts=self.verdicts, grade=grade, currency="USD")
        html, _ = panels.ways_to_improve(ctx)
        self.assertIn("not diagnosed (missing data)", html)
        undiagnosed = next(g for g in interact.weak_groups(ctx.records) if g["step"] is None)
        self.assertEqual(undiagnosed["ads"], 1)
        spend = next(r["spend"] for r in ctx.records if r["id"] == gone["ad"])
        self.assertAlmostEqual(undiagnosed["spend"], spend)

    def test_without_grade_output_it_is_a_labelled_empty_state(self):
        html, state = panels.ways_to_improve(panels.Ctx(rows=self.rows, verdicts=self.verdicts))
        self.assertEqual(state, "empty")
        self.assertIn("creative-grader", html)
        self.assertIn("How to get it:", html)


class StructureTest(Fixture):
    def test_the_gallery_is_the_last_panel_of_keep_kill_and_ways_follows_do_first(self):
        ids = re.findall(r'<section class="card panel" id="panel-([a-z-]+)"', self.html)
        self.assertEqual(ids, ["kpis", "time", "do-first", "improve", "funnel", "pareto", "head-tail", "board", "fatigue", "all-ads",
                               "format", "white-space", "briefing"])

    def test_with_scripts_off_the_default_grouping_is_in_the_page_and_nothing_is_hidden(self):
        gallery = re.search(r'id="panel-all-ads".*?</section>\s*</section>', self.html, re.S).group(0)
        names = re.findall(r'<section class="group" data-group="([^"]+)"', gallery)
        self.assertEqual(names, [str(g["key"] if g["key"] is not None else "unknown") for g in interact.group_subtotals(self.ctx.records, "verdict")])
        for text in ("ads", "of spend", "ROAS", "CPA"):
            self.assertIn(text, gallery)
        self.assertIn("more", gallery)
        for tag in re.findall(r"<[a-z][^>]*>", self.html.split("<main>")[1].split("</main>")[0]):
            self.assertNotRegex(tag, r"\bhidden\b")
            self.assertNotRegex(tag, r'style="[^"]*(display\s*:\s*none|visibility\s*:\s*hidden)')
        self.assertRegex(self.html, r"\.filterbar \{[^}]*display: none")
        self.assertRegex(self.html, r"\.js \.filterbar \{[^}]*display: block")

    def test_the_inline_script_is_valid_javascript(self):
        if not HAS_NODE:
            self.skipTest("node is not installed")
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script)
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_filter_chips_are_toggle_buttons_and_the_bar_is_labelled(self):
        bar = re.search(r'<div class="filterbar".*?(?=</header>)', self.html, re.S).group(0)
        self.assertIn("aria-label=", bar.split(">")[0])
        buttons = re.findall(r"<button[^>]*>", bar)
        self.assertTrue(buttons)
        chips = [b for b in buttons if 'class="chip' in b]
        self.assertTrue(chips)
        for button in chips:
            self.assertIn("aria-pressed=", button)
            self.assertIn('type="button"', button)
        self.assertIn('type="search"', bar)
        for label in ("Money at risk", "Ready to scale", "Tiring out", "Can&#x27;t judge yet", "Biggest spenders"):
            self.assertIn(label, bar)
        self.assertIn("account-wide", bar)

    def test_filter_bar_sits_in_the_sticky_header_after_the_tabs(self):
        header = re.search(r'<header class="top">.*?</header>', self.html, re.S).group(0)
        self.assertLess(header.index('<nav class="tabs"'), header.index('class="filterbar"'))

    def test_the_dialog_is_labelled_and_the_script_fills_it_from_the_details_it_mirrors(self):
        dialog = re.search(r"<dialog[^>]*>.*?</dialog>", self.html, re.S).group(0)
        labelled = re.search(r'aria-labelledby="([^"]+)"', dialog).group(1)
        self.assertIn('id="%s"' % labelled, dialog)
        self.assertIn("Close", dialog)
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        self.assertIn('.open-body', script)
        self.assertIn("cloneNode(true)", script)
        self.assertIn("showModal", script)
        self.assertIn("focus()", script)

    def test_every_card_has_an_open_this_ad_details_with_the_full_picture(self):
        html, _ = panels.verdict_board(self.ctx)
        cards = re.findall(r'<article class="ad-card" data-ad="[^"]+">.*?</article>', html, re.S)
        self.assertTrue(cards)
        for card in cards:
            self.assertEqual(card.count('<details class="open-ad">'), 1)
            self.assertIn("<summary>Open this ad</summary>", card)
            body = re.search(r'<div class="open-body">(.*)</div></details>', card, re.S).group(1)
            for text in ("Graded metrics", "Funnel for this ad", "Technical detail", "Age", "How to improve", "Confidence"):
                self.assertIn(text, body, text)
        card = next(c for c in cards if 'data-ad="120000000001"' in c)
        body = re.search(r'<div class="open-body">(.*)</div></details>', card, re.S).group(1)
        for text in ("among your weakest", "among your best", "Hook rate", "25.52%", "Impressions", "3-second plays", "Refresh it, keep the idea",
                     "29 days", "Change the first 3 seconds", "Also weak: hold rate, CTR, add-to-cart rate."):
            self.assertIn(text, body, text)
        self.assertRegex(body, r'<svg class="(pv|ph) big"')

    def test_the_preview_in_the_open_view_is_larger_than_the_card_thumbnail(self):
        self.assertRegex(self.html, r"\.open-body svg\.pv, \.open-body svg\.ph \{[^}]*max-width: 460px")

    def test_the_format_badge_sits_on_the_preview_corner(self):
        card = panels.ad_card(self.ctx, self.verdicts["ads"][0])
        self.assertRegex(card, r'<div class="ad-img"><span class="fmt-badge">UGC video</span>')

    def test_the_badge_adds_video_length_when_the_export_has_a_length_column(self):
        rows = [dict(r, **{"Video length (seconds)": "23"}) for r in self.rows]
        ctx = panels.Ctx(rows=rows, verdicts=self.verdicts, grade=self.grade, currency="USD")
        self.assertIn('<span class="fmt-badge">UGC video 0:23</span>', panels.ad_card(ctx, self.verdicts["ads"][0]))
        self.assertEqual(panels.clock(75), "1:15")

    def test_next_version_prompts_are_on_iterate_check_and_pause_cards_only(self):
        by_class = {}
        for entry in self.verdicts["ads"]:
            by_class.setdefault(panels.entry_class(entry), entry)
        for cls, entry in by_class.items():
            card = panels.ad_card(self.ctx, entry)
            has = '<pre class="prompt">' in card
            self.assertEqual(has, cls in ("iterate", "check", "kill"), cls)
            self.assertEqual("Make the next version" in card, cls in ("iterate", "check", "kill"), cls)
        card = panels.ad_card(self.ctx, by_class["iterate"])
        self.assertIn("hook-writer", card)
        self.assertIn('data-action="copy-prompt"', card)

    def test_the_gallery_has_group_sort_and_previews_only_controls(self):
        gallery = re.search(r'id="panel-all-ads".*?</section>\s*</section>', self.html, re.S).group(0)
        for text in ('data-action="group"', 'data-action="sort"', 'data-action="previews-only"', "Previews only"):
            self.assertIn(text, gallery)
        for option in ("Verdict", "Format", "Concept", "Ad type", "Creator"):
            self.assertIn(">%s<" % option, gallery)
        self.assertNotIn(">Market<", gallery)
        for option in ("Spend at stake", "ROAS", "CPA", "CTR", "Hook rate", "Age"):
            self.assertIn(option, gallery)

    def test_every_image_has_alt_text(self):
        for svg in re.findall(r"<svg[^>]*class=\"(?:pv|ph)[^\"]*\"[^>]*>", self.html):
            self.assertIn("aria-label=", svg)


class ScriptLogicTest(Fixture):
    @classmethod
    def setUpClass(cls):
        if not HAS_NODE:
            raise unittest.SkipTest("node is not installed")
        super().setUpClass()

    def test_the_browser_subtotals_match_python_for_the_default_view(self):
        _, data = page_data(self.html)
        total = sum(r["spend"] for r in self.ctx.records)
        out = node_run(self.html, "var d = JSON.parse(%s); console.log(JSON.stringify(CR.subtotals(d.ads, 'verdict', %r)));"
                       % (json.dumps(json.dumps(data)), total))
        js = json.loads(out)
        py = interact.group_subtotals(self.ctx.records, "verdict")
        self.assertEqual([g["key"] for g in js], [g["key"] for g in py])
        for a, b in zip(js, py):
            self.assertEqual(a["ads"], b["ads"])
            for field in ("spend", "share", "roas", "cpa"):
                if b[field] is None:
                    self.assertIsNone(a[field], field)
                else:
                    self.assertAlmostEqual(a[field], b[field], places={"roas": 4, "cpa": 2}.get(field, 6), msg=field)

    def test_filtering_and_hash_round_trip_use_public_ids_only(self):
        _, data = page_data(self.html)
        body = ("var d = JSON.parse(%s); var s = CR.presetState(d.presets, 'money'); var h = CR.toHash('tab-keep-kill', s);"
                "var back = CR.fromHash(h); var ids = CR.visible(d.ads, back).map(function (a) { return a.id; });"
                "console.log(JSON.stringify({hash: h, tab: back.tab, ids: ids}));" % json.dumps(json.dumps(data)))
        out = json.loads(node_run(self.html, body))
        self.assertTrue(out["hash"].startswith("tab-keep-kill?"))
        self.assertIn("verdict=pause&verdict=check", out["hash"])
        self.assertNotIn("kill", out["hash"].split("?")[1])
        self.assertEqual(out["tab"], "tab-keep-kill")
        expect = {a["id"] for a in data["ads"] if a["verdict"] in ("pause", "check")}
        self.assertEqual(set(out["ids"]), expect)

    def test_facet_counts_follow_the_other_active_facets(self):
        _, data = page_data(self.html)
        body = ("var d = JSON.parse(%s); var s = CR.emptyState(); s.facets.format = ['static'];"
                "console.log(JSON.stringify(CR.facetCount(d.ads, s, 'verdict', 'scale')));" % json.dumps(json.dumps(data)))
        got = json.loads(node_run(self.html, body))
        want = sum(1 for a in data["ads"] if a["format"] == "static" and a["verdict"] == "scale")
        self.assertEqual(got, want)

    def test_summary_uses_ratio_of_sums_and_names_missing_operands(self):
        body = ("var ads = [{spend: 100, conversions: 10, conversion_value: 300}, {spend: 300, conversions: 5, conversion_value: 300}];"
                "var one = CR.summary(ads, 4, 800); var none = CR.summary([{spend: 5, conversions: null, conversion_value: null}], 1, 5);"
                "console.log(JSON.stringify({one: one, none: none}));")
        out = json.loads(node_run(self.html, body))
        self.assertAlmostEqual(out["one"]["roas"], 1.5)
        self.assertAlmostEqual(out["one"]["cpa"], 400 / 15)
        self.assertAlmostEqual(out["one"]["share"], 50.0)
        self.assertEqual(out["none"]["roas_text"], "n/a (missing purchase value)")
        self.assertEqual(out["none"]["cpa_text"], "n/a (missing purchases)")

    def test_search_matches_label_name_and_id_case_insensitively(self):
        body = ("var ads = [{id: '99', label: 'Sunrise Story', name: 'x | y'}, {id: '5', label: 'other', name: 'Boot-Launch'}];"
                "function q(t) { var s = CR.emptyState(); s.q = t; return CR.visible(ads, s).map(function (a) { return a.id; }); }"
                "console.log(JSON.stringify([q('sunrise'), q('BOOT'), q('99'), q('zzz')]));")
        self.assertEqual(json.loads(node_run(self.html, body)), [["99"], ["5"], ["99"], []])



class TextParts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.text = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)


def two_ads():
    base = {"date": "2026-03-01", "spend": 10.0, "impressions": 10000.0}
    return [dict(base, ad_id="v", ad_name="vid | ugc-video | c | bau | p | t | 2026-03-01", video_views_3s=2500.0, video_thruplay=1000.0),
            dict(base, ad_id="s", ad_name="pic | static | c | bau | p | t | 2026-03-01")]


class ReviewScriptTest(Fixture):
    @classmethod
    def setUpClass(cls):
        if not HAS_NODE:
            raise unittest.SkipTest("node is not installed")
        super().setUpClass()

    def js(self, body):
        _, data = page_data(self.html)
        pre = "var d = JSON.parse(%s); CR.setLabels(d.verdict_labels, d.weak_steps, d.names);" % json.dumps(json.dumps(data))
        return json.loads(node_run(self.html, pre + body))

    def test_every_weak_step_round_trips_through_the_link(self):
        slugs = list(interact.STEP_SLUG.values()) + ["none", "undiagnosed"]
        got = self.js("var out = %s.map(function (w) { var s = CR.emptyState(); s.weak = w; return CR.fromHash(CR.toHash('tab-keep-kill', s)).weak; });"
                      "console.log(JSON.stringify(out));" % json.dumps(slugs))
        self.assertEqual(got, slugs)
        self.assertNotIn(" ", "".join(slugs))

    def test_an_unknown_weak_step_in_a_link_is_dropped(self):
        got = self.js("console.log(JSON.stringify(CR.fromHash('#tab-keep-kill?weak=bogus').weak));")
        self.assertIsNone(got)

    def test_facet_values_with_commas_round_trip(self):
        got = self.js("var s = CR.emptyState(); s.facets.concept = ['sale, summer', 'b']; var h = CR.toHash('t', s);"
                      "console.log(JSON.stringify({h: h, back: CR.fromHash(h).facets.concept}));")
        self.assertEqual(got["back"], ["sale, summer", "b"])
        self.assertEqual(got["h"].count("concept="), 2)

    def test_sorting_by_stake_puts_unknown_last_in_python_and_the_browser(self):
        recs = [record("a", 0, stake=0.0), record("b", 0, stake=None), record("c", 0, stake=5.0), record("d", 0, stake=3.0)]
        py = [r["id"] for r in interact.by_stake(recs)]
        js = self.js("console.log(JSON.stringify(CR.sortAds(%s, 'stake').map(function (a) { return a.id; })));" % json.dumps(recs))
        self.assertEqual(py, ["c", "d", "a", "b"])
        self.assertEqual(js, py)

    def test_an_ad_id_of_proto_is_an_ordinary_ad(self):
        ads = [record("__proto__", 5, verdict="keep", format="static"), record("x", 9, verdict="keep", format="video")]
        got = self.js("var ads = %s; var s = CR.emptyState(); s.top = 1; var ids = CR.visible(ads, s).map(function (a) { return a.id; });"
                      "var t = CR.emptyState(); t.top = 2; console.log(JSON.stringify({top1: ids, top2: CR.visible(ads, t).length,"
                      "groups: CR.groupAds(ads, 'format').length, back: CR.fromHash('#t?format=__proto__').facets.format}));" % json.dumps(ads))
        self.assertEqual(got, {"top1": ["x"], "top2": 2, "groups": 2, "back": ["__proto__"]})
        got = self.js("var ads = %s; var s = CR.emptyState(); s.top = 1; console.log(JSON.stringify(CR.visible(ads, s).length));" % json.dumps([record("__proto__", 5)]))
        self.assertEqual(got, 1)

    def test_a_partial_fixture_gives_the_same_ratios_in_python_and_the_browser(self):
        recs = [record("a", 100, verdict="keep", conversions=10.0, conversion_value=300.0),
                record("b", 100, verdict="keep", conversions=5.0, conversion_value=None),
                record("c", 100, verdict="keep", conversions=None, conversion_value=300.0)]
        py = interact.group_subtotals(recs, "verdict")[0]
        js = self.js("console.log(JSON.stringify(CR.subtotals(%s, 'verdict', 300)[0]));" % json.dumps(recs))
        for field in ("roas_text", "cpa_text", "roas_n", "cpa_n"):
            self.assertEqual(js[field], py[field], field)
        self.assertAlmostEqual(js["roas"], py["roas"], places=4)
        self.assertAlmostEqual(js["cpa"], py["cpa"], places=2)
        self.assertEqual(py["roas_text"], "3.00x (2 of 3 ads)")
        self.assertEqual(py["cpa_text"], "%.2f (2 of 3 ads)" % (200 / 15))


class ReviewPythonTest(Fixture):
    def test_the_hash_slug_for_a_weak_step_has_no_spaces_and_reaches_the_payload(self):
        grade = [{"ad": "1", "diagnosis": {"step": "pays back", "also_weak": [], "action": "x"}}, {"ad": "2", "diagnosis": {"step": "reach cost"}}]
        recs = interact.ad_records([{"ad_id": "1", "ad_name": "a", "spend": 1.0}, {"ad_id": "2", "ad_name": "b", "spend": 2.0}], None, grade)
        self.assertEqual([r["weak"] for r in recs], ["pays-back", "reach-cost"])
        self.assertEqual([g["step"] for g in interact.weak_groups(recs)], ["reach-cost", "pays-back"])

    def test_an_all_unknown_operand_reads_na_in_words(self):
        total = interact.totals_of([record("a", 100)], 100)
        self.assertEqual(total["roas_text"], "n/a (missing purchase value)")
        self.assertEqual(total["cpa_text"], "n/a (missing purchases)")

    def test_the_video_hook_rate_is_not_diluted_by_static_ads(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=two_ads(), currency="USD"))
        tile = re.search(r'<div class="kpi[^"]*"><p class="kpi-name">Hook rate.*?</div></div>', html, re.S).group(0)
        self.assertIn("25.00%", tile)
        self.assertNotIn("12.50%", tile)
        self.assertIn("video ads only (1 of 2 ads)", tile)
        hold = re.search(r'<div class="kpi[^"]*"><p class="kpi-name">Hold rate.*?</div></div>', html, re.S).group(0)
        self.assertIn("40.00%", hold)
        self.assertIn("video ads only (1 of 2 ads)", hold)

    def test_the_funnel_rates_the_video_steps_on_video_impressions(self):
        html, _ = panels.funnel(panels.Ctx(rows=two_ads(), currency="USD"))
        self.assertIn("25.00% of video impressions", html)
        self.assertIn("40.00%", html)
        self.assertNotIn("12.50%", html)

    def test_no_field_id_appears_in_the_words_a_reader_sees(self):
        full = report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=run_json("creative-mix", "mix.py"), currency="USD", title="Acme")
        parser = TextParts()
        parser.feed(full)
        seen = sorted(set(re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", " ".join(parser.text))))
        self.assertEqual(seen, [])

    def test_a_static_ad_is_not_video_rather_than_missing(self):
        rows = interact.ad_funnel({"impressions": 100.0, "spend": 1.0}, "static")
        plays = next(r for r in rows if r["step"] == "3-second plays")
        self.assertEqual(plays["count"], "n/a (not a video ad)")
        unknown = next(r for r in interact.ad_funnel({"impressions": 100.0}, "ugc-video") if r["step"] == "3-second plays")
        self.assertEqual(unknown["count"], "n/a (missing 3-second plays)")
        bands = interact.band_rows({"grades": {"hook_rate": {"value": None, "band": "not graded (missing video_views_3s)"}}}, str, "static")
        self.assertEqual(bands[0]["band"], "not graded: not a video ad")

    def test_slugs_are_shown_as_words_and_kept_raw_in_the_data(self):
        self.assertEqual(interact.humanise("ugc-video", True), "UGC video")
        self.assertEqual(interact.humanise("bau", True), "BAU")
        self.assertEqual(interact.humanise("AU", True), "AU")
        self.assertEqual(interact.humanise("trail_boot", True), "Trail boot")
        self.assertEqual(interact.humanise("static"), "static")
        self.assertEqual(interact.group_records(self.ctx.records, "format")[0]["label"], "UGC video")
        self.assertEqual(interact.group_records(self.ctx.records, "ad_type")[0]["label"], "BAU")
        _, data = page_data(report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, currency="USD"))
        self.assertEqual(data["names"]["format"]["ugc-video"], "UGC video")
        self.assertEqual(next(a for a in data["ads"] if a["id"] == "120000000001")["format"], "ugc-video")
        chips = re.findall(r'data-facet="format" data-value="ugc-video"><span class="chip-label">([^<]+)<', panels.filter_bar(self.ctx))
        self.assertEqual(chips, ["UGC video"])

    def test_the_open_view_leads_with_plain_words_and_files_the_technical_reasons_away(self):
        card = panels.ad_card(self.ctx, self.verdicts["ads"][0])
        body = card.split('<div class="open-body">')[1]
        self.assertLess(body.index("Confidence"), body.index("Technical detail"))
        self.assertLess(body.index("How to improve"), body.index("Technical detail"))
        tech = re.search(r'<details class="tech"><summary>Technical detail[^<]*</summary>(.*?)</details>', body, re.S).group(1)
        self.assertIn("top quartile", tech)
        self.assertNotIn("compared with format", body.split("Technical detail")[0])

    def test_the_open_view_is_two_columns_on_a_wide_screen_only(self):
        self.assertRegex(self.html, r"@media \(min-width: 721px\) \{[^@]*dialog\.ad-dialog \.ob-top \{[^}]*grid-template-columns")
        self.assertIn('<div class="ob-top"><div class="ob-media">', panels.ad_card(self.ctx, self.verdicts["ads"][0]))


class ScaleTest(unittest.TestCase):
    def test_five_hundred_twenty_ads_keep_the_payload_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.csv"
            with open(path, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Day", "Ad name", "Ad ID", "Amount spent (USD)", "Impressions", "Link clicks", "Purchases", "Purchases conversion value"])
                for n in range(520):
                    name = "concept-%d | %s | creator-%d | bau | prod | lofi | 2026-03-01" % (n % 40, ("static", "ugc-video", "carousel")[n % 3], n % 23)
                    for day in range(1, 4):
                        writer.writerow(["2026-03-%02d" % day, name, 1000 + n, 40 + (n * 7) % 90, 9000 + n * 11, 120 + n % 47, 3 + n % 7, 150 + (n * 13) % 400])
            verdicts = run_json("keep-or-kill", "verdicts.py", path)
            grade = run_json("creative-grader", "grade.py", path)
            html = report.build_html(rows=cm.load_rows(str(path)), verdicts=verdicts, grade=grade, currency="USD")
        raw, data = page_data(html)
        self.assertEqual(len(data["ads"]), 520)
        self.assertLess(len(raw.encode("utf-8")), 400 * 1024)
        self.assertLess(len(html.encode("utf-8")), 6 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
