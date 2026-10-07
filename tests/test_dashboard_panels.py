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
sys.path.insert(0, str(SCRIPT))

import creative_metrics as cm  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
from previews import Previews  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a730000001049444154789c63a8b17a0b440c100a002c1e068d70420d590000000049454e44ae426082")
DATA_PANELS = [(pid, fn) for _, _, tab in panels.TABS for pid, _, _, fn in tab if fn.__name__ != "panel"]
PLACEHOLDERS = [(pid, fn) for _, _, tab in panels.TABS for pid, _, _, fn in tab if fn.__name__ == "panel"]
TAB_ORDER = ["Overview analysis", "Pareto", "Keep / kill", "Format", "White space", "Briefing"]
BALANCED = ("section", "table", "svg", "div", "ul", "thead", "tbody", "tr", "td", "th", "article", "details", "nav",
            "header", "footer", "main", "figure")


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.attrs = [], [], []

    def handle_starttag(self, tag, attrs):
        self.attrs.append((tag, dict(attrs)))
        if tag in BALANCED:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in BALANCED:
            if not self.stack or self.stack[-1] != tag:
                self.errors.append("unexpected </%s> with %s open" % (tag, self.stack[-3:]))
            else:
                self.stack.pop()


def ad_row(ad_id, name, spend, value, day="2026-03-01", **extra):
    row = {"ad_id": ad_id, "ad_name": name, "date": day, "spend": float(spend), "impressions": 10000.0,
           "conversion_value": float(value), "conversions": 5.0}
    row.update(extra)
    return row


