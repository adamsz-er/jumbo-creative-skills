import csv
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

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


class UniqueLabelsTest(unittest.TestCase):
    def labels(self, *recs):
        return interact.unique_labels(list(recs))

    def test_ads_that_share_a_label_are_told_apart_by_the_next_parsed_fields_in_order(self):
        recs = [record(1, 10, label="video · BAU", collection="spring", product="boot"),
                record(2, 10, label="video · BAU", collection="spring", product="tent"),
                record(3, 10, label="video · BAU", collection="autumn", product="boot")]
        got = self.labels(*recs)
        self.assertEqual(len(set(got.values())), 3)
        self.assertEqual(got["1"], "video · BAU · spring · boot")
        self.assertEqual(got["3"], "video · BAU · autumn")

    def test_a_field_that_is_the_same_across_the_group_is_not_appended(self):
        recs = [record(1, 10, label="video · BAU", collection="spring", tone="warm"),
                record(2, 10, label="video · BAU", collection="spring", tone="cool")]
        got = self.labels(*recs)
        self.assertEqual(got, {"1": "video · BAU · warm", "2": "video · BAU · cool"})

    def test_segment_fields_come_after_the_named_ones_in_position_order(self):
        recs = [record(1, 10, label="static", segment_9="b", segment_2="a"),
                record(2, 10, label="static", segment_9="c", segment_2="a")]
        self.assertEqual(self.labels(*recs), {"1": "static · b", "2": "static · c"})

    def test_a_launch_date_is_written_as_it_was(self):
        recs = [record(1, 10, label="static", launch_date="2026-03-01"), record(2, 10, label="static", launch_date="2026-04-01")]
        self.assertEqual(self.labels(*recs)["1"], "static · 2026-03-01")

    def test_ads_with_nothing_left_to_tell_them_apart_get_the_last_four_digits_of_the_id(self):
        recs = [record(120000000001, 10, label="video · BAU"), record(120000000002, 10, label="video · BAU"),
                record(120000000003, 10, label="video · BAU")]
        got = self.labels(*recs)
        self.assertEqual(got["120000000001"], "video · BAU · …0001")
        self.assertEqual(len(set(got.values())), 3)

    def test_ids_that_even_share_their_last_four_digits_still_end_up_distinct(self):
        got = self.labels(record(11110001, 10, label="x"), record(22220001, 10, label="x"))
        self.assertEqual(len(set(got.values())), 2)

    def test_a_label_that_is_already_unique_is_left_alone(self):
        got = self.labels(record(1, 10, label="a", collection="c"), record(2, 10, label="b", collection="c"))
        self.assertEqual(got, {"1": "a", "2": "b"})

    def test_the_records_the_dashboard_builds_carry_the_distinct_labels(self):
        rows = [{"ad_id": str(100 + n), "ad_name": "x | video | bau | boot | warm | 2026-03-0%d" % n, "date": "2026-03-01", "spend": 10.0}
                for n in range(1, 4)]
        ads = cm.aggregate_by_ad(rows)
        labels = [r["label"] for r in interact.ad_records(ads, None, None)]
        self.assertEqual(len(set(labels)), 3, labels)


PARTIAL_ROWS = [{"ad_id": i, "ad_name": "ad %s | static | c | bau | p | t | 2026-03-01" % i, "date": "2026-03-01", "spend": float(sp),
                 "impressions": 10000.0, "conversion_value": float(v), "conversions": float(c)}
                for i, sp, v, c in (("a", 100, 500, 5), ("b", 80, 300, 4), ("c", 60, 100, 2), ("d", 40, 60, 1))]


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


CHIP_COLOURS = {"scale": ("#dbeafe", "#1d4ed8", "#bfdbfe"), "keep": ("#ede9fe", "#6d28d9", "#ddd6fe"), "iterate": ("#fef3c7", "#b45309", "#fde68a"),
                "check": ("#e0f2fe", "#0369a1", "#bae6fd"), "kill": ("#fee2e2", "#b91c1c", "#fecaca"), "early": ("#f3f4f6", "#4b5563", "#e5e7eb"),
                "cant": ("#f3f4f6", "#4b5563", "#e5e7eb")}


class VerdictChipTest(Fixture):
    def test_every_verdict_class_has_a_plain_tooltip(self):
        self.assertEqual(set(interact.VERDICT_TIPS), {cls for cls, _ in interact.BOARD})
        for cls, tip in interact.VERDICT_TIPS.items():
            self.assertGreater(len(tip.split()), 5, cls)
            self.assertNotRegex(tip, r"[_{}]")

    def test_the_chip_carries_its_label_and_tooltip_escaped(self):
        chip = panels.verdict_chip("check")
        self.assertEqual(chip, '<span class="badge check" title="%s">Check before cutting</span>' % panels.esc(interact.VERDICT_TIPS["check"]))

    def test_the_card_the_open_view_the_board_header_and_the_tile_use_the_chip_with_its_tooltip(self):
        entry = next(e for e in self.verdicts["ads"] if panels.entry_class(e) == "iterate")
        card = panels.ad_card(self.ctx, entry)
        self.assertGreaterEqual(card.count(panels.verdict_chip("iterate")), 2)
        board, _ = panels.verdict_board(self.ctx)
        shown = re.findall(r'<section class="v-row v-row-(\w+)"><h3><span class="badge \w+" title="', board)
        self.assertGreaterEqual(len(shown), 3)
        tile = panels.preview_tile(self.ctx, entry["ad"])
        self.assertIn(panels.verdict_chip("iterate"), tile)

    def test_the_page_data_carries_the_tooltips_for_the_script(self):
        _, data = page_data(self.html)
        self.assertEqual(set(data["verdict_tips"]), set(interact.PUBLIC_LABEL))
        self.assertEqual(data["verdict_tips"]["pause"], interact.VERDICT_TIPS["kill"])

    def test_the_chips_are_tinted_in_light_and_dark(self):
        template = (ASSETS / "report-template.html").read_text()
        for cls, (bg, fg, edge) in CHIP_COLOURS.items():
            for value in (bg, fg, edge):
                self.assertIn("--v-%s-%s: %s;" % (cls, {bg: "bg", fg: "fg", edge: "bd"}[value], value), template)
            self.assertRegex(template, r"\.badge\.%s \{[^}]*background: var\(--v-%s-bg\)[^}]*color: var\(--v-%s-fg\)[^}]*border-color: var\(--v-%s-bd\)" % ((cls,) * 4))
        dark = re.findall(r"--v-scale-bg: hsl\(217 91% 60% / \.12\);", template)
        self.assertEqual(len(dark), 2)
        self.assertIn("font: 600 11px/1.4", re.search(r"\.badge \{[^}]*\}", template).group(0))


