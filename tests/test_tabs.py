import copy
import html as htmllib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))
sys.path.insert(1, str(ROOT / "skills" / "creative-mix" / "scripts"))

import briefing  # noqa: E402
import charts  # noqa: E402
import creative_metrics as cm  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
from mix import analyse_mix  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
BREAKDOWNS = ROOT / "tests" / "fixtures" / "breakdowns.csv"
BRIEFS = ROOT / "tests" / "fixtures" / "briefs.json"
PANELS = {pid: fn for _, _, tab in panels.TABS for pid, _, _, fn in tab}
NEW_IDS = ("format-scorecard", "hook-hold", "retention", "ad-types", "heatmap", "stage-heatmap", "no-creative", "segments", "gaps",
           "briefs", "copy", "prompts")


def run_json(skill, script, path=FIXTURE):
    out = subprocess.run([sys.executable, str(ROOT / "skills" / skill / "scripts" / script), str(path), "--json"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def synthetic_rows():
    """Twelve keyed-name ads over two markets and two funnel stages, with ad copy and a call to action on every row."""
    rows, n = [], 0
    for market in ("AU", "AU", "AU", "NZ"):
        for stage in ("tof", "mof"):
            for concept, fmt in (("alpha", "static"), ("beta", "ugc-video"), ("gamma", "carousel")):
                n += 1
                if market == "NZ" and n % 3:
                    continue
                rows.append({"ad_id": str(100 + n), "ad_name": "CONCEPT:%s | FMT:%s | TYPE:bau | MKT:%s | STAGE:%s | CR:house" % (concept, fmt, market, stage),
                             "date": "2026-03-01", "spend": 100.0 + n, "impressions": 9000.0, "conversion_value": 300.0 + n, "conversions": 5.0,
                             "Primary text": "Opening line %d <b>bold</b>\nSecond line" % n, "Headline": "Headline %d" % n,
                             "Call to action": "Shop now" if n % 2 else "Learn more"})
    return rows


def video_day(ad, fmt, day, impressions, plays=None, thru=None, link_clicks=None, source=None, quartiles=False, first_quartile=None):
    row = {"ad_id": ad, "ad_name": "c%s | %s | house | bau | p | lofi | 2026-03-01" % (ad, fmt), "date": day, "spend": 100.0, "impressions": impressions}
    if link_clicks is not None:
        row["link_clicks"] = link_clicks
    if plays is not None:
        row.update(video_views_3s=plays, video_thruplay=thru, video_views_3s_source=source or "reported")
    if quartiles:
        for n, name in enumerate(("25%", "50%", "75%", "95%", "100%")):
            row["Video plays at " + name] = first_quartile if (n == 0 and first_quartile is not None) else plays * (0.8 - 0.1 * n)
    return row


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = run_json("keep-or-kill", "verdicts.py")
        cls.grade = run_json("creative-grader", "grade.py")
        cls.mix = run_json("creative-mix", "mix.py")
        cls.ctx = panels.Ctx(rows=cls.rows, verdicts=cls.verdicts, grade=cls.grade, mix=cls.mix, currency="USD")
        cls.syn_rows = synthetic_rows()
        cls.syn = panels.Ctx(rows=cls.syn_rows, mix=analyse_mix(cls.syn_rows), currency="USD")

    def ctx_with(self, **changes):
        base = dict(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=self.mix, currency="USD")
        base.update(changes)
        return panels.Ctx(**base)


class NewPanelStateTest(Fixture):
    def test_all_twelve_new_panels_are_in_the_spec_order(self):
        tabs = {tab_id: [pid for pid, _, _, _ in tab] for tab_id, _, tab in panels.TABS}
        self.assertEqual(tabs["format"], ["format-scorecard", "hook-hold", "retention", "ad-types"])
        self.assertEqual(tabs["white-space"], ["heatmap", "stage-heatmap", "no-creative", "segments", "gaps"])
        self.assertEqual(tabs["briefing"], ["briefs", "copy", "prompts"])

    def test_each_panel_is_data_on_inputs_that_carry_its_source(self):
        breakdown_ctx = self.ctx_with(breakdowns=cm.load_rows(str(BREAKDOWNS)))
        copy_ctx = panels.Ctx(rows=self.syn_rows, mix=self.syn.mix, verdicts=self.verdicts, currency="USD")
        sources = {pid: self.ctx for pid in NEW_IDS}
        sources.update({"segments": breakdown_ctx, "stage-heatmap": self.syn, "copy": copy_ctx})
        for pid in NEW_IDS:
            html, state = PANELS[pid](sources[pid])
            self.assertEqual(state, "data", pid)
            self.assertNotIn("Why this is empty", html, pid)

    def test_each_panel_is_a_labelled_empty_state_without_its_source(self):
        for pid in NEW_IDS:
            html, state = PANELS[pid](panels.Ctx())
            self.assertEqual(state, "empty", pid)
            self.assertIn("Why this is empty:", html, pid)
            self.assertIn("How to get it:", html, pid)

    def test_panels_that_need_the_mix_say_so_with_rows_alone(self):
        ctx = panels.Ctx(rows=self.rows, verdicts=self.verdicts)
        for pid in ("format-scorecard", "ad-types", "heatmap", "stage-heatmap", "no-creative", "gaps", "prompts"):
            html, state = PANELS[pid](ctx)
            self.assertEqual(state, "empty", pid)
            self.assertIn("creative-mix", html, pid)

    def test_the_acme_example_has_no_funnel_stage_market_copy_or_breakdowns_and_says_how_to_add_them(self):
        stage = PANELS["stage-heatmap"](self.ctx)
        self.assertEqual(stage[1], "empty")
        self.assertIn("Your ad names do not carry a funnel stage: add one (see the naming guide in creative-context)", stage[0])
        seg = PANELS["segments"](self.ctx)
        self.assertEqual(seg[1], "empty")
        self.assertIn("Meta&#x27;s connector returns no age, gender or placement breakdowns: export one from Ads Manager "
                      "(recipe in creative-context) and pass it with --breakdowns", seg[0])
        copy_html, copy_state = PANELS["copy"](self.ctx)
        self.assertEqual(copy_state, "empty")
        self.assertIn("Copy comes back only for classic creatives; flexible and dynamic creatives return none. "
                      "Pass a CSV export with the Primary text and Headline columns to fill this.", copy_html)

    def test_no_not_built_state_is_left_on_the_page(self):
        page = report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=self.mix, currency="USD", title="Acme")
        self.assertNotIn("not built in this version", page.lower())
        for pid in NEW_IDS:
            self.assertIn('id="panel-%s"' % pid, page)


class FormatTest(Fixture):
    def rows_of(self, html):
        return re.findall(r"<tr[^>]*>.*?</tr>", html, re.S)

    def test_the_scorecard_lists_every_mix_format_with_the_spec_columns(self):
        html, _ = panels.format_scorecard(self.ctx)
        for fmt in self.mix["by_format"]:
            self.assertIn(panels.interact.humanise(fmt["format"], True), html)
        for head in ("Ads", "Spend share", "CTR", "CPM", "CPA", "ROAS", "Hook rate", "Hold rate"):
            self.assertIn(">%s<" % head, html)

    def test_a_metric_is_graded_across_formats_in_plain_words(self):
        html, _ = panels.format_scorecard(self.ctx)
        for words in ("best of your formats", "middle", "weakest"):
            self.assertIn(words, html)

    def test_grading_needs_three_formats(self):
        mix = copy.deepcopy(self.mix)
        mix["by_format"] = mix["by_format"][:2]
        html, _ = panels.format_scorecard(self.ctx_with(mix=mix))
        self.assertIn("not graded: fewer than 3 formats", html)
        self.assertNotIn("best of your formats", html)
        self.assertNotIn("weakest", html)

    def test_equal_values_share_a_band_and_the_tie_is_stated(self):
        mix = copy.deepcopy(self.mix)
        for row, roas in zip(mix["by_format"], (2.0, 2.0, 1.0)):
            row["roas"] = roas
        mix["by_format"] = mix["by_format"][:3]
        html, _ = panels.format_scorecard(self.ctx_with(mix=mix))
        self.assertEqual(html.count("best of your formats (tied)"), 2)
        self.assertIn("weakest", html)
        self.assertIn("equal values share a band", html)

    def test_hook_and_hold_are_not_applicable_to_a_format_without_three_second_plays(self):
        html, _ = panels.format_scorecard(self.ctx)
        static = [r for r in self.rows_of(html) if ">Static<" in r][0]
        self.assertEqual(static.count("n/a (not video)"), 2)
        video = [r for r in self.rows_of(html) if ">UGC video<" in r][0]
        self.assertNotIn("n/a (not video)", video)

    def test_each_format_row_has_a_strip_of_at_most_three_top_spend_ads_that_carry_data_ad(self):
        html, _ = panels.format_scorecard(self.ctx)
        strips = re.findall(r'<div class="pv-grid strip">(.*?)</div></td>', html, re.S)
        self.assertEqual(len(strips), len(self.mix["by_format"]))
        ids = set(self.ctx.record_index)
        for strip in strips:
            found = re.findall(r'data-ad="([^"]+)"', strip)
            self.assertTrue(1 <= len(found) <= 3)
            self.assertTrue(set(found) <= ids)

    def test_the_rendered_scorecard_ctr_is_the_ratio_of_sums_across_unequal_ads(self):
        rows = [video_day("1", "static", "2026-03-01", 1000.0, link_clicks=10.0), video_day("2", "static", "2026-03-01", 9000.0, link_clicks=900.0)]
        html, _ = panels.format_scorecard(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertIn("9.10%", html)
        self.assertNotIn("5.50%", html)

    def test_hook_and_hold_ignore_the_days_a_video_ad_has_no_plays_for(self):
        rows = [video_day("1", "ugc-video", "2026-03-01", 1000.0, plays=500.0, thru=100.0),
                video_day("1", "ugc-video", "2026-03-02", 9000.0)]
        html, _ = panels.format_scorecard(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertIn("50.00%", html)
        self.assertNotIn("5.00%", html)

    def test_the_bubble_chart_reads_the_same_video_days(self):
        rows = [video_day("1", "ugc-video", "2026-03-01", 1000.0, plays=500.0, thru=100.0), video_day("1", "ugc-video", "2026-03-02", 9000.0),
                video_day("2", "ugc-video", "2026-03-01", 1000.0, plays=200.0, thru=100.0)]
        html, state = panels.video_hook_hold(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertEqual(state, "data")
        self.assertIn("Hook rate (%) 50.00", html)
        self.assertNotIn("Hook rate (%) 5.00", html)

    def test_derived_three_second_plays_are_labelled_in_the_scorecard_and_the_bubble_note(self):
        rows = [video_day(str(i), "ugc-video", "2026-03-01", 1000.0, plays=100.0 * i, thru=50.0, source="derived: spend / cost per 3-second view")
                for i in (1, 2, 3)]
        ctx = panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD")
        card = panels.format_scorecard(ctx)[0]
        self.assertIn("(derived)", card)
        self.assertIn("derived", panels.video_hook_hold(ctx)[0].lower())

    def test_retention_leaves_derived_ads_out_and_says_why(self):
        rows = [video_day("1", "ugc-video", "2026-03-01", 1000.0, plays=500.0, thru=100.0, quartiles=True),
                video_day("2", "ugc-video", "2026-03-01", 1000.0, plays=400.0, thru=100.0, quartiles=True, source="derived: spend / cost per 3-second view")]
        html, state = panels.video_retention(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertEqual(state, "data")
        self.assertEqual(html.count('<path class="line s'), 1)
        self.assertIn("derived", html)
        only_derived = [rows[1]]
        html, state = panels.video_retention(panels.Ctx(rows=only_derived, mix=analyse_mix(only_derived), currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("derived", html)

    def test_retention_first_point_sums_only_the_days_that_carry_all_five_counts(self):
        rows = [video_day("1", "ugc-video", "2026-03-01", 1000.0, plays=500.0, thru=100.0, quartiles=True),
                video_day("1", "ugc-video", "2026-03-02", 1000.0, plays=700.0, thru=100.0)]
        html, _ = panels.video_retention(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertIn("3-second plays: 500 people", html)
        self.assertNotIn("1,200", html)

    def test_an_unknown_format_is_not_graded_and_does_not_count_toward_three(self):
        rows = [video_day("1", "static", "2026-03-01", 1000.0, link_clicks=10.0), video_day("2", "carousel", "2026-03-01", 1000.0, link_clicks=20.0)]
        rows.append({"ad_id": "3", "ad_name": "mystery", "date": "2026-03-01", "spend": 50.0, "impressions": 1000.0, "link_clicks": 30.0})
        mix = analyse_mix(rows)
        mix["by_format"] = mix["by_format"] + [{"format": "unknown", "ads": 1, "spend": 50.0, "share": 10.0, "roas": None, "cpa": None}]
        html, _ = panels.format_scorecard(panels.Ctx(rows=rows, mix=mix, currency="USD"))
        self.assertIn("not graded: fewer than 3 formats", html)
        self.assertIn("not graded: format not known", html)
        self.assertNotIn("best of your formats", html)

    def test_the_retention_note_does_not_claim_the_lines_only_fall_and_explains_a_rise(self):
        html, _ = panels.video_retention(self.ctx)
        self.assertNotIn("can only fall", html)
        rows = [video_day("1", "ugc-video", "2026-03-01", 1000.0, plays=100.0, thru=50.0, quartiles=True, first_quartile=300.0)]
        html, _ = panels.video_retention(panels.Ctx(rows=rows, mix=analyse_mix(rows), currency="USD"))
        self.assertIn("On short videos the 25% point comes before the 3-second mark", html)

    def test_a_non_finite_number_in_the_data_is_missing_not_a_value(self):
        for text in ("nan", "inf", "-inf", "NaN"):
            self.assertIsNone(cm._num(text), text)
        self.assertIsNone(cm._num(float("nan")))
        self.assertEqual(cm._num("1,234.5"), 1234.5)

    def test_bubble_chart_has_four_plain_word_quadrants_and_labels_the_top_ads(self):
        html, _ = panels.video_hook_hold(self.ctx_with(top_n=2))
        for words in ("Stops people and keeps them", "Stops people, loses them", "Keeps the few it stops", "Neither yet"):
            self.assertIn(words, html)
        self.assertIn("Hook rate (%)", html)
        self.assertIn("Hold rate (%)", html)
        self.assertTrue(1 <= html.count('class="blabel"') <= 2)
        self.assertIn("named where there is room", html)
        self.assertIn('class="guide"', html)

    def test_bubble_area_follows_spend(self):
        svg = charts.bubble_chart([(10.0, 20.0, 100.0, "a", True), (12.0, 22.0, 400.0, "b", True), (14.0, 24.0, 900.0, "c", False)],
                                  "Hook (%)", "Hold (%)", "test", 12.0, 22.0, ("tl", "tr", "bl", "br"))
        radii = sorted(float(r) for r in re.findall(r'<circle class="bub"[^>]* r="([\d.]+)"', svg))
        self.assertEqual(len(radii), 3)
        self.assertAlmostEqual((radii[1] / radii[0]) ** 2, 4.0, places=1)
        self.assertAlmostEqual((radii[2] / radii[0]) ** 2, 9.0, places=1)

    def test_no_video_ads_gives_an_empty_state(self):
        static = [r for r in self.rows if "ugc" not in str(r.get("ad_name")) and "video" not in str(r.get("ad_name"))
                  and "partnership" not in str(r.get("ad_name"))]
        stripped = [{k: v for k, v in r.items() if k not in ("video_views_3s", "video_thruplay")} for r in static]
        html, state = panels.video_hook_hold(self.ctx_with(rows=stripped))
        self.assertEqual(state, "empty")
        self.assertIn("3-second", html)


class RetentionTest(Fixture):
    COLUMNS = ("Video plays at 25%", "Video plays at 50%", "Video plays at 75%", "Video plays at 95%", "Video plays at 100%")

    def test_the_curve_is_a_count_of_people_still_watching_never_a_percentage(self):
        html, state = panels.video_retention(self.ctx)
        self.assertEqual(state, "data")
        self.assertIn("People still watching (count)", html)
        y_axis = re.search(r'rotate\(-90[^>]*>([^<]*)<', html).group(1)
        self.assertNotIn("%", y_axis)
        self.assertEqual(html.count('<path class="line s'), 3)
        for step in ("3-second plays", "25% watched", "100% watched"):
            self.assertIn(step, html)

    def test_average_watch_time_shows_when_the_column_exists(self):
        html, _ = panels.video_retention(self.ctx)
        self.assertIn("Average watch time", html)
        rows = [{k: v for k, v in r.items() if k != "Video average play time"} for r in self.rows]
        without, state = panels.video_retention(self.ctx_with(rows=rows))
        self.assertEqual(state, "data")
        self.assertIn("n/a (no average play time column in the data)", without)

    def test_missing_quartile_columns_are_an_empty_state_that_names_them(self):
        rows = [{k: v for k, v in r.items() if k not in ("Video plays at 75%", "Video plays at 95%")} for r in self.rows]
        html, state = panels.video_retention(self.ctx_with(rows=rows))
        self.assertEqual(state, "empty")
        self.assertIn("Video plays at 75%", html)
        self.assertIn("Video plays at 95%", html)
        self.assertNotIn("Video plays at 25%,", html)

    def test_no_quartile_columns_at_all_names_all_five(self):
        rows = [{k: v for k, v in r.items() if k not in self.COLUMNS} for r in self.rows]
        html, state = panels.video_retention(self.ctx_with(rows=rows))
        self.assertEqual(state, "empty")
        for name in self.COLUMNS:
            self.assertIn(name, html)

    def test_matched_headers_are_named_in_the_footer(self):
        page = report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=self.mix, currency="USD")
        method = page[page.index("<footer>"):]
        for name in self.COLUMNS + ("Video average play time",):
            self.assertIn(name, method)

    def test_unmatched_headers_are_named_in_the_footer_too(self):
        rows = [{k: v for k, v in r.items() if k != "Video plays at 75%"} for r in self.rows]
        page = report.build_html(rows=rows, mix=self.mix, currency="USD")
        self.assertIn("Video plays at 75%: not found", page[page.index("<footer>"):])


class AdTypeTest(Fixture):
    def test_one_table_per_type_and_never_a_blended_total(self):
        html, _ = panels.ad_type_split(self.ctx)
        types = [t["ad_type"] for t in self.mix["by_type"]]
        self.assertEqual(html.count("<table"), len(types))
        for name in types:
            self.assertIn(">%s<" % panels.interact.humanise(name, True), html)
        self.assertNotIn("All types", html)
        self.assertNotIn("Total", html)

    def test_each_type_states_its_own_ads_spend_share_roas_cpa_and_format_mix(self):
        html, _ = panels.ad_type_split(self.ctx)
        bau = [t for t in self.mix["by_type"] if t["ad_type"] == "bau"][0]
        block = html[html.index(">BAU<"):]
        block = block[:block.index("</table>")]
        self.assertIn("%d ads" % bau["ads"], block)
        self.assertIn("%.2fx" % bau["roas"], block)
        self.assertIn("Share of this type", block)

    def test_a_type_outside_the_list_is_kept_and_explained(self):
        mix = copy.deepcopy(self.mix)
        mix["unknown_types"] = ["flashsale"]
        mix["by_type"].append({"ad_type": "flashsale", "ads": 1, "spend": 5.0, "share": 0.1, "roas": 1.0, "cpa": 5.0})
        html, _ = panels.ad_type_split(self.ctx_with(mix=mix))
        self.assertIn("flashsale", html)
        self.assertIn("not in the standard list", html)
        self.assertIn("promo", html)


class WhiteSpaceTest(Fixture):
    def test_the_heatmap_caps_concepts_and_says_how_many_are_hidden(self):
        html, _ = panels.concept_heatmap(self.ctx)
        total = len(self.mix["grid"]["families"])
        self.assertGreater(total, 18)
        self.assertIn("top 18 of %d concepts" % total, html)
        self.assertIn("%d hidden" % (total - 18), html)
        self.assertEqual(html.count('class="hm-row-label"'), 18)

    def test_the_heatmap_shows_ad_counts_hatches_empty_cells_and_numbers_the_gaps_like_the_list(self):
        html, _ = panels.concept_heatmap(self.ctx)
        self.assertIn("url(#hatch", html)
        self.assertIn("hm-gap", html)
        listing, _ = panels.gap_list(self.ctx)
        listed = {int(n): text for n, text in re.findall(r'data-gap="(\d+)".*?<b>#\d+ ([^<]*)</b>', listing, re.S)}
        outlined = {int(n) for n in re.findall(r'class="hm-gap-num"[^>]*>#(\d+)<', html)}
        self.assertTrue(outlined)
        self.assertTrue(outlined <= set(listed))
        gaps = self.mix["gaps"]
        shown = set(self.mix["grid"]["families"][:18])
        expected = {i + 1 for i, g in enumerate(gaps) if g["concept"] in shown}
        self.assertEqual(outlined, expected)
        for number in outlined:
            gap = gaps[number - 1]
            self.assertIn(panels.interact.humanise(gap["concept"], True), listed[number])

    def test_a_gap_hidden_from_the_heatmap_is_said_to_be_hidden(self):
        html, _ = panels.concept_heatmap(self.ctx)
        hidden = sum(1 for g in self.mix["gaps"] if g["concept"] not in set(self.mix["grid"]["families"][:18]))
        if hidden:
            self.assertIn("%d gap" % hidden, html)

    def test_the_gap_list_keeps_mix_order_shows_top_n_and_folds_the_rest(self):
        html, _ = panels.gap_list(self.ctx_with(top_n=4))
        self.assertEqual(len(re.findall(r'<li class="gap" data-gap=', html.split("<details")[0])), 4)
        self.assertIn("<details", html)
        self.assertEqual(len(re.findall(r'data-gap="', html)), len(self.mix["gaps"]))
        self.assertIn("hypothesis to test", html)

    def test_why_test_this_names_the_neighbour_with_its_spend_and_roas(self):
        html, _ = panels.gap_list(self.ctx)
        gap = self.mix["gaps"][0]
        row = [r for r in self.mix["by_format"] if r["format"] == gap["format"]][0]
        self.assertIn("%.2fx" % row["roas"], html)
        self.assertIn("top quarter", html)

    def test_the_stage_heatmap_reads_a_name_that_carries_a_funnel_stage(self):
        html, state = panels.stage_heatmap(self.syn)
        self.assertEqual(state, "data")
        self.assertIn("tof", html)
        self.assertIn("mof", html)

    def test_types_with_no_creative_are_listed_with_one_line_each(self):
        html, state = panels.no_creative_types(self.ctx)
        self.assertEqual(state, "data")
        present = {t["ad_type"] for t in self.mix["by_type"]}
        for kind in cm.AD_TYPES:
            self.assertEqual(kind in present, ('data-type="%s"' % kind) not in html)
        self.assertIn('data-type="hype"', html)

    def test_every_type_present_says_so(self):
        mix = copy.deepcopy(self.mix)
        mix["by_type"] = [{"ad_type": t, "ads": 1, "spend": 1.0, "share": 1.0, "roas": 1.0, "cpa": 1.0} for t in cm.AD_TYPES]
        html, state = panels.no_creative_types(self.ctx_with(mix=mix))
        self.assertEqual(state, "data")
        self.assertIn("Every ad type", html)

    def test_markets_flag_thin_coverage_below_the_group_minimum(self):
        html, state = panels.segments(self.syn)
        self.assertEqual(state, "data")
        self.assertIn(">AU<", html)
        nz = [r for r in re.findall(r"<tr.*?</tr>", html, re.S) if ">NZ<" in r][0]
        self.assertIn("thin coverage", nz)
        au = [r for r in re.findall(r"<tr.*?</tr>", html, re.S) if ">AU<" in r][0]
        self.assertNotIn("thin coverage", au)

    def test_breakdowns_aggregate_as_a_ratio_of_sums(self):
        html, state = panels.segments(self.ctx_with(breakdowns=cm.load_rows(str(BREAKDOWNS))))
        self.assertEqual(state, "data")
        age = [r for r in re.findall(r"<tr.*?</tr>", html, re.S) if ">35-44<" in r][0]
        self.assertIn("2.83x", age)
        self.assertIn("USD 40.00", age)
        self.assertIn("64.3%", age)
        young = [r for r in re.findall(r"<tr.*?</tr>", html, re.S) if ">18-24<" in r][0]
        self.assertIn("1.80x", young)
        self.assertNotIn("1.62x", young)
        male = [r for r in re.findall(r"<tr.*?</tr>", html, re.S) if ">male<" in r][0]
        self.assertIn("0.43x", male)
        self.assertIn("USD 140.00", male)
        for dim in ("Age", "Gender", "Placement"):
            self.assertIn(">%s<" % dim, html)

    def test_a_segment_with_no_purchases_is_na_not_zero(self):
        rows = cm.load_rows(str(BREAKDOWNS))
        html, _ = panels.segments(self.ctx_with(breakdowns=[r for r in rows if r["Age"] == "35-44" and r["Gender"] == "male"]))
        self.assertIn("n/a (zero purchases)", html)


class BriefingTest(Fixture):
    def test_validation_shows_missing_keys_as_not_stated_and_ignores_unknown_keys(self):
        briefs = briefing.validate_briefs(json.loads(BRIEFS.read_text()))
        self.assertEqual(len(briefs), 2)
        sparse = briefs[1]
        for key in ("objective", "persona", "stage", "message", "format", "specs"):
            self.assertEqual(sparse[key], "not stated", key)
        self.assertEqual(sparse["hooks"], [])
        self.assertNotIn("ignored_extra", briefs[0])

    def test_an_unknown_metric_id_is_flagged_and_a_known_one_is_not(self):
        brief = briefing.validate_briefs(json.loads(BRIEFS.read_text()))[0]
        status = {m["id"]: m["defined"] for m in brief["judged_by"]}
        self.assertEqual(status, {"roas": True, "cpa": True, "payback_speed": False})

    def test_a_briefs_file_must_be_a_list_of_objects(self):
        for bad in ({"title": "x"}, ["x"], "text", 3):
            with self.assertRaises(ValueError):
                briefing.validate_briefs(bad)

    def test_brief_cards_escape_hooks_and_flag_the_undefined_metric(self):
        briefs = json.loads(BRIEFS.read_text())
        html, state = panels.ready_briefs(self.ctx_with(briefs=briefs))
        self.assertEqual(state, "data")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert", html)
        self.assertIn("payback_speed (not a defined metric)", html)
        self.assertIn("not stated", html)
        self.assertNotIn("never shown", html)

    def test_brief_cards_show_reference_previews_and_say_when_an_ad_is_not_in_the_data(self):
        html, _ = panels.ready_briefs(self.ctx_with(briefs=json.loads(BRIEFS.read_text())))
        self.assertIn('data-ad="120000000001"', html)
        self.assertIn("999999999999", html)
        self.assertIn("not in this data", html)

    def test_without_a_briefs_file_there_are_starters_from_gaps_and_iterate_ads(self):
        html, state = panels.ready_briefs(self.ctx)
        self.assertEqual(state, "data")
        cards = html.count('<article class="brief-card"')
        iterate = sum(1 for e in self.verdicts["ads"] if e["verdict_id"] == "iterate")
        self.assertEqual(cards, 3 + min(2, iterate))
        self.assertIn("a new version of", html.lower())
        self.assertIn("Write the full brief", html)

    def test_starters_never_contain_a_hook_or_a_message(self):
        html, _ = panels.ready_briefs(self.ctx)
        self.assertEqual(html.count("Hooks: ask the hook-writer skill"), html.count('<article class="brief-card"'))
        self.assertNotIn("Message:", html)
        self.assertIn("hook-writer", html)
        self.assertIn("creative-brief", html)

    def test_starters_say_how_each_will_be_judged_from_the_verdict_basis(self):
        html, _ = panels.ready_briefs(self.ctx)
        self.assertIn("cost per sale and return on ad spend", html)

    def test_no_briefs_file_and_nothing_to_build_from_is_an_empty_state(self):
        html, state = panels.ready_briefs(panels.Ctx(rows=self.rows))
        self.assertEqual(state, "empty")
        self.assertIn("--briefs", html)

    def test_the_copy_panel_lists_cta_types_and_the_opening_line_of_top_ads_with_a_verdict_chip(self):
        verdict_rows = [{"ad": r["ad_id"], "ad_name": r["ad_name"], "verdict_id": "keep", "spend": r["spend"]} for r in self.syn_rows]
        ctx = panels.Ctx(rows=self.syn_rows, mix=self.syn.mix, verdicts={"ads": verdict_rows, "summary": {}}, currency="USD")
        html, state = panels.copy_cta(ctx)
        self.assertEqual(state, "data")
        self.assertIn("Shop now", html)
        self.assertIn("Learn more", html)
        self.assertEqual(len(re.findall(r'<tr data-ad="', html)), min(8, len(ctx.ads)))
        self.assertIn("Opening line", html)
        self.assertNotIn("<b>bold</b>", html)
        self.assertNotIn("Second line", html)
        self.assertIn('class="badge keep"', html)

    def test_three_prompts_use_labels_only_and_carry_no_figure_from_the_data(self):
        html, state = panels.prompts_panel(self.ctx)
        self.assertEqual(state, "data")
        prompts = [htmllib.unescape(p) for p in re.findall(r'<pre class="prompt">(.*?)</pre>', html, re.S)]
        self.assertEqual(len(prompts), 3)
        for skill in ("creative-ideation", "hook-writer", "creative-brief"):
            self.assertEqual(sum(skill in p for p in prompts), 1 if skill != "hook-writer" else 2, skill)
        for text in prompts:
            self.assertIsNone(re.search(r"\d", text), text)
        self.assertIn(panels.interact.humanise(self.mix["top_formats"][0], True).lower(), prompts[0].lower())
        self.assertEqual(html.count("<details"), 3)

    def test_the_copy_buttons_sit_outside_the_prompt_details_and_find_their_prompt(self):
        html, _ = panels.prompts_panel(self.ctx)
        self.assertEqual(html.count('data-action="copy-prompt"'), 3)
        self.assertEqual(html.count('class="prompt-scope"'), 3)
        template = (ROOT / "skills" / "creative-report" / "assets" / "report-template.html").read_text()
        self.assertIn('btn.closest(".prompt-scope")', template)


class FilterAttributeTest(Fixture):
    def test_every_ad_in_a_new_panel_carries_data_ad_for_the_filters(self):
        ids = set(self.ctx.record_index)
        breakdown_ctx = self.ctx_with(briefs=json.loads(BRIEFS.read_text()))
        for pid, ctx in (("format-scorecard", self.ctx), ("briefs", self.ctx), ("briefs-file", breakdown_ctx)):
            html = PANELS["briefs" if pid == "briefs-file" else pid](ctx)[0]
            found = re.findall(r'data-ad="([^"]+)"', html)
            self.assertTrue(found, pid)
            self.assertTrue(set(found) <= ids, pid)

    def test_copy_rows_carry_data_ad(self):
        html = panels.copy_cta(self.syn)[0]
        found = re.findall(r'<tr data-ad="([^"]+)"', html)
        self.assertTrue(found)
        self.assertTrue(set(found) <= set(self.syn.record_index))

    def test_the_payload_still_lists_every_ad(self):
        page = report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=self.mix, currency="USD")
        block = re.search(r'id="ad-data">(.*?)</script>', page, re.S).group(1)
        self.assertEqual(len(json.loads(block)["ads"]), len(self.ctx.records))


class CommandLineTest(Fixture):
    def build(self, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "r.html"
            args = [str(FIXTURE), "--verdicts", self.write(tmp, self.verdicts, "v"), "--mix", self.write(tmp, self.mix, "m"),
                    "--grade", self.write(tmp, self.grade, "g"), "--title", "Acme", "-o", str(out)] + list(extra)
            done = subprocess.run([sys.executable, str(SCRIPT / "report.py")] + args, capture_output=True, text=True)
            return done, out.read_text() if out.exists() else ""

    def write(self, tmp, data, name):
        path = Path(tmp) / (name + ".json")
        path.write_text(json.dumps(data))
        return str(path)

    def test_breakdowns_and_briefs_flags_fill_their_panels(self):
        done, page = self.build("--breakdowns", str(BREAKDOWNS), "--briefs", str(BRIEFS))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Trail boots, the long way round", page)
        panel = page[page.index('id="panel-segments"'):page.index('id="panel-gaps"')]
        self.assertIn('data-state="data"', panel[:200])
        self.assertIn("2.83x", panel)
        self.assertIn("Breakdown file: 5 rows", page)

    def test_a_briefs_file_that_is_not_a_list_stops_with_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "b.json"
            bad.write_text('{"title": "x"}')
            done = subprocess.run([sys.executable, str(SCRIPT / "report.py"), str(FIXTURE), "--briefs", str(bad), "-o", str(Path(tmp) / "r.html")],
                                  capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--briefs", done.stderr)


class TemplateTest(unittest.TestCase):
    def test_the_open_ad_preview_column_is_sized_to_the_image(self):
        css = (ROOT / "skills" / "creative-report" / "assets" / "report-template.html").read_text()
        self.assertIn("grid-template-columns: fit-content(460px) minmax(0, 1fr)", css)
        self.assertNotIn("grid-template-columns: minmax(0, 460px) minmax(0, 1fr)", css)


if __name__ == "__main__":
    unittest.main()