def acme_verdicts():
    out = subprocess.run([sys.executable, str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"), str(FIXTURE), "--json",
                          "--profile", str(ROOT / "examples" / "acme" / "brand-profile.md")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def acme_grade():
    out = subprocess.run([sys.executable, str(ROOT / "skills" / "creative-grader" / "scripts" / "grade.py"), str(FIXTURE), "--json"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


class PanelStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = acme_verdicts()
        cls.grade = acme_grade()
        cls.ctx = panels.Ctx(rows=cls.rows, verdicts=cls.verdicts, grade=cls.grade, currency="USD")

    def test_ten_data_panels_and_three_placeholders_exist(self):
        self.assertEqual(len(DATA_PANELS), 10)
        self.assertEqual(len(PLACEHOLDERS), 3)

    def test_every_panel_is_data_on_the_acme_inputs(self):
        for pid, fn in DATA_PANELS:
            html, state = fn(self.ctx)
            self.assertEqual(state, "data", pid)
            self.assertNotIn("Why this is empty", html, pid)

    def test_every_panel_is_a_labelled_empty_state_without_its_data(self):
        for pid, fn in DATA_PANELS:
            html, state = fn(panels.Ctx())
            self.assertEqual(state, "empty", pid)
            self.assertIn("Why this is empty:", html, pid)
            self.assertIn("How to get it:", html, pid)

    def test_panels_that_need_verdicts_are_empty_with_rows_alone(self):
        ctx = panels.Ctx(rows=self.rows)
        for pid in ("do-first", "board"):
            html, state = dict(DATA_PANELS)[pid](ctx)
            self.assertEqual(state, "empty", pid)
            self.assertIn("keep-or-kill", html)

    def test_panels_that_need_rows_are_empty_with_verdicts_alone(self):
        ctx = panels.Ctx(verdicts=self.verdicts)
        for pid in ("kpis", "time", "funnel", "pareto", "head-tail"):
            self.assertEqual(dict(DATA_PANELS)[pid](ctx)[1], "empty", pid)

    def test_tabs_four_to_six_say_not_built_in_this_version(self):
        for pid, fn in PLACEHOLDERS:
            html, state = fn(self.ctx)
            self.assertEqual(state, "empty", pid)
            self.assertIn("Not built in this version", html)

    def test_do_these_first_never_lists_an_ad_that_cannot_be_judged(self):
        cant = {"ad": "999", "ad_name": "ghost | static | house | bau | x | y | 2026-03-01", "verdict": "Can't judge",
                "verdict_id": "cant_judge", "spend_at_stake": 9e9, "confidence": "Early read", "sentence": "GHOSTSENTENCE"}
        verdicts = {"summary": {"do_first": [cant] + self.verdicts["summary"]["do_first"]}, "ads": []}
        html, state = panels.do_first(panels.Ctx(rows=self.rows, verdicts=verdicts))
        self.assertEqual(state, "data")
        self.assertNotIn("GHOSTSENTENCE", html)
        self.assertNotIn("Can&#x27;t judge", html)
        only_cant = {"summary": {"do_first": [cant]}, "ads": []}
        self.assertEqual(panels.do_first(panels.Ctx(verdicts=only_cant))[1], "empty")

    def test_real_do_first_has_no_cant_judge_and_is_capped_at_five(self):
        items = self.verdicts["summary"]["do_first"]
        self.assertLessEqual(len(items), 5)
        self.assertNotIn("cant_judge", {e["verdict_id"] for e in items})
        html, _ = panels.do_first(self.ctx)
        self.assertEqual(html.count('<article class="ad-card" '), len(items))

    def test_board_columns_carry_counts_and_every_pause_card_the_check_line(self):
        html, _ = panels.verdict_board(self.ctx)
        for name in ("Scale", "Keep", "Iterate", "Check before cutting", "Pause", "Too early", "Can&#x27;t judge"):
            self.assertIn(name, html)
        pauses = [e for e in self.verdicts["ads"] if e["verdict_id"].startswith("pause")]
        self.assertTrue(pauses)
        self.assertGreaterEqual(html.count("Check first:"), len(pauses))
        self.assertIn(panels.PAUSE_CHECK, panels.ad_card(self.ctx, {"ad": "1", "ad_name": "n", "verdict_id": "pause_fatigued"}))

    def test_board_shows_top_n_per_column_and_collapses_the_rest(self):
        ctx = panels.Ctx(rows=self.rows, verdicts=self.verdicts, top_n=2)
        html, _ = panels.verdict_board(ctx)
        keep = next(c for c in html.split('<div class="col col-')[1:] if c.startswith("keep"))
        self.assertEqual(keep.count('<article class="ad-card" '), 2)
        self.assertIn("more keep ads", keep)
        self.assertIn("N=2", html)
        self.assertIn("<details", keep)
        self.assertNotIn("<details open", keep)

    def test_thin_groups_note_is_shown_above_the_board(self):
        html, _ = panels.verdict_board(self.ctx)
        self.assertTrue(self.verdicts["summary"]["thin_groups"])
        self.assertIn("Small comparison groups", html)
        self.assertLess(html.index("Small comparison groups"), html.index('<div class="board">'))

    def test_fatigue_view_has_small_multiples_and_a_labelled_scatter(self):
        html, _ = panels.fatigue(self.ctx)
        self.assertIn("CTR by day", html)
        self.assertIn("Frequency by day", html)
        self.assertIn("Ad age (days)", html)
        self.assertIn("CTR change (%)", html)


class ChartTicksTest(unittest.TestCase):
    def test_a_narrow_chart_has_few_enough_date_ticks_not_to_collide(self):
        import charts
        labels = ["2026-03-%02d" % d for d in range(1, 31)]
        narrow = charts.combo_chart(labels, None, [float(i) for i in range(30)], "", "CTR (%)", "x", width=300, height=190)
        wide = charts.combo_chart(labels, None, [float(i) for i in range(30)], "", "CTR (%)", "x")
        ticks = lambda svg: len(re.findall(r"<text[^>]*text-anchor=\"middle\">\d\d-\d\d</text>", svg))
        self.assertLessEqual(ticks(narrow), 4)
        self.assertGreater(ticks(wide), ticks(narrow))


class LegendTest(unittest.TestCase):
    def test_pareto_names_both_lines_when_there_is_value(self):
        rows = [ad_row("a", "A", 100, 500), ad_row("b", "B", 80, 300), ad_row("c", "C", 60, 100)]
        html, _ = panels.pareto(panels.Ctx(rows=rows, currency="USD"))
        self.assertIn('<li><span class="sw spend-line"></span>Cumulative share of spend (right axis, percent)</li>', html)
        self.assertIn('<li><span class="sw value-line"></span>Cumulative share of purchase value (right axis, percent)</li>', html)
        self.assertIn('<li><span class="sw bar"></span>Spend per ad (bars, left axis, USD)</li>', html)

    def test_pareto_names_spend_only_when_value_is_missing(self):
        rows = [ad_row("a", "A", 100, 0, conversion_value=None), ad_row("b", "B", 80, 0, conversion_value=None)]
        html, _ = panels.pareto(panels.Ctx(rows=rows, currency="USD"))
        self.assertIn("Cumulative share of spend", html)
        self.assertNotIn("Cumulative share of purchase value", html)

    def test_the_spend_and_roas_chart_has_a_legend_and_single_series_charts_do_not(self):
        html, _ = panels.over_time(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD"))
        key = html.split('<ul class="legend">')[1].split("</ul>")[0]
        self.assertIn('<span class="sw bar"></span>Spend (USD)', key)
        self.assertIn('<span class="sw line"></span>ROAS (x)', key)
        import charts
        single = charts.combo_chart(["2026-03-01", "2026-03-02"], None, [1.0, 2.0], "", "CTR (%)", "x", width=300, height=190)
        self.assertNotIn("legend", single)


class VerdictRobustnessTest(unittest.TestCase):
    def test_an_unknown_or_missing_verdict_id_is_cant_judge_never_too_early(self):
        for entry in ({"verdict_id": "mystery"}, {"verdict_id": ""}, {}):
            self.assertEqual(panels.entry_class(entry), "cant", entry)
        self.assertEqual(panels.entry_class({"verdict_id": "too_early"}), "early")
        rows = [ad_row("1", "a", 100, 300), ad_row("2", "b", 90, 200)]
        verdicts = {"summary": {}, "ads": [{"ad": "1", "ad_name": "a", "verdict_id": "mystery", "spend_at_stake": 5},
                                           {"ad": "2", "ad_name": "b", "spend_at_stake": 4}]}
        html, _ = panels.verdict_board(panels.Ctx(rows=rows, verdicts=verdicts, currency="USD"))
        cant = next(c for c in html.split('<div class="col col-')[1:] if c.startswith("cant"))
        early = next(c for c in html.split('<div class="col col-')[1:] if c.startswith("early"))
        self.assertEqual(cant.count('<article class="ad-card" '), 2)
        self.assertEqual(early.count('<article class="ad-card" '), 0)
        self.assertEqual(cant.count("unrecognised verdict"), 2)


class BoardTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verdicts = acme_verdicts()
        cls.ctx = panels.Ctx(rows=cm.load_rows(str(FIXTURE)), verdicts=cls.verdicts, currency="USD")

    def test_the_shared_basis_is_said_once_above_the_board(self):
        html, _ = panels.verdict_board(self.ctx)
        basis = self.verdicts["ads"][0]["payback_basis"]
        self.assertEqual(html.count(basis), 1)
        self.assertLess(html.index("Judged on:"), html.index('<div class="board">'))
        self.assertNotIn("Judged on: cost per sale", html[html.index('<div class="board">'):])

    def test_cards_drop_the_repeated_confidence_clause_but_keep_the_chip(self):
        entry = next(e for e in self.verdicts["ads"] if e["confidence"] == "Early read")
        self.assertIn("Early read:", entry["sentence"])
        card = panels.ad_card(self.ctx, entry)
        self.assertNotIn("Early read:", card)
        self.assertNotIn("small comparison group (", card)
        self.assertIn('<span class="conf" title="%s">Early read</span>' % entry["confidence_reason"], card)
        self.assertEqual(panels.strip_confidence("Pause it. Confident: sure.", "Confident"), "Pause it.")
        self.assertEqual(panels.strip_confidence("Pause it.", "Confident"), "Pause it.")


class PartialCoverageTest(unittest.TestCase):
    ROWS = [ad_row("a", "A", 100, 500), ad_row("b", "B", 80, 300), ad_row("c", "C", 60, 100),
            ad_row("d", "D", 40, 60), ad_row("e", "E", 21, 30), ad_row("f", "F", 9, 10)]

    def half_blank(self):
        return [dict(r, conversion_value=None) if i % 2 else r for i, r in enumerate(self.ROWS)]

    def test_a_tile_with_partial_coverage_shows_its_value_and_how_many_rows_lack_it(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.half_blank(), currency="USD"))
        self.assertIn("purchase value missing on 3 of 6 rows", html)
        self.assertEqual(html.count("purchase value missing on 3 of 6 rows"), 2)
        self.assertIn("USD 630", html)

    def test_fully_present_and_fully_missing_are_not_partial(self):
        full, _ = panels.kpi_strip(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertNotIn("missing on", full)
        none, _ = panels.kpi_strip(panels.Ctx(rows=[dict(r, conversion_value=None) for r in self.ROWS], currency="USD"))
        self.assertIn("n/a (missing purchase value)", none)
        self.assertNotIn("conversion_value missing on", none)

    def test_the_pareto_sentence_states_value_coverage_when_partial(self):
        html, _ = panels.pareto(panels.Ctx(rows=self.half_blank(), currency="USD"))
        self.assertIn("Purchase value is present for 3 of 6 ads and on 3 of 6 rows", html)
        clean, _ = panels.pareto(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertNotIn("is present for", clean)


class KpiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))

    def test_twelve_tiles_in_spec_order(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        names = re.findall(r'<p class="kpi-name">([^<]*)</p>', html)
        self.assertEqual([n.split(" (")[0] for n in names],
                         ["Spend", "Impressions", "Reach", "Frequency", "CTR", "CPM", "Purchases", "CPA", "Purchase value", "ROAS", "Hook rate", "Hold rate"])

    def test_reach_and_frequency_need_the_account_file(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        self.assertEqual(html.count(panels.NEEDS_ACCOUNT), 2)
        self.assertIn("--account", html)
        with_account, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD", account={"reach": 123456.0, "frequency": 1.75}))
        self.assertNotIn(panels.NEEDS_ACCOUNT, with_account)
        self.assertIn("123,456", with_account)
        self.assertIn("1.75", with_account)

    def test_totals_never_sum_reach(self):
        self.assertIsNone(panels.totals(self.rows)["reach"])

    def test_every_tile_says_no_prior_period_without_a_prior_file(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        self.assertEqual(html.count("no prior period"), 12)

    def test_prior_period_gives_a_signed_change(self):
        prior = [dict(r, spend=(r.get("spend") or 0) / 2) for r in self.rows]
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD", prior=prior))
        self.assertIn("+100.0% vs prior period", html)
        self.assertNotIn("no prior period", html.split("Impressions")[0])

    def test_hook_rate_is_marked_derived_when_three_second_plays_were_derived(self):
        rows = cm.load_rows([{"ad_name": "a | video | c | bau | p | t | 2026-03-01", "ad_id": "1", "date": "2026-03-01", "spend": 100.0,
                              "impressions": 10000.0, "cost_per_action_type:video_view": 0.5123}])
        self.assertEqual(rows[0]["video_views_3s_source"].split(":")[0], "derived")
        derived, _ = panels.kpi_strip(panels.Ctx(rows=rows, currency="USD"))
        self.assertIn("Hook rate (derived)", derived)
        reported, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        self.assertNotIn("(derived)", reported)

    def test_one_day_of_data_has_no_sparkline_and_says_so(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=[ad_row("1", "a", 100, 300)], currency="USD"))
        self.assertNotIn("<svg", html)
        self.assertIn("one day of data", html)

    def test_sparklines_appear_with_two_or_more_days(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        self.assertIn('class="spark"', html)

    def test_a_missing_operand_reads_n_a_never_zero(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=[ad_row("1", "a", 100, 300)], currency="USD"))
        self.assertIn("n/a (missing", html)
        self.assertNotRegex(html, r'kpi-value">0(\.0+)?%?<')

    def test_unknown_currency_is_stated_not_guessed(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows))
        self.assertIn("Spend (account currency)", html)


class FunnelTest(unittest.TestCase):
    def test_absent_columns_read_missing_and_the_rate_after_a_gap_is_not_computed(self):
        rows = cm.load_rows(str(FIXTURE))
        ctx = panels.Ctx(rows=rows, currency="USD")
        html, state = panels.funnel(ctx)
        self.assertEqual(state, "data")
        self.assertIn("n/a (missing landing page views)", html)
        self.assertIn("n/a (missing checkouts)", html)
        self.assertIn("not computed across the missing Landing page views step", html)
        self.assertIn("not computed across the missing Checkouts step", html)
        self.assertEqual(ctx.funnel_headers, {"landing_page_views": None, "checkouts": None})

    def test_present_columns_are_summed_and_their_headers_named(self):
        rows = [ad_row("1", "a", 100, 300, **{"Landing page views": "80", "Checkouts initiated": "21", "link_clicks": 100.0, "add_to_carts": 40.0}),
                ad_row("2", "b", 50, 90, **{"Landing page views": "60", "Checkouts initiated": "9", "link_clicks": 100.0, "add_to_carts": 20.0})]
        ctx = panels.Ctx(rows=rows, currency="USD")
        html, _ = panels.funnel(ctx)
        self.assertEqual(ctx.funnel_headers, {"landing_page_views": "Landing page views", "checkouts": "Checkouts initiated"})
        self.assertIn(">140<", html)
        self.assertIn("70.00%", html)
        self.assertNotIn("n/a (missing landing page views)", html)
        self.assertNotIn("n/a (missing checkouts)", html)

    def test_funnel_headers_are_named_in_the_footer_for_both_cases(self):
        present = report.build_html(rows=[ad_row("1", "a", 100, 300, **{"Landing page views": "80"})], currency="USD")
        absent = report.build_html(rows=cm.load_rows(str(FIXTURE)), currency="USD")
        self.assertIn("landing page views read from column &#x27;Landing page views&#x27;", present)
        self.assertIn("checkouts: no matching column", present)
        self.assertIn("landing page views: no matching column", absent)
        self.assertIn("checkouts: no matching column", absent)


class ParetoTest(unittest.TestCase):
    ROWS = [ad_row("a", "A", 100, 500), ad_row("b", "B", 80, 300), ad_row("c", "C", 60, 100),
            ad_row("d", "D", 40, 60), ad_row("e", "E", 21, 30), ad_row("f", "F", 9, 10)]

    def test_the_cut_sentence_on_known_numbers(self):
        html, state = panels.pareto(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertEqual(state, "data")
        self.assertIn("2 ads (33% of ads) drive 80% of purchase value.", html)
        self.assertIn("--pareto-share", html)

    def test_the_share_is_settable(self):
        html, _ = panels.pareto(panels.Ctx(rows=self.ROWS, currency="USD", pareto_share=90.0))
        self.assertIn("3 ads (50% of ads) drive 90% of purchase value.", html)

    def test_without_purchase_value_the_cut_reads_spend_and_says_so(self):
        rows = [dict(r, conversion_value=None) for r in self.ROWS]
        html, _ = panels.pareto(panels.Ctx(rows=rows, currency="USD"))
        self.assertIn("of spend.", html)
        self.assertIn("no purchase value in the data", html)
        self.assertNotIn("of purchase value.", html)

    def test_concentration_gauge_states_its_n(self):
        html, _ = panels.head_tail(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertIn("Share of spend in the top 3 ads", html)
        self.assertIn("N=3", html)
        self.assertIn("77%", html)
        verdicts = {"settings": {"top_n": 2}, "summary": {}, "ads": []}
        html, _ = panels.head_tail(panels.Ctx(rows=self.ROWS, currency="USD", verdicts=verdicts))
        self.assertIn("N=2", html)
        self.assertIn("58%", html)

    def test_head_gallery_stops_at_the_cut_and_the_tail_is_collapsed_with_a_summary(self):
        html, _ = panels.head_tail(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertEqual(html.count('<article class="ad-card" '), 2)
        self.assertIn("Long tail: 4 ads", html)
        self.assertIn("<details", html)
        self.assertNotIn("<details open", html)

    def test_the_gallery_is_capped_at_top_n_and_the_overflow_is_listed_compactly(self):
        html, _ = panels.head_tail(panels.Ctx(rows=self.ROWS, currency="USD", pareto_share=99.0, top_n=2))
        self.assertEqual(html.count('<article class="ad-card" '), 2)
        self.assertIn("more head ads are listed below the cards", html)


class LabelTest(unittest.TestCase):
    def test_labels_are_never_the_raw_first_name_segment(self):
        ctx = panels.Ctx(rows=cm.load_rows(str(FIXTURE)))
        for ad in ctx.ads:
            label = panels.readable_label(ad, ad["ad_name"], ad["ad_id"])
            self.assertNotEqual(label.lower(), panels._first_segment(ad["ad_name"]).lower(), ad["ad_name"])
            self.assertIn(" · ", label)

    def test_a_lone_parsed_field_falls_back_to_the_full_name_truncated_at_a_word(self):
        name = "sunrise story " + "word " * 31
        label = panels.readable_label({"concept": "sunrise story word word word"}, "sunrise story word word word | x", 1)
        self.assertEqual(label, "sunrise story word word word | x")
        long_label = panels.readable_label({"concept": "sunrise"}, "sunrise", 1)
        self.assertEqual(long_label, "sunrise")
        cut = panels.readable_label({}, name, 1)
        self.assertTrue(cut.endswith("..."))
        self.assertLessEqual(len(cut), panels.LABEL_WORDS + 3)
        self.assertNotIn("wor...", cut)

    def test_unparsed_names_with_no_name_use_the_id(self):
        self.assertEqual(panels.readable_label({}, None, 42), "Ad 42")

    def test_fields_that_did_not_parse_are_skipped(self):
        self.assertEqual(panels.readable_label({"concept": "c", "format": "static"}, "x | y", 1), "c · static")

    def test_card_text_from_the_data_is_escaped(self):
        ctx = panels.Ctx()
        html = panels.ad_card(ctx, {"ad": "<b>1</b>", "ad_name": "<script>alert(1)</script>", "sentence": "<i>hi</i>", "verdict_id": "scale",
                                    "confidence": "<u>x</u>", "confidence_reason": '"><x>'})
        for raw in ("<script>alert", "<i>hi", "<b>1</b>", "<u>x", '"><x>'):
            self.assertNotIn(raw, html)


class ScaleTest(unittest.TestCase):
    def test_five_hundred_twenty_ads_stay_capped_and_under_six_megabytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.csv"
            with open(path, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Day", "Ad name", "Ad ID", "Amount spent (USD)", "Impressions", "Link clicks", "Purchases", "Purchases conversion value"])
                for n in range(520):
                    name = "concept-%d | %s | creator-%d | bau | prod | lofi | 2026-03-01" % (n % 40, ("static", "ugc-video", "carousel")[n % 3], n % 23)
                    for day in range(1, 4):
                        writer.writerow(["2026-03-%02d" % day, name, 1000 + n, 40 + (n * 7) % 90, 9000 + n * 11, 120 + n % 47, 3 + n % 7, 150 + (n * 13) % 400])
            out = subprocess.run([sys.executable, str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"), str(path), "--json"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            verdicts = json.loads(out.stdout)
            rows = cm.load_rows(str(path))
            top_n = 8
            html = report.build_html(rows=rows, verdicts=verdicts, currency="USD", top_n=top_n)
        self.assertLess(len(html.encode("utf-8")), 6 * 1024 * 1024)
        self.assertEqual(len(verdicts["ads"]), 520)
        self.assertIn("N=%d" % top_n, html)
        board = html[html.index('id="panel-board"'):html.index('id="panel-fatigue"')]
        columns = board.split('<div class="col col-')[1:]
        self.assertEqual(len(columns), 7)
        for column in columns:
            self.assertLessEqual(column.count('<article class="ad-card" '), top_n)
            self.assertLessEqual(column.count('<td class="adname">'), panels.LIST_CAP)
        self.assertIn("more are not listed", board)
        tail = html[html.index('id="panel-head-tail"'):html.index('id="tab-keep-kill"')]
        self.assertLessEqual(tail.count('<td class="adname">'), panels.LIST_CAP)
        self.assertLessEqual(tail.count('<article class="ad-card" '), top_n)


class PageStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = acme_verdicts()
        cls.html = report.build_html(rows=cls.rows, verdicts=cls.verdicts, currency="USD", title="Acme", source="Meta ads connector",
                                     attribution="7-day click", completeness="reconciled")

    def test_nav_lists_six_tabs_in_spec_order(self):
        nav = re.search(r'<nav class="tabs".*?</nav>', self.html, re.S).group(0)
        self.assertEqual(re.findall(r">([^<]+)</a>", nav), TAB_ORDER)
        self.assertEqual(re.findall(r'href="#(tab-[a-z-]+)"', nav),
                         ["tab-overview", "tab-pareto", "tab-keep-kill", "tab-format", "tab-white-space", "tab-briefing"])

    def test_all_six_sections_exist_in_order_with_javascript_off(self):
        ids = re.findall(r'<section class="tab" id="(tab-[a-z-]+)"', self.html)
        self.assertEqual(ids, ["tab-overview", "tab-pareto", "tab-keep-kill", "tab-format", "tab-white-space", "tab-briefing"])
        parser = Balance()
        parser.feed(self.html)
        self.assertEqual((parser.errors, parser.stack), ([], []))
        for tag, attrs in parser.attrs:
            self.assertNotIn("hidden", attrs, tag)
            self.assertNotRegex(attrs.get("style") or "", r"display\s*:\s*none|visibility\s*:\s*hidden")

    def test_the_script_only_adds_behaviour(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        self.assertIn('root.className += " js"', script)
        self.assertIn("beforeprint", script)
        self.assertIn("details:not([open])", script)
        self.assertRegex(self.html, r"@media print[^@]*section\.tab\[hidden\]\s*\{\s*display: block !important")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_inline_script_is_valid_javascript(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script)
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_header_has_both_logo_variants_title_window_currency_and_source(self):
        header = re.search(r"<header class=\"top\">.*?</header>", self.html, re.S).group(0)
        light = re.search(r'<span class="logo-light" role="img" aria-label="Elephant Room">.*?</span>', header, re.S).group(0)
        dark = re.search(r'<span class="logo-dark" role="img" aria-label="Elephant Room">.*?</span>', header, re.S).group(0)
        self.assertIn('fill="#1a1a1a"', light)
        self.assertIn('fill="white"', dark)
        self.assertIn("Acme creative <span class=\"grad\">review</span>", header)
        self.assertIn("2026-03-01 to 2026-03-30", header)
        self.assertIn("USD", header)
        self.assertIn("Meta ads connector", header)
        self.assertIn("7-day click", header)

    def test_the_two_logos_do_not_share_a_clip_id(self):
        ids = re.findall(r'<clipPath id="([^"]+)"', self.html)
        self.assertGreaterEqual(len(ids), 4)
        self.assertEqual(len(ids), len(set(ids)))

    def test_footer_has_data_and_method_and_the_logo_and_the_privacy_line(self):
        footer = re.search(r"<footer>.*?</footer>", self.html, re.S).group(0)
        for text in ("Data and method", "by Elephant Room", "own ads, never benchmarks", "only outside request this page makes is the font stylesheet",
                     "Ad images:", "Funnel columns beyond the standard fields", "Dashboard settings used"):
            self.assertIn(text, footer)
        self.assertEqual(footer.count('role="img" aria-label="Elephant Room"'), 2)

    def test_three_completeness_states(self):
        for value, css, text in ((None, "warn", "Not reconciled"), ("reconciled", "ok", "Reconciled"), ("incomplete:7.5", "bad", "Incomplete 7.5%")):
            html = report.build_html(rows=self.rows, completeness=value)
            self.assertIn('<span class="status %s">%s</span>' % (css, text), html)

    def test_a_bad_completeness_value_is_refused(self):
        with self.assertRaises(ValueError):
            report.completeness_badge("mostly fine")

    def test_no_url_is_written_into_any_src_and_no_external_host_but_fonts(self):
        self.assertIsNone(re.search(r'src="(?!data:)', self.html))
        hosts = set(re.findall(r"https?://([^/\"'\s)]+)", self.html))
        self.assertLessEqual(hosts, {"fonts.googleapis.com", "fonts.gstatic.com"})

    def test_user_text_cannot_inject_a_template_placeholder(self):
        html = report.build_html(rows=[ad_row("1", "{{footer}} | static | c | bau | p | t | 2026-03-01", 5, 5)], title="{{body}}")
        self.assertEqual(html.count("<footer>"), 1)
        self.assertIn("{{body}}", html)

    def test_an_ad_in_three_panels_is_embedded_once_and_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = self.verdicts["summary"]["do_first"][0]["ad"]
            folder = Path(tmp)
            (folder / ("%s.png" % top)).write_bytes(PNG)
            html = report.build_html(rows=self.rows, verdicts=self.verdicts, currency="USD", previews=Previews(str(folder)))
        self.assertEqual(html.count("data:image/png"), 1)
        self.assertGreaterEqual(html.count('href="#pv-%s"' % top), 3)
        self.assertIn("previews embedded 1, thumbnails used 0", html)

    def test_account_file_must_carry_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "a.json"
            bad.write_text('{"reach": "lots"}')
            with self.assertRaises(ValueError):
                report.load_account(str(bad))
            good = Path(tmp) / "b.json"
            good.write_text('{"reach": 1000, "frequency": 1.5}')
            self.assertEqual(report.load_account(str(good)), {"reach": 1000.0, "frequency": 1.5})


if __name__ == "__main__":
    unittest.main()