class HeatTest(unittest.TestCase):
    GREEN, RED = "rgb(34 197 94 / 0.60)", "rgb(220 38 38 / 0.60)"

    def test_the_best_value_of_a_higher_is_better_metric_gets_the_strongest_green_and_the_worst_the_strongest_red(self):
        tints = interact.heat_tints({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0}, lower_is_better=False)
        self.assertEqual(tints["e"], self.GREEN)
        self.assertEqual(tints["a"], self.RED)
        self.assertIsNone(tints["c"])

    def test_a_cost_metric_is_inverted_so_the_lowest_cost_is_the_strongest_green(self):
        tints = interact.heat_tints({"a": 10.0, "b": 20.0, "c": 30.0}, lower_is_better=True)
        self.assertEqual(tints["a"], self.GREEN)
        self.assertEqual(tints["c"], self.RED)

    def test_an_unreadable_value_is_not_tinted_and_does_not_take_a_rank(self):
        tints = interact.heat_tints({"a": 1.0, "b": None, "c": 3.0}, lower_is_better=False)
        self.assertIsNone(tints["b"])
        self.assertEqual((tints["a"], tints["c"]), (self.RED, self.GREEN))

    def test_a_tie_is_never_painted_green_or_red(self):
        self.assertEqual(interact.heat_tints({"a": 2.0, "b": 2.0, "c": 2.0}, False), {"a": None, "b": None, "c": None})
        self.assertEqual(interact.heat_tints({"a": 2.0}, False), {"a": None})
        tints = interact.heat_tints({"a": 1.0, "b": 2.0, "c": 2.0, "d": 3.0}, False)
        self.assertEqual((tints["b"], tints["c"]), (None, None))

    def test_strength_comes_from_ranks_so_one_outlier_does_not_wash_the_rest_to_neutral(self):
        tints = interact.heat_tints({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 100000.0}, False)
        alphas = [float(tints[k].split("/ ")[1].rstrip(")")) for k in "abde"]
        self.assertEqual(alphas, [0.6, 0.35, 0.35, 0.6])

    def test_the_tint_never_goes_past_the_cap_so_text_stays_readable(self):
        for tint in interact.heat_tints({str(n): float(n) for n in range(9)}, False).values():
            if tint:
                self.assertLessEqual(float(tint.split("/ ")[1].rstrip(")")), 0.6)


class MetricPillTest(Fixture):
    def pills(self, html):
        return re.findall(r'<div class="m-row"><span class="m-label">([^<]+)</span><span class="m-pill"([^>]*)>([^<]*)</span></div>', html)

    def test_a_card_shows_spend_roas_cpa_ctr_and_hook_rate_for_video_and_cpm_for_the_rest(self):
        video = next(a for a in self.ctx.ads if "video" in str(a["format"]))
        still = next(a for a in self.ctx.ads if "video" not in str(a["format"]))
        labels = lambda ad: [l for l, _, _ in self.pills(panels.ad_card(self.ctx, {"ad": ad["ad_id"], "ad_name": ad["ad_name"]}))]
        self.assertEqual(labels(video), ["Spend", "ROAS", "CPA", "CTR", "Hook rate"])
        self.assertEqual(labels(still), ["Spend", "ROAS", "CPA", "CTR", "CPM"])

    def test_the_best_roas_on_the_page_gets_the_strongest_green_and_the_best_cpa_too(self):
        best_roas = max((a for a in self.ctx.ads if a["roas"] is not None), key=lambda a: a["roas"])
        best_cpa = min((a for a in self.ctx.ads if a["cpa"] is not None), key=lambda a: a["cpa"])
        for ad, label in ((best_roas, "ROAS"), (best_cpa, "CPA")):
            pills = {l: (attrs, text) for l, attrs, text in self.pills(panels.ad_card(self.ctx, {"ad": ad["ad_id"], "ad_name": ad["ad_name"]}))}
            self.assertIn("--heat:rgb(34 197 94 / 0.60)", pills[label][0], label)

    def test_spend_is_never_tinted(self):
        for ad in self.ctx.ads[:5]:
            pills = {l: attrs for l, attrs, _ in self.pills(panels.ad_card(self.ctx, {"ad": ad["ad_id"], "ad_name": ad["ad_name"]}))}
            self.assertNotIn("--heat", pills["Spend"])

    def test_a_missing_value_reads_n_a_with_its_reason_and_no_tint(self):
        rows = [{"ad_id": str(n), "ad_name": "x%d | static | bau" % n, "date": "2026-03-01", "spend": 10.0 * n, "impressions": 1000.0} for n in (1, 2, 3)]
        ctx = panels.Ctx(rows=rows, currency="USD")
        pills = {l: (attrs, text) for l, attrs, text in self.pills(panels.ad_card(ctx, {"ad": "1", "ad_name": "x1 | static | bau"}))}
        attrs, text = pills["ROAS"]
        self.assertEqual(text, "n/a")
        self.assertNotIn("--heat", attrs)
        self.assertIn("missing", attrs)

    def test_an_ad_that_is_not_in_the_data_reads_n_a_everywhere(self):
        pills = self.pills(panels.ad_card(panels.Ctx(), {"ad": "9", "ad_name": "x"}))
        self.assertTrue(pills)
        self.assertTrue(all(text == "n/a" and "--heat" not in attrs for _, attrs, text in pills))


def template_text():
    return (ASSETS / "report-template.html").read_text()


def css_rule(selector):
    found = re.search(r"(?m)^%s \{([^}]*)\}" % re.escape(selector), template_text())
    assert found, "no rule for %s" % selector
    return found.group(1)


class CardDesignTest(Fixture):
    def entry_of(self, cls):
        return next(e for e in self.verdicts["ads"] if panels.entry_class(e) == cls)

    def test_the_card_stacks_preview_label_tags_numbers_and_the_verdict_footer(self):
        entry = self.entry_of("iterate")
        card = panels.ad_card(self.ctx, entry)
        order = [card.index(m) for m in ('class="ad-img"', "<h4>", 'class="metrics"', 'class="ad-foot"', '<details class="open-ad">')]
        self.assertEqual(order, sorted(order))
        self.assertIn('<span class="fmt-badge">', card.split("</div>")[0])
        self.assertRegex(card, r'<span class="v-corner"><span class="badge iterate"')
        self.assertNotIn("ad-tag", card)
        self.assertTrue(self.ctx.record_index[str(entry["ad"])]["label"].endswith("BAU"))
        rows = [{"ad_id": str(n), "ad_name": "c | ugc-video | creator-01 | bau | boot | lofi | 2026-03-0%d" % n, "date": "2026-03-01", "spend": 10.0} for n in (1, 2)]
        twins = panels.Ctx(rows=rows)
        self.assertFalse(twins.records[0]["label"].endswith("BAU"))
        self.assertIn('<span class="ad-tag">BAU</span>', panels.ad_card(twins, {"ad": "1", "ad_name": rows[0]["ad_name"]}))
        self.assertEqual(len(re.findall(r'class="m-row"', card)), 5)
        foot = card.split('<div class="ad-foot">')[1]
        self.assertEqual(foot.count('class="conf'), 1)
        self.assertIn("Early read · 6 similar ads", foot)
        self.assertIn('class="sentence"', foot)

    def test_a_non_judged_ad_has_no_verdict_chip_corner_and_no_tone(self):
        steady = next(r for r in self.ctx.records if not r["fatiguing"])
        card = panels.ad_card(self.ctx, {"ad": steady["id"], "ad_name": "x"})
        self.assertNotIn("v-corner", card)
        self.assertNotIn("data-tone", card)
        tiring = next(r for r in self.ctx.records if r["fatiguing"])
        self.assertIn('data-tone="warn"', panels.ad_card(self.ctx, {"ad": tiring["id"], "ad_name": "x"}))

    def test_the_card_tone_follows_the_verdict_and_tiring(self):
        for cls, tone in (("scale", "scale"), ("iterate", "warn")):
            self.assertIn('data-tone="%s"' % tone, panels.ad_card(self.ctx, self.entry_of(cls)), cls)
        pause = {"ad": "120000000002", "ad_name": "x", "verdict_id": "pause_weak"}
        self.assertIn('data-tone="pause"', panels.ad_card(self.ctx, pause))
        self.assertEqual(panels.card_tone("keep", True), "warn")
        self.assertEqual(panels.card_tone("keep", False), "")
        self.assertEqual(panels.card_tone("kill", True), "pause")
        self.assertEqual(panels.card_tone("scale", True), "scale")
        self.assertEqual(panels.card_tone(None, None), "")

    def test_a_card_with_no_preview_is_a_tile_with_the_format_word_and_no_preview_and_the_reason_for_screen_readers(self):
        card = panels.ad_card(self.ctx, self.entry_of("scale"))
        self.assertRegex(card, r'<div class="ph" role="img" aria-label="[^"]*preview unavailable: no preview fetched"[^>]*><span class="ph-format">[^<]+</span><span class="ph-note">No preview</span></div>')

    def test_the_card_css_matches_the_design(self):
        card = css_rule(".ad-card")
        for text in ("border-radius: var(--radius)", "overflow: hidden", "border: 1px solid var(--border)", "background: var(--surface)"):
            self.assertIn(text, card)
        self.assertIn("border-color: var(--hover-border)", css_rule(".ad-card:hover"))
        img = css_rule(".ad-img")
        self.assertIn("aspect-ratio: 3 / 4", img)
        self.assertIn("var(--surface-muted)", img)
        self.assertIn("height: 100%", css_rule(".ad-img svg.pv"))
        fmt = css_rule(".fmt-badge")
        for text in ("rgb(0 0 0 / .6)", "font: 500 10px", "padding: 2px 6px", "border-radius: 4px", "text-transform: capitalize", "bottom: 8px", "left: 8px"):
            self.assertIn(text, fmt)
        self.assertIn("top: 8px", css_rule(".v-corner"))
        self.assertIn("right: 8px", css_rule(".v-corner"))
        body = css_rule(".ad-body")
        self.assertIn("padding: 12px", body)
        title = css_rule(".ad-body h4")
        for text in ("font: 500 13px", "-webkit-line-clamp: 2", "min-height: 2lh"):
            self.assertIn(text, title)
        for text in ("font: 500 10px", "border-radius: 4px", "var(--surface-muted)"):
            self.assertIn(text, css_rule(".ad-tag"))
        pill = css_rule(".m-pill")
        for text in ("border-radius: 999px", "var(--heat, transparent)"):
            self.assertIn(text, pill)
        self.assertIn("justify-content: space-between", css_rule(".m-row"))
        self.assertIn("font-size: 12px", css_rule(".m-row"))

    def test_the_card_tones_have_light_and_dark_tokens(self):
        text = template_text()
        for token in ("--tone-scale-bd: #86efac;", "--tone-scale-bg: rgb(240 253 244 / .6);", "--tone-warn-bd: #fcd34d;", "--tone-warn-bg: rgb(255 251 235 / .6);"):
            self.assertIn(token, text)
        self.assertEqual(text.count("--tone-scale-bg: hsl(160 84% 51% / .06);"), 2)
        self.assertEqual(text.count("--tone-warn-bg: hsl(38 92% 50% / .06);"), 2)
        self.assertIn("border-left: 4px solid var(--danger)", css_rule('.ad-card[data-tone="pause"]'))

    def test_the_placeholder_has_the_gradient_and_hides_its_second_line_in_a_narrow_tile(self):
        ph = css_rule(".ph")
        self.assertIn("linear-gradient(135deg, hsl(258 92% 68% / .15), hsl(246 100% 50% / .15))", ph)
        self.assertIn("font: 700 14px", css_rule(".ph-format"))
        self.assertIn("font: 400 12px", css_rule(".ph-note"))
        self.assertRegex(template_text(), r"@container \(max-width: 139px\) \{ \.ph-note \{ display: none; \} \}")
        self.assertIn("container-type: inline-size", css_rule(".ad-img"))

    def test_one_card_is_used_in_every_list_and_strips_use_its_compact_form(self):
        for name in ("do_first", "all_ads", "head_tail"):
            html, _ = getattr(panels, name)(self.ctx)
            self.assertIn('<article class="ad-card" ', html, name)
            self.assertNotIn("pv-tile", html, name)
        board, _ = panels.verdict_board(self.ctx)
        self.assertIn('<article class="ad-card compact"', board)
        self.assertNotIn('<article class="ad-card" ', board)
        strip = panels.preview_strip(self.ctx, self.ctx.ads)
        self.assertEqual(strip.count('<article class="ad-card compact"'), 3)
        self.assertNotIn("pv-tile", strip)
        html, _ = panels.ready_briefs(self.ctx)
        self.assertNotIn("pv-grid", html)

    def test_the_compact_card_shows_label_spend_and_roas_and_opens_the_shared_dialog(self):
        card = panels.compact_card(self.ctx, "120000000001")
        self.assertEqual(re.findall(r'<span class="m-label">([^<]+)</span>', card), ["Spend", "ROAS"])
        self.assertIn('<div class="ad-img" data-open="120000000001">', card)
        self.assertNotIn("open-body", card)
        self.assertEqual(panels.compact_card(self.ctx, "nope"), "")

    def test_the_grid_columns_gaps_and_strip_columns(self):
        grid = css_rule(".ad-grid")
        self.assertIn("repeat(auto-fill, minmax(220px, 1fr))", grid)
        self.assertIn("gap: 12px", grid)
        strip = css_rule(".ad-grid.strip")
        self.assertIn("repeat(auto-fill, minmax(160px, 200px))", strip)
        self.assertIn("justify-content: start", strip)


class AllAdsViewTest(Fixture):
    def many(self, n):
        rows = [{"ad_id": str(1000 + i), "ad_name": "c%d | static | bau | p | t | 2026-03-01" % i, "date": "2026-03-01", "spend": 10.0 + i,
                 "impressions": 1000.0, "conversion_value": 40.0 + i, "conversions": 2.0} for i in range(n)]
        return panels.Ctx(rows=rows, currency="USD")

    def test_a_small_account_opens_as_a_grid_and_a_big_one_as_a_table_and_both_views_are_in_the_page(self):
        for count, view in ((12, "grid"), (60, "grid"), (61, "table")):
            html, _ = panels.all_ads(self.many(count))
            self.assertIn('<div class="allads" data-view="%s">' % view, html, count)
            self.assertEqual(html.count('class="view-grid"'), html.count('class="view-table"'))
            self.assertGreaterEqual(html.count('class="view-table"'), 1)

    def test_the_switch_is_a_labelled_group_of_two_pressed_buttons_for_the_default_view(self):
        html, _ = panels.all_ads(self.many(12))
        group = re.search(r'<div class="view-switch" role="group" aria-label="View">(.*?)</div>', html, re.S).group(1)
        self.assertEqual(re.findall(r'<button type="button" class="seg-btn" aria-pressed="(\w+)" data-view-pick="(\w+)">(\w+)</button>', group),
                         [("true", "grid", "Grid"), ("false", "table", "Table")])
        html, _ = panels.all_ads(self.many(61))
        self.assertIn('aria-pressed="true" data-view-pick="table"', html)

    def test_the_table_lists_every_ad_with_its_numbers_right_aligned_and_the_label_opening_the_ad(self):
        ctx = self.many(70)
        html, _ = panels.all_ads(ctx)
        table = re.search(r'<div class="view-table">(.*?)</div></section>', html, re.S).group(1)
        self.assertEqual(table.count("<tr data-ad="), 70)
        self.assertEqual(re.findall(r"<th[^>]*>([^<]*)</th>", table), ["Ad", "Format", "Verdict", "Spend", "ROAS", "CPA", "CTR", "Hook rate"])
        self.assertEqual(len(re.findall(r'<th class="num">', table)), 5)
        self.assertIn('<td class="adname"><button type="button" class="link" data-open="1000">', table)
        row = re.search(r"<tr data-ad=\"1000\">(.*?)</tr>", table, re.S).group(1)
        self.assertIn('<td class="num" data-label="ROAS">4.00x</td>', row)
        self.assertEqual(row.count('class="num"'), 5)

    def test_the_grid_view_keeps_its_cards_capped_and_the_rest_in_the_compact_list(self):
        html, _ = panels.all_ads(self.many(20))
        grid = re.search(r'<div class="view-grid">(.*?)</div><div class="view-table">', html, re.S).group(1)
        self.assertEqual(grid.count('<article class="ad-card" '), panels.TOP_N_CARDS)
        self.assertIn("more ads (compact list)", grid)

    def test_the_switch_is_hidden_without_the_script_and_the_other_view_is_hidden(self):
        self.assertIn("display: none", css_rule(".view-switch"))
        self.assertIn("display: inline-flex", css_rule(".js .view-switch"))
        text = template_text()
        self.assertIn(".allads .view-table { display: none; }", text)
        self.assertIn('.js .allads[data-view="table"] .view-table { display: block; }', text)
        self.assertIn('.js .allads[data-view="table"] .view-grid { display: none; }', text)
        self.assertNotIn('\n.allads[data-view="table"] .view-grid', text)

    def test_the_page_data_carries_the_default_view_for_the_script(self):
        _, data = page_data(report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, currency="USD"))
        self.assertEqual(data["defaults"]["view"], "grid")

    @unittest.skipUnless(HAS_NODE, "node is not installed")
    def test_the_view_lives_in_the_link_only_when_it_is_not_the_default(self):
        html = report.build_html(rows=self.rows, verdicts=self.verdicts, grade=self.grade, currency="USD")
        out = node_run(html, "var d = {group: 'verdict', sort: 'stake', view: 'grid'}; var s = CR.emptyState(d); var plain = CR.toHash('t', s, d);"
                             "s.view = 'table'; var h = CR.toHash('t', s, d); var back = CR.fromHash(h, d).view;"
                             "var bad = CR.fromHash('#t?view=bogus', d).view; var t = {group: 'verdict', sort: 'stake', view: 'table'};"
                             "console.log(JSON.stringify([plain, h, back, bad, CR.emptyState(t).view, CR.toHash('t', CR.emptyState(t), t)]));")
        self.assertEqual(json.loads(out), ["t", "t?view=table", "table", "grid", "table", "t"])

    def test_the_script_builds_the_table_view_when_it_regroups_the_gallery(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        for text in ("adsTable(", 'el("div", "view-table")', 'el("div", "view-grid")', "data-view-pick", 'setAttribute("data-view", state.view)'):
            self.assertIn(text, script)


class TableDesignTest(Fixture):
    def test_the_header_row_stays_in_view_and_reads_small_uppercase_and_spaced(self):
        head = css_rule("thead th")
        for text in ("position: sticky", "top: 0", "font: 600 11px", "letter-spacing: 0.06em", "text-transform: uppercase", "color-mix(in srgb, var(--text) 80%, transparent)"):
            self.assertIn(text, head)

    def test_rows_are_13px_with_a_soft_divider_a_hover_tint_and_right_aligned_tabular_numbers(self):
        self.assertIn("font-size: 13px", css_rule("table"))
        self.assertIn("border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent)", css_rule("th, td"))
        self.assertIn("background: var(--surface-muted)", css_rule("tbody tr:hover td"))
        numbers = css_rule("td.num, th.num")
        self.assertIn("text-align: right", numbers)
        self.assertIn("tabular-nums", numbers)
        self.assertIn("text-align: left", css_rule("th, td"))

    def test_a_long_table_scrolls_inside_its_frame_so_the_sticky_header_works_and_a_short_one_does_not(self):
        self.assertIn("max-height: 70vh", css_rule(".scroll.tall"))
        short = panels.table([("A", False)], ["<tr><td>x</td></tr>"] * panels.TALL_ROWS)
        long = panels.table([("A", False)], ["<tr><td>x</td></tr>"] * (panels.TALL_ROWS + 1))
        self.assertIn('<div class="scroll">', short)
        self.assertIn('<div class="scroll tall">', long)

    def test_printing_unfreezes_a_tall_table(self):
        self.assertIn(".scroll, .scroll.tall { overflow: visible; max-height: none;", template_text())

    def test_the_gap_list_is_a_table_with_the_numbers_the_heatmap_uses(self):
        mix = run_json("creative-mix", "mix.py")
        ctx = panels.Ctx(rows=self.rows, verdicts=self.verdicts, grade=self.grade, mix=mix, currency="USD")
        html, _ = panels.gap_list(ctx)
        self.assertIn('<th>Gap</th><th>Why test it</th>', html)
        self.assertEqual(len(re.findall(r'<tr class="gap" data-gap="\d+">', html)), len(mix["gaps"]))
        self.assertNotIn("<li", html)

    def test_the_scorecards_and_ways_to_improve_use_the_same_table(self):
        for html, _ in (panels.ways_to_improve(self.ctx), panels.format_scorecard(panels.Ctx(rows=self.rows, mix=run_json("creative-mix", "mix.py"), currency="USD"))):
            self.assertIn('<div class="scroll', html)
            self.assertIn("<thead>", html)


class DialogDesignTest(Fixture):
    def test_the_dialog_is_wide_scrolls_inside_and_has_a_header_with_the_name_the_chip_and_close(self):
        dialog = css_rule("dialog.ad-dialog")
        for text in ("max-width: 1024px", "width: calc(100% - 32px)", "max-height: 90vh", "padding: 0", "overflow: auto"):
            self.assertIn(text, dialog)
        self.assertIn("padding: 20px 24px", css_rule(".dlg-head"))
        shell = re.search(r"<dialog[^>]*>.*?</dialog>", self.html, re.S).group(0)
        for text in ('id="ad-dialog-title"', 'class="dlg-sub"', 'class="dlg-chip"', 'data-action="close-dialog"'):
            self.assertIn(text, shell)

    def test_the_open_view_has_the_preview_and_a_numbers_table_side_by_side_from_768px(self):
        card = panels.ad_card(self.ctx, self.verdicts["ads"][0])
        body = card.split('<div class="open-body"')[1]
        media, main = body.split('<div class="ob-main">')
        self.assertIn('class="ob-media"', media)
        self.assertRegex(main, r'<h5>Numbers</h5><dl class="ob-dl"><dt>Spend</dt><dd>[^<]+</dd>')
        for label in ("ROAS", "CPA", "CTR", "Hook rate", "Impressions", "Age", "Ad ID"):
            self.assertIn("<dt>%s</dt>" % label, main)
        self.assertLess(main.index("<h5>Numbers</h5>"), main.index("<h5>Verdict</h5>"))
        self.assertLess(main.index("<h5>Verdict</h5>"), main.index("<h5>How to improve</h5>"))
        self.assertRegex(template_text(), r"@media \(min-width: 768px\) \{[^@]*dialog\.ad-dialog \.ob-top \{ display: grid; grid-template-columns: minmax\(0, 480px\) minmax\(0, 1fr\)")
        self.assertIn("max-width: 480px", css_rule(".open-body .ob-media svg.pv, .open-body .ob-media .ph"))
        self.assertIn("border-radius: 12px", css_rule(".open-body .ob-media svg.pv, .open-body .ob-media .ph"))

    def test_the_numbers_table_leaves_out_video_rates_for_a_still_and_reads_n_a_with_the_reason(self):
        still = next(a for a in self.ctx.ads if "video" not in str(a["format"]))
        card = panels.ad_card(self.ctx, {"ad": still["ad_id"], "ad_name": still["ad_name"]})
        body = card.split('<div class="open-body"')[1]
        self.assertNotIn("<dt>Hook rate</dt>", body)
        self.assertIn("<dt>CPM</dt>", body)
        rows = [{"ad_id": "1", "ad_name": "x | static | bau", "date": "2026-03-01", "spend": 5.0, "impressions": 100.0}]
        card = panels.ad_card(panels.Ctx(rows=rows, currency="USD"), {"ad": "1", "ad_name": "x | static | bau"})
        self.assertIn('<dt>ROAS</dt><dd><span class="na" title="missing purchase value">n/a</span></dd>', card)

    def test_the_open_body_carries_the_title_the_raw_name_and_the_verdict_chip_for_the_header(self):
        card = panels.ad_card(self.ctx, self.verdicts["ads"][0])
        self.assertRegex(card, r'<div class="open-body" data-title="[^"]+" data-raw="durability-test \| ugc-video[^"]*"><span class="ob-chip"><span class="badge ')

    def test_the_script_fills_the_header_and_still_closes_on_escape_and_backdrop_and_returns_focus(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        for text in ('data-title', 'data-raw', ".dlg-sub", ".dlg-chip", ".ob-chip", 'event.target === dialog', "opener.focus()", "showModal"):
            self.assertIn(text, script)


DIALOG_JS = r'''
var out = { calls: [] }, listeners = {}, dlgListeners = {};
var tabNode = { id: "t", hidden: false, closest: function () { return null; }, addEventListener: function () {}, getAttribute: function () { return "#t"; },
  setAttribute: function () {}, removeAttribute: function () {}, querySelector: function () { return null; } };
var parent = { removeChild: function (n) { out.calls.push("removed " + n.name); } };
var chipChild = { name: "chipChild" };
var chip = { name: "chip", firstElementChild: chipChild, parentNode: parent };
var raw = { name: "raw", parentNode: parent };
var clone = { querySelector: function (sel) { return sel === ".ob-chip" ? chip : sel === ".raw-name" ? raw : null; } };
var body = { getAttribute: function (k) { return { "data-title": "Label X", "data-raw": "raw | name" }[k] || null; }, cloneNode: function () { return clone; } };
var card = { getAttribute: function () { return "42"; }, querySelector: function (sel) { return sel === ".open-body" ? body : sel === "h4" ? { textContent: "Fallback" } : null; },
  closest: function () { return null; } };
var titleEl = {}, sub = {}, slot = { textContent: "x", appendChild: function (n) { out.slot = n.name; } };
var holder = { textContent: "", appendChild: function (n) { out.holder = n === clone; } };
var focused = 0;
var dialog = { showModal: function () { out.calls.push("showModal"); }, close: function () { dlgListeners.close(); },
  addEventListener: function (t, fn) { dlgListeners[t] = fn; },
  querySelector: function (sel) { return sel === ".dlg-body" ? holder : sel === ".dlg-sub" ? sub : sel === ".dlg-chip" ? slot : null; } };
var data = { ads: [], presets: [], names: {}, weak_steps: [], currency: "USD", unit_note: "", top_n: 8, defaults: { group: "none", sort: "stake", view: "grid" }, verdict_labels: {}, verdict_tips: {} };
var root = { className: "", setAttribute: function () {}, getAttribute: function () { return null; } };
global.window = { localStorage: null, matchMedia: function () { return { matches: false }; }, addEventListener: function () {}, scrollTo: function () {}, innerWidth: 1200 };
global.history = { replaceState: function () {} };
global.location = { hash: "" };
global.document = { documentElement: root, activeElement: null,
  querySelectorAll: function (sel) { return sel === "section.tab" ? [tabNode] : []; },
  querySelector: function (sel) { return sel === "svg" ? { namespaceURI: "" } : null; },
  getElementById: function (id) {
    return id === "ad-dialog" ? dialog : id === "ad-data" ? { textContent: JSON.stringify(data) } : id === "ad-dialog-title" ? titleEl
      : id === "ad-pool" ? { content: { querySelectorAll: function () { return [card]; } } } : null;
  },
  addEventListener: function (type, fn) { (listeners[type] = listeners[type] || []).push(fn); }, createElementNS: function () { return {}; } };
new Function(SCRIPT)();
function click(target) { listeners.click.forEach(function (fn) { fn({ target: target, preventDefault: function () { out.calls.push("preventDefault"); } }); }); }
var opener = { focus: function () { focused += 1; }, closest: function (sel) { return sel.indexOf("data-open") >= 0 ? opener : null; }, getAttribute: function () { return "42"; } };
click(opener);
out.title = titleEl.textContent; out.sub = sub.textContent;
dialog.close();
out.focused = focused;
var summary = { closest: function (sel) { return sel.indexOf("open-ad > summary") >= 0 ? summary : sel === ".ad-card" ? card : null; }, focus: function () { focused += 1; } };
out.calls.length = 0;
click(summary);
out.summaryCalls = out.calls.slice();
console.log(JSON.stringify({ title: out.title, sub: out.sub, slot: out.slot, holder: out.holder, focusedAfterClose: out.focused, summaryCalls: out.summaryCalls }));
'''


class ReviewFixTest(Fixture):
    def all_class_verdicts(self):
        ids = ("scale", "keep", "iterate", "check_cut", "pause_weak", "too_early", "cant_judge")
        rows = [{"ad_id": str(n), "ad_name": "c%d | static | bau" % n, "date": "2026-03-01", "spend": 100.0 - n, "impressions": 1000.0,
                 "conversion_value": 50.0, "conversions": 2.0} for n in range(len(ids))]
        entries = [{"ad": str(n), "ad_name": rows[n]["ad_name"], "verdict_id": vid, "spend_at_stake": 100.0 - n} for n, vid in enumerate(ids)]
        return panels.Ctx(rows=rows, verdicts={"ads": entries, "summary": {}}, currency="USD")

    def test_the_board_is_one_strip_per_verdict_money_at_risk_first(self):
        html, _ = panels.verdict_board(self.all_class_verdicts())
        order = re.findall(r'<section class="v-row v-row-(\w+)">', html)
        self.assertEqual(order, ["kill", "iterate", "check", "scale", "keep", "early", "cant"])
        self.assertEqual(panels.BOARD_ORDER, ("kill", "iterate", "check", "scale", "keep", "early", "cant"))

    def test_a_verdict_with_no_ads_is_one_muted_line_and_no_row(self):
        ctx = panels.Ctx(rows=self.rows[:3], verdicts={"ads": [dict(self.verdicts["ads"][0], verdict_id="keep")], "summary": {}}, currency="USD")
        html, _ = panels.verdict_board(ctx)
        self.assertEqual(re.findall(r'<section class="v-row v-row-(\w+)">', html), ["keep"])
        self.assertEqual(html.count('class="muted board-none"'), 6)
        self.assertIn("Pause: no ads.", html)

    def test_the_board_uses_only_compact_cards_so_it_stays_short(self):
        board, _ = panels.verdict_board(self.ctx)
        self.assertNotIn('<article class="ad-card" ', board)
        rows = re.findall(r'<section class="v-row .*?</section>', board, re.S)
        self.assertLessEqual(len(rows), 7)
        for row in rows:
            self.assertLessEqual(row.count('<article class="ad-card compact"'), self.ctx.top_n)
        strip = css_rule(".v-strip")
        for text in ("overflow-x: auto", "scroll-snap-type: x mandatory", "display: flex"):
            self.assertIn(text, strip)
        self.assertIn("scroll-snap-align: start", css_rule(".v-strip .ad-card"))
        self.assertIn("flex-direction: column", css_rule(".board"))
        self.assertIn("flex: 0 0 168px", css_rule(".v-strip .ad-card"))
        self.assertIn("aspect-ratio: 4 / 3", css_rule(".v-strip .ad-card .ad-img"))
        tallest = max(r.count('<article class="ad-card compact"') for r in rows)
        self.assertLessEqual(tallest, self.ctx.top_n)

    def test_the_pause_strip_says_check_first_once_not_on_every_card(self):
        ctx = self.all_class_verdicts()
        board, _ = panels.verdict_board(ctx)
        pause = re.search(r'<section class="v-row v-row-kill">.*?</section>', board, re.S).group(0)
        self.assertEqual(pause.count("<b>Check first:</b> " + panels.esc(panels.PAUSE_CHECK)), 1)
        self.assertLess(pause.index("Check first:"), pause.index('class="v-strip"'))
        self.assertNotIn("Check first:", pause.split('class="v-strip"')[1])
        self.assertNotIn("Check first:", re.search(r'<section class="v-row v-row-iterate">.*?</section>', board, re.S).group(0))
        many = panels.Ctx(rows=self.rows, verdicts={"ads": [dict(e, verdict_id="pause_x") for e in self.verdicts["ads"][:3]], "summary": {}}, currency="USD")
        board, _ = panels.verdict_board(many)
        self.assertEqual(board.count("Check first:"), 1)

    def test_a_chip_on_a_preview_is_opaque_in_both_themes_while_inline_chips_stay_tinted(self):
        self.assertIn("background: var(--surface)", css_rule(".v-corner .badge"))
        text = template_text()
        self.assertGreater(text.index(".v-corner .badge {"), text.index(".badge.cant {"))
        self.assertIn("background: var(--v-scale-bg)", css_rule(".badge.scale"))

    def test_compact_cards_are_small_and_one_line(self):
        self.assertIn("aspect-ratio: 1 / 1", css_rule(".ad-card.compact .ad-img"))
        self.assertNotIn(".ad-card.compact .ad-body h4", template_text())
        h4 = css_rule(".ad-body h4")
        self.assertIn("-webkit-line-clamp: 2", h4)
        self.assertIn("min-height: 2lh", h4)
        self.assertIn('title="', panels.compact_card(self.ctx, "120000000001"))

    def test_the_dialog_sits_in_the_middle_of_the_screen(self):
        dialog = css_rule("dialog.ad-dialog")
        self.assertIn("margin: auto", dialog)
        self.assertIn("inset: 0", dialog)

    def test_a_verdict_sentence_and_card_spend_driver_do_not_repeat_the_spend_row(self):
        ad = self.ctx.ads[0]
        entry = {"ad": ad["ad_id"], "ad_name": ad["ad_name"]}
        same = panels.ad_card(self.ctx, entry, driver="Spend at stake: %s" % self.ctx.money(ad["spend"]))
        other = panels.ad_card(self.ctx, entry, driver="Spend at stake: USD 1")
        cumulative = panels.ad_card(self.ctx, entry, driver="Cumulative spend: 40%")
        self.assertNotIn('class="driver"', same)
        self.assertIn('class="driver">Spend at stake: USD 1', other)
        self.assertIn('class="driver">Cumulative spend: 40%', cumulative)

    def test_the_footer_confidence_and_group_size_are_one_chip(self):
        entry = {"ad": "1", "ad_name": "a", "verdict_id": "scale", "confidence": "Confident", "confidence_reason": "r", "group_size": 29, "sentence": "S."}
        card = panels.ad_card(panels.Ctx(verdicts={"ads": [entry]}), entry)
        self.assertEqual(card.split('<div class="ad-foot">')[1].count('class="conf'), 1)
        self.assertIn(">Confident · 29 similar ads</span>", card)
        self.assertEqual(panels._age_text(None, None), "n/a (age is not in the data)")

    def test_the_age_reads_without_nested_brackets(self):
        text = panels._age_text(29, "first delivery in window (older ads may be understated)")
        self.assertEqual(text, "29 days, counted from its first delivery in this window (it may be older)")
        self.assertNotIn("((", text)
        card = panels.ad_card(self.ctx, self.verdicts["ads"][0])
        self.assertIn("counted from its first delivery in this window (it may be older)", card)
        self.assertNotIn("(first delivery in window (", card)
        self.assertEqual(panels._age_text(5, "its creation date"), "5 days, counted from its creation date")
        self.assertNotIn("(", panels._age_text(5, "created (as stated)"))

    @unittest.skipUnless(HAS_NODE, "node is not installed")
    def test_opening_an_ad_fills_the_dialog_header_returns_focus_on_close_and_the_summary_opens_the_dialog_too(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dialog.js"
            path.write_text("var SCRIPT = %s;\n%s" % (json.dumps(script), DIALOG_JS))
            done = subprocess.run(["node", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        got = json.loads(done.stdout)
        self.assertEqual((got["title"], got["sub"]), ("Label X", "raw | name"))
        self.assertEqual((got["slot"], got["holder"]), ("chipChild", True))
        self.assertEqual(got["focusedAfterClose"], 1)
        self.assertEqual(got["summaryCalls"], ["preventDefault", "removed chip", "removed raw", "showModal"])

    def test_the_chip_escapes_a_tooltip_with_markup_in_it(self):
        with mock.patch.dict(interact.VERDICT_TIPS, {"check": 'a <b>"x"</b> & y'}):
            chip = panels.verdict_chip("check")
        self.assertNotIn("<b>", chip)
        self.assertIn('title="a &lt;b&gt;&quot;x&quot;&lt;/b&gt; &amp; y"', chip)


class HeatEdgeTest(unittest.TestCase):
    def test_a_value_two_ads_share_is_never_tinted_and_the_rest_rank_among_themselves(self):
        self.assertEqual(interact.heat_tints({"a": 1.0, "b": 1.0, "c": 5.0}, False), {"a": None, "b": None, "c": None})
        self.assertEqual(interact.heat_tints({"a": 0.0, "b": 0.0, "c": 0.0, "d": 9.0}, False), {"a": None, "b": None, "c": None, "d": None})
        tints = interact.heat_tints({"a": 1.0, "b": 1.0, "c": 5.0, "d": 7.0, "e": 9.0}, False)
        self.assertEqual((tints["a"], tints["b"], tints["d"]), (None, None, None))
        self.assertEqual(tints["c"], "rgb(220 38 38 / 0.60)")
        self.assertEqual(tints["e"], "rgb(34 197 94 / 0.60)")

    def test_a_cost_of_zero_or_less_is_left_out_of_the_heat_not_ranked_best(self):
        ads = [{"ad_id": "a", "cpa": 0.0, "cpm": -1.0}, {"ad_id": "b", "cpa": 10.0, "cpm": 5.0}, {"ad_id": "c", "cpa": 20.0, "cpm": 9.0}]
        heat = interact.heat_map(ads)
        self.assertIsNone(heat["cpa"]["a"])
        self.assertEqual(heat["cpa"]["b"], "rgb(34 197 94 / 0.60)")
        self.assertEqual(heat["cpa"]["c"], "rgb(220 38 38 / 0.60)")
        self.assertIsNone(heat["cpm"]["a"])

    def test_a_number_that_is_not_finite_is_not_ranked(self):
        tints = interact.heat_tints({"a": math.nan, "b": 1.0, "c": 2.0, "d": math.inf}, False)
        self.assertEqual((tints["a"], tints["d"]), (None, None))
        self.assertEqual(tints["b"], "rgb(220 38 38 / 0.60)")
        self.assertEqual(tints["c"], "rgb(34 197 94 / 0.60)")


class DuplicateIdLabelTest(unittest.TestCase):
    def test_a_repeated_id_does_not_misalign_the_fields_of_the_ads_after_it(self):
        recs = [record(1, 10, label="x", collection="a"), record(1, 10, label="x", collection="b"), record(2, 10, label="x", collection="c")]
        got = interact.unique_labels(recs)
        self.assertEqual(got["2"], "x · c")


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


class OneBasisTest(unittest.TestCase):
    RECS = [record("a", 100, verdict="keep", conversions=10.0, conversion_value=300.0),
            record("b", 100, verdict="keep", conversions=5.0, conversion_value=None),
            record("c", 100, verdict="keep", conversions=None, conversion_value=300.0)]

    def test_roas_and_cpa_divide_over_every_ad_and_a_missing_value_counts_as_none(self):
        total = interact.totals_of(self.RECS, 300.0)
        self.assertAlmostEqual(total["roas"], 600 / 300)
        self.assertAlmostEqual(total["cpa"], round(300 / 15, 2))
        self.assertEqual(total["roas_text"], "2.00x")
        self.assertEqual(total["cpa_text"], "%.2f" % (300 / 15))

    def test_no_ad_count_suffix_is_ever_added(self):
        total = interact.totals_of(self.RECS, 300.0)
        self.assertNotIn(" ads)", total["roas_text"] + total["cpa_text"])
        self.assertNotIn("roas_suffix", total)
        self.assertNotIn("cpa_n", total)

    def test_roas_and_cpa_are_na_only_when_no_ad_has_any_value_or_purchase(self):
        bare = [record("a", 100, verdict="keep"), record("b", 50, verdict="keep")]
        total = interact.totals_of(bare, 150.0)
        self.assertIsNone(total["roas"])
        self.assertIsNone(total["cpa"])
        self.assertEqual(total["roas_text"], "n/a (missing purchase value)")
        self.assertEqual(total["cpa_text"], "n/a (missing purchases)")
        zero = interact.totals_of([record("a", 100, conversions=0.0, conversion_value=0.0)], 100.0)
        self.assertEqual(zero["cpa_text"], "n/a (zero purchases)")

    def test_the_unfiltered_summary_equals_the_kpi_tiles_when_some_ads_have_no_value(self):
        rows = [dict(r, conversion_value=None, conversions=None) if r["ad_id"] in ("c", "d") else r for r in PARTIAL_ROWS]
        ctx = panels.Ctx(rows=rows, currency="USD")
        total = interact.totals_of(ctx.records, None, ctx.money)
        html, _ = panels.kpi_strip(ctx)
        tile = {name: value for name, value in re.findall(r'<p class="kpi-name">([^<]*)</p>.*?<p class="kpi-value">([^<]*)</p>', html, re.S)}
        self.assertEqual(total["roas_text"], tile["ROAS"])
        self.assertEqual(total["cpa_text"], tile["CPA (USD)"])


class CoverageNoteTest(unittest.TestCase):
    RECS = OneBasisTest.RECS

    def test_a_partly_recorded_operand_adds_a_plain_coverage_note_to_the_summary(self):
        total = interact.totals_of(self.RECS, 300.0)
        self.assertEqual(total["roas_note"], "value recorded on 2 of 3 ads")
        self.assertEqual(total["cpa_note"], "purchases recorded on 2 of 3 ads")
        self.assertEqual(total["roas_text"], "2.00x")

    def test_a_fully_recorded_or_fully_missing_operand_adds_no_note(self):
        full = [record("a", 100, conversions=1.0, conversion_value=5.0), record("b", 50, conversions=1.0, conversion_value=5.0)]
        done = interact.totals_of(full, 150.0)
        self.assertEqual((done["roas_note"], done["cpa_note"]), ("", ""))
        bare = interact.totals_of([record("a", 100)], 100.0)
        self.assertEqual((bare["roas_note"], bare["cpa_note"]), ("", ""))

    def test_the_group_header_line_carries_the_note_in_the_page(self):
        rows = [dict(r, conversion_value=None, conversions=None) if r["ad_id"] in ("c", "d") else r for r in PARTIAL_ROWS]
        page = report.build_html(rows=rows, currency="USD", title="Acme")
        line = re.search(r'<p class="group-sub">.*?</p>', page).group(0)
        self.assertIn("value recorded on 2 of 4 ads", line)
        self.assertIn("purchases recorded on 2 of 4 ads", line)


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
        self.assertEqual(ids, ["kpis", "time", "money-by-format", "do-first", "improve", "funnel", "pareto", "head-tail", "board", "fatigue",
                               "ad-age", "launches", "all-ads", "format-scorecard", "format-benchmarks", "formats-over-time", "spend-return", "hook-hold", "retention", "ad-types", "heatmap", "stage-heatmap", "no-creative", "segments",
                               "gaps", "briefs", "copy", "prompts"])

    def test_with_scripts_off_the_default_grouping_is_in_the_page_and_nothing_is_hidden(self):
        gallery = re.search(r'id="panel-all-ads".*?</section>\s*</section>', self.html, re.S).group(0)
        names = re.findall(r'<section class="group" data-group="([^"]+)"', gallery)
        self.assertEqual(names, [str(g["key"] if g["key"] is not None else "unknown") for g in interact.group_subtotals(self.ctx.records, "verdict")])
        for text in ("ads", "of spend", "ROAS", "CPA"):
            self.assertIn(text, gallery)
        self.assertIn("more", gallery)
        for tag in re.findall(r"<[a-z][^>]*>", re.search(r"<main[^>]*>(.*?)</main>", self.html, re.S).group(1)):
            self.assertNotRegex(tag, r"(?<![-\w])hidden\b")
            self.assertNotRegex(tag, r'style="[^"]*(display\s*:\s*none|visibility\s*:\s*hidden)')
        self.assertRegex(self.html, r"\.filterbar \{[^}]*display: none")
        self.assertRegex(self.html, r"\.js \.filterbar \{[^}]*display: flex")

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
        bar = re.search(r'<div class="filterbar".*?(?=<main)', self.html, re.S).group(0)
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

    def test_the_filter_row_opens_the_content_column_beside_the_tabs_and_is_not_in_the_header(self):
        self.assertNotIn("filterbar", re.search(r'<header class="top">.*?</header>', self.html, re.S).group(0))
        self.assertLess(self.html.index('<nav class="tabs"'), self.html.index('class="filterbar"'))
        self.assertLess(self.html.index('class="filterbar"'), self.html.index("<main"))

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
        html, _ = panels.all_ads(self.ctx)
        cards = re.findall(r'<article class="ad-card" data-ad="[^"]+"[^>]*>.*?</article>', html, re.S)
        self.assertTrue(cards)
        for card in cards:
            self.assertEqual(card.count('<details class="open-ad">'), 1)
            self.assertIn("<summary>Open this ad</summary>", card)
            body = re.search(r'<div class="open-body"[^>]*>(.*)</div></details>', card, re.S).group(1)
            for text in ("Graded metrics", "Funnel for this ad", "Technical detail", "Age", "How to improve", "Confidence"):
                self.assertIn(text, body, text)
        card = next(c for c in cards if 'data-ad="120000000001"' in c)
        body = re.search(r'<div class="open-body"[^>]*>(.*)</div></details>', card, re.S).group(1)
        for text in ("among your weakest", "among your best", "Hook rate", "25.52%", "Impressions", "3-second plays", "Refresh it, keep the idea",
                     "29 days", "Change the first 3 seconds", "Also weak: hold rate, CTR, add-to-cart rate."):
            self.assertIn(text, body, text)
        self.assertRegex(body, r'<(svg|div) class="(pv|ph) big"')

    def test_the_preview_in_the_open_view_is_larger_than_the_card_thumbnail(self):
        self.assertRegex(self.html, r"\.open-body \.ob-media svg\.pv, \.open-body \.ob-media \.ph \{[^}]*max-width: 480px")

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

    def test_the_filter_row_has_group_sort_and_previews_only_controls(self):
        gallery = re.search(r'<div class="filterbar".*?(?=<main)', self.html, re.S).group(0)
        self.assertEqual(gallery.count('data-action="group"'), 2)
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

    def test_the_browser_adds_the_same_coverage_note_as_python(self):
        recs = OneBasisTest.RECS
        py = interact.totals_of(recs, 300.0)
        js = json.loads(node_run(self.html, "console.log(JSON.stringify(CR.summary(%s, 3, 300)));" % json.dumps(recs)))
        self.assertEqual((js["roas_note"], js["cpa_note"]), (py["roas_note"], py["cpa_note"]))
        done = json.loads(node_run(self.html, "console.log(JSON.stringify(CR.summary([{spend: 5, conversions: 1, conversion_value: 2}], 1, 5)));"))
        self.assertEqual((done["roas_note"], done["cpa_note"]), ("", ""))

    def test_summary_divides_over_every_ad_with_no_count_suffix(self):
        body = ("var ads = [{spend: 100, conversions: 10, conversion_value: 300}, {spend: 100, conversions: null, conversion_value: null}];"
                "var s = CR.summary(ads, 2, 200); console.log(JSON.stringify(s));")
        out = json.loads(node_run(self.html, body))
        self.assertAlmostEqual(out["roas"], 1.5)
        self.assertAlmostEqual(out["cpa"], 20.0)
        self.assertEqual(out["roas_text"], "1.50x")
        self.assertEqual(out["cpa_text"], "20.00")
        self.assertNotIn("roas_suffix", out)

    def test_the_filter_count_adds_the_search_and_every_chip_and_view(self):
        body = ("var s = CR.emptyState(); var none = CR.activeCount(s); s.q = 'x'; s.facets.format = ['static', 'video']; s.facets.verdict = ['pause'];"
                "s.fat = true; s.top = 5; var many = CR.activeCount(s);"
                "console.log(JSON.stringify({none: none, many: many, active: CR.active(s)}));")
        self.assertEqual(json.loads(node_run(self.html, body)), {"none": 0, "many": 6, "active": True})

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
        for field in ("roas_text", "cpa_text"):
            self.assertEqual(js[field], py[field], field)
        self.assertAlmostEqual(js["roas"], py["roas"], places=4)
        self.assertAlmostEqual(js["cpa"], py["cpa"], places=2)
        self.assertEqual(py["roas_text"], "2.00x")
        self.assertEqual(py["cpa_text"], "%.2f" % (300 / 15))


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
        self.assertIn("(1 of 1 video ads)", tile)
        hold = re.search(r'<div class="kpi[^"]*"><p class="kpi-name">Hold rate.*?</div></div>', html, re.S).group(0)
        self.assertIn("40.00%", hold)
        self.assertIn("(1 of 1 video ads)", hold)

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
        body = card.split('<div class="open-body"')[1]
        self.assertLess(body.index("Confidence"), body.index("Technical detail"))
        self.assertLess(body.index("How to improve"), body.index("Technical detail"))
        tech = re.search(r'<details class="tech"><summary>Technical detail[^<]*</summary>(.*?)</details>', body, re.S).group(1)
        self.assertIn("top quartile", tech)
        self.assertNotIn("compared with format", body.split("Technical detail")[0])

    def test_the_open_view_is_two_columns_on_a_wide_screen_only(self):
        self.assertRegex(self.html, r"@media \(min-width: 768px\) \{[^@]*dialog\.ad-dialog \.ob-top \{[^}]*grid-template-columns")
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
