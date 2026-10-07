import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))

import benchmarks  # noqa: E402
import creative_metrics as cm  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
from previews import Previews  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a730000001049444154789c63a8b17a0b440c100a002c1e068d70420d590000000049454e44ae426082")
OVERVIEW_TABS = ("overview", "pareto", "keep-kill")
DATA_PANELS = [(pid, fn) for tab_id, _, tab in panels.TABS if tab_id in OVERVIEW_TABS for pid, _, _, fn in tab]
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

    def test_thirteen_overview_panels_and_fifteen_later_tab_panels_exist(self):
        self.assertEqual(len(DATA_PANELS), 13)
        self.assertEqual(sum(len(tab) for tab_id, _, tab in panels.TABS if tab_id not in OVERVIEW_TABS), 15)

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


def axis_labels(svg):
    """The text of the y-axis tick labels: left ones end at the axis, right ones start after the plot."""
    left = re.findall(r'<text x="[\d.]+" y="[\d.]+" text-anchor="end">([^<]*)</text>', svg)
    right = re.findall(r'<text x="[\d.]+" y="[\d.]+">([^<]*)</text>', svg)
    return left, right


class AxisUnitTest(unittest.TestCase):
    def roas_view(self):
        html, _ = panels.over_time(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD"))
        return re.search(r'data-view="roas">.*?</svg>', html, re.S).group(0)

    def test_the_roas_view_prints_its_ticks_in_x_and_the_spend_bars_theirs_in_money(self):
        left, right = axis_labels(self.roas_view())
        self.assertNotIn("0.00", left + right)
        self.assertEqual(left[0], "0x")
        self.assertTrue(all(label.endswith("x") for label in left), left)
        self.assertTrue(right and all(re.fullmatch(r"[\d,]+(\.\d+)?", label) for label in right), right)

    def test_the_spend_axis_does_not_print_a_second_zero_beside_the_roas_zero(self):
        left, right = axis_labels(self.roas_view())
        self.assertEqual(left.count("0x"), 1)
        self.assertNotIn("0", right)
        self.assertEqual(len(right), 2)

    def test_a_line_only_chart_keeps_its_own_zero_in_its_unit(self):
        import charts
        svg = charts.combo_chart(["2026-03-01", "2026-03-02"], None, [1.0, 3.0], "", "ROAS (x)", "x", line_fmt=charts.axis_format("x"))
        self.assertEqual(axis_labels(svg)[1], ["0x", "1.5x", "3x"])

    def test_money_ticks_use_the_currencys_own_digits(self):
        import charts
        self.assertEqual(charts.axis_format("money", "USD")(0), "0")
        self.assertEqual(charts.axis_format("money", "USD")(12.5), "12.50")
        self.assertEqual(charts.axis_format("money", "USD")(1234.5), "1,234")
        self.assertEqual(charts.axis_format("money", "JPY")(12.5), "12")
        self.assertEqual(charts.axis_format("pct")(0.8), "0.8%")
        self.assertEqual(charts.axis_format("x")(2.45), "2.45x")

    def test_fatigue_charts_use_percent_and_x_ticks(self):
        ctx = panels.Ctx(rows=cm.load_rows(str(FIXTURE)), verdicts=acme_verdicts(), currency="USD")
        html, _ = panels.fatigue(ctx)
        found = list(re.finditer(r"<svg[^>]*aria-label=\"((?:CTR|Frequency)) by day[^\"]*\"[^>]*>(.*?)</svg>", html, re.S))
        self.assertTrue(found)
        for match in found:
            _, right = axis_labels(match.group(2))
            suffix = "%" if match.group(1) == "CTR" else "x"
            self.assertTrue(all(label.endswith(suffix) for label in right), (match.group(1), right))


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

    def test_the_time_chart_has_a_chip_per_series_and_single_series_charts_do_not(self):
        html, _ = panels.over_time(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD"))
        roas = re.search(r'data-view="roas">.*?</figure>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<button type="button" class="chip" data-series="([^"]*)"', roas), ["Spend", "Daily", "7-day average"])
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
        self.assertIn("purchase value recorded on 3 of 6 ads; the rest had none in this window", html)
        self.assertEqual(html.count("purchase value recorded on 3 of 6 ads; the rest had none in this window"), 2)
        self.assertIn("USD 630", html)

    def test_fully_present_and_fully_missing_are_not_partial(self):
        full, _ = panels.kpi_strip(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertNotIn("recorded on", full)
        none, _ = panels.kpi_strip(panels.Ctx(rows=[dict(r, conversion_value=None) for r in self.ROWS], currency="USD"))
        self.assertRegex(none, r'<p class="kpi-name">ROAS[^<]*</p><p class="kpi-value">n/a</p><p class="kpi-note">missing purchase value</p>')
        self.assertNotIn("recorded on", none)

    def test_the_pareto_sentence_states_value_coverage_when_partial(self):
        html, _ = panels.pareto(panels.Ctx(rows=self.half_blank(), currency="USD"))
        self.assertIn("Purchase value was recorded on 3 of 6 ads; the rest had none in this window and count as no value.", html)
        clean, _ = panels.pareto(panels.Ctx(rows=self.ROWS, currency="USD"))
        self.assertNotIn("was recorded on", clean)


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
        tiles = dict(re.findall(r'<p class="kpi-name">([^<]*)</p><p class="kpi-value">([^<]*)</p>', html))
        self.assertEqual((tiles["Reach"], tiles["Frequency"]), ("n/a", "n/a"))
        with_account, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD", account={"reach": 123456.0, "frequency": 1.75}))
        self.assertNotIn('kpi-value">n/a', with_account)
        self.assertIn("123,456", with_account)
        self.assertIn("1.75", with_account)

    def test_totals_never_sum_reach(self):
        self.assertIsNone(panels.totals(self.rows)["reach"])

    def test_every_tile_says_no_prior_period_without_a_prior_file(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD"))
        self.assertEqual(len(re.findall("no prior period", html, re.I)), 1)
        self.assertIn("No prior period supplied: deltas appear when you pass one.", html)
        self.assertNotIn('<span class="muted">no prior period', html)

    def test_prior_period_gives_a_signed_change(self):
        prior = [dict(r, spend=(r.get("spend") or 0) / 2) for r in self.rows]
        html, _ = panels.kpi_strip(panels.Ctx(rows=self.rows, currency="USD", prior=prior))
        self.assertIn("+100.0%</span> vs prior period", html)
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
        self.assertRegex(html, r'kpi-value">n/a</p><p class="kpi-note">missing ')
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
        self.assertIn("you can change it when you rebuild the report", html)

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
        self.assertIn("1 Mar \u2013 30 Mar 2026", header)
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
        tip = "Pull the account totals for the same window to check nothing is missing"
        cases = ((None, '<span class="status neutral" title="%s">Totals not checked</span>' % tip),
                 ("reconciled", '<span class="status ok">Reconciled</span>'),
                 ("incomplete:7.5", "<span class=\"status warn\">Totals don't match (7.5% short)</span>"))
        for value, badge in cases:
            self.assertIn(badge, report.build_html(rows=self.rows, completeness=value))
        self.assertRegex(self.css_of(report.build_html(rows=self.rows)), r"\.status\.neutral \{[^}]*background: var\(--flat-bg\)[^}]*color: var\(--flat-fg\)")

    @staticmethod
    def css_of(html):
        return re.search(r"<style>(.*?)</style>", html, re.S).group(1)

    def test_an_unchecked_pull_is_never_dressed_as_a_warning_or_a_pass(self):
        page = report.build_html(rows=self.rows)
        self.assertNotIn("Not reconciled", page)
        self.assertNotIn('class="status ok"', page)
        self.assertNotIn('class="status warn"', page)

    def test_a_bad_completeness_value_is_refused(self):
        with self.assertRaises(ValueError):
            report.completeness_badge("mostly fine")

    def test_no_url_is_written_into_any_src_and_no_external_host_but_fonts(self):
        self.assertIsNone(re.search(r'src="(?!data:)', self.html))
        fonts = {"fonts.googleapis.com", "fonts.gstatic.com"}
        method = "".join(re.findall(r"<pre>.*?</pre>", self.html, re.S))
        self.assertLessEqual(set(re.findall(r"https?://([^/\"'\s)]+)", self.html.replace(method, ""))), fonts)
        cited = {urlparse(e["url"]).netloc for e in benchmarks.load()}
        self.assertLessEqual(set(re.findall(r"https?://([^/\"'\s)]+)", method)), fonts | cited)

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


class ReaderText(HTMLParser):
    """Text and text-bearing attributes a reader can see, leaving out scripts, styles and the Data and method details."""

    def __init__(self):
        super().__init__()
        self.hidden, self.method, self.text = 0, 0, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag == "details" and (self.method or "method" in (attrs.get("class") or "").split()):
            self.method += 1
        elif not self.method:
            self.text.extend(v for k, v in attrs.items() if k in ("title", "aria-label", "alt", "placeholder") and v)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif tag == "details" and self.method:
            self.method -= 1

    def handle_data(self, data):
        if not self.hidden and not self.method:
            self.text.append(data)


def reader_text(page):
    parser = ReaderText()
    parser.feed(page)
    return " ".join(parser.text)


class ReaderWordsTest(unittest.TestCase):
    """Reader-visible text speaks of ads, never of rows or command flags (those live in SKILL.md and the Data and method details)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = acme_verdicts()
        cls.grade = acme_grade()
        blank = [dict(r, conversion_value=None, conversions=None) if str(r["ad_id"])[-1] in "02468" else r for r in cls.rows]
        cls.pages = {
            "full": report.build_html(rows=cls.rows, verdicts=cls.verdicts, grade=cls.grade, currency="USD", title="Acme"),
            "partial": report.build_html(rows=blank, verdicts=cls.verdicts, grade=cls.grade, currency="USD", title="Acme"),
            "rows only": report.build_html(rows=cls.rows, currency="USD", title="Acme"),
            "no data": report.build_html(verdicts=cls.verdicts, title="Acme"),
            "undated": report.build_html(rows=[{k: v for k, v in r.items() if k != "date"} for r in cls.rows[:6]], currency="USD", title="Acme"),
            "one day": report.build_html(rows=[r for r in cls.rows if r["date"] == cls.rows[0]["date"]], currency="USD", title="Acme"),
        }

    def test_no_reader_visible_text_says_rows(self):
        for name, page in self.pages.items():
            self.assertNotRegex(reader_text(page), r"(?i)\brows?\b", name)

    def test_no_reader_visible_text_names_a_command_flag(self):
        for name, page in self.pages.items():
            self.assertNotRegex(reader_text(page), r"(?<![\w-])--[a-z]", name)

    def test_partial_coverage_is_said_in_ads(self):
        text = reader_text(self.pages["partial"])
        self.assertRegex(text, r"purchases recorded on \d+ of \d+ ads; the rest had none in this window")
        self.assertRegex(text, r"purchase value recorded on \d+ of \d+ ads")

    def test_the_method_details_are_where_flags_and_row_counts_may_live(self):
        method = self.pages["full"].split('<details class="method"')[1].split("</details>")[0]
        self.assertIn("cards per list (--top-n)", method)
        self.assertNotIn("--top-n", reader_text(self.pages["full"]))


NO_VIDEO = [{k: v for k, v in r.items() if not k.startswith("video")} for r in cm.load_rows(str(FIXTURE))]
BANNER = 'class="banner"'


class OverviewBannerTest(unittest.TestCase):
    """One banner when a metric is missing for every ad; plain n/a in the tiles; nothing when it is only partly missing."""

    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.account = {"reach": 123456.0, "frequency": 1.75}

    def overview(self, **kw):
        page = report.build_html(currency="USD", title="Acme", **kw)
        return page.split('id="tab-overview"')[1].split('id="tab-pareto"')[0]

    def test_hook_hold_reach_and_frequency_missing_everywhere_give_one_banner_at_the_top(self):
        tab = self.overview(rows=NO_VIDEO)
        self.assertEqual(tab.count(BANNER), 1)
        self.assertLess(tab.index(BANNER), tab.index('id="panel-kpis"'))
        text = reader_text(tab)
        self.assertIn("Not in this pull", text)
        self.assertIn("Hook rate : missing 3-second plays. To get it:", text)
        self.assertIn("Hold rate : missing ThruPlays. To get it:", text)
        self.assertIn("Reach and frequency don't add up across ads, so they need an account-level figure for this window; none was supplied.", text)
        tiles = dict(re.findall(r'<p class="kpi-name">([^<]*)</p><p class="kpi-value">([^<]*)</p>', tab))
        for name in ("Hook rate", "Hold rate", "Reach", "Frequency"):
            self.assertEqual(tiles[name], "n/a", name)
        for name in ("Hook rate", "Hold rate", "Reach", "Frequency"):
            tile = re.search(r'<p class="kpi-name">%s.*?</div></div>' % name, tab, re.S).group(0)
            self.assertNotIn("kpi-note", tile, name)
            self.assertNotIn("n/a (", tile, name)

    def test_only_hold_missing_names_only_hold(self):
        rows = [{k: v for k, v in r.items() if k != "video_thruplay"} for r in self.rows]
        tab = self.overview(rows=rows, account=self.account)
        self.assertEqual(tab.count(BANNER), 1)
        text = reader_text(tab)
        self.assertIn("Hold rate : missing ThruPlays. To get it:", text)
        self.assertNotIn("Hook rate : missing", text)
        self.assertNotIn("Reach and frequency don't add up", text)

    def test_partly_missing_data_shows_no_banner_and_keeps_the_per_tile_note(self):
        tab = self.overview(rows=self.rows, account=self.account)
        self.assertEqual(tab.count(BANNER), 0)
        hook = re.search(r'<p class="kpi-name">Hook rate.*?</div></div>', tab, re.S).group(0)
        self.assertRegex(hook, r"video ads \u00b7 \d+ of \d+")

    def test_the_account_file_removes_the_reach_sentence_only(self):
        tab = self.overview(rows=NO_VIDEO, account=self.account)
        self.assertEqual(tab.count(BANNER), 1)
        self.assertNotIn("Reach and frequency", reader_text(tab.split(BANNER)[1].split("</div>")[0]))

    def test_no_banner_without_data_the_whole_tab_is_an_empty_state(self):
        self.assertEqual(self.overview(verdicts=acme_verdicts()).count(BANNER), 0)

    def test_the_banner_is_the_only_place_that_says_why_everywhere(self):
        tab = self.overview(rows=NO_VIDEO)
        outside = tab.replace(re.search(r'<div class="banner".*?</div>', tab, re.S).group(0), "")
        self.assertNotIn("Not in this pull", reader_text(outside))
        self.assertNotIn("none was supplied", reader_text(outside))



HARNESS_JS = r'''
var attrs = {}, listeners = {};
var node = { id: "t", hidden: false, closest: function () { return null; }, addEventListener: function () {}, getAttribute: function () { return "#t"; },
  setAttribute: function () {}, removeAttribute: function () {}, querySelector: function () { return null; } };
function stub(store) {
  attrs = {};
  var root = { className: "", setAttribute: function (k, v) { attrs[k] = v; }, getAttribute: function (k) { return attrs[k] || null; } };
  global.window = { localStorage: store, matchMedia: function () { return { matches: false }; }, addEventListener: function () {}, scrollTo: function () {}, innerWidth: 1200 };
  global.history = { replaceState: function () {} };
  global.location = { hash: "" };
  global.document = { documentElement: root,
    querySelectorAll: function (sel) { return sel === "section.tab" ? [node] : []; },
    querySelector: function () { return { namespaceURI: "" }; }, getElementById: function () { return null; },
    addEventListener: function (type, fn) { (listeners[type] = listeners[type] || []).push(fn); }, createElementNS: function () { return {}; } };
}
function click() {
  var target = { closest: function (sel) { return sel.indexOf("theme") >= 0 ? {} : null; } };
  listeners.click.forEach(function (fn) { fn({ target: target, preventDefault: function () {} }); });
}
function boot() { listeners = {}; new Function(SCRIPT)(); }
var out = {};
stub({ getItem: function () { throw new Error("blocked"); }, setItem: function () { throw new Error("blocked"); } });
boot(); click(); out.afterBlockedClick = attrs["data-theme"];
click(); out.afterSecondClick = attrs["data-theme"];
stub({ getItem: function () { return "dark"; }, setItem: function () {} });
boot(); out.storedApplied = attrs["data-theme"];
console.log(JSON.stringify(out));
'''


def squash(css):
    return re.sub(r"\s+", " ", css)


class ShellTest(unittest.TestCase):
    """The redesigned frame: tokens, top bar, scope bar, sub-nav, filter row, KPI strip, cards, responsive and print."""

    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = acme_verdicts()
        cls.html = report.build_html(rows=cls.rows, verdicts=cls.verdicts, grade=acme_grade(), currency="USD", title="Acme",
                                     source="Meta ads connector", attribution="7-day click", completeness="reconciled")
        cls.css = squash(re.search(r"<style>(.*?)</style>", cls.html, re.S).group(1))
        cls.header = re.search(r'<header class="top">.*?</header>', cls.html, re.S).group(0)

    def block(self, opener):
        """The body of the first CSS rule or at-rule that starts with `opener`."""
        start = self.css.index(opener) + len(opener)
        depth, i = 1, start
        while depth:
            depth += {"{": 1, "}": -1}.get(self.css[i], 0)
            i += 1
        return self.css[start:i - 1]

    def test_light_tokens_are_the_default(self):
        root = self.block(":root {")
        for token in ("--bg: #ffffff", "--surface: #ffffff", "--surface-muted: hsl(210 40% 96.1%)", "--text: hsl(222 47% 11%)",
                      "--text-muted: hsl(215 16% 47%)", "--border: hsl(220 13% 91%)", "--accent: hsl(251 97% 60%)",
                      "--accent-soft: hsl(251 97% 60% / .10)", "--danger: hsl(0 84% 60%)", "--bar: hsl(222 47% 8%)",
                      "--bar-border: hsl(217 33% 18%)", "--bar-text: hsl(210 20% 96%)"):
            self.assertIn(token, root)

    def test_dark_follows_the_system_unless_a_theme_is_chosen_and_never_uses_pure_black(self):
        system = self.block('@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {')
        chosen = self.block(':root[data-theme="dark"] {')
        for dark in (system, chosen):
            for token in ("--bg: hsl(222 35% 5%)", "--surface: hsl(222 28% 11%)", "--surface-raised: hsl(222 28% 14%)",
                          "--surface-muted: hsl(222 25% 17%)", "--text: hsl(210 20% 96%)", "--text-muted: hsl(217 18% 68%)",
                          "--border: hsl(222 18% 29%)", "--accent: hsl(251 91% 64%)"):
                self.assertIn(token, dark)
            self.assertNotRegex(dark, r"#000\b|#000000|hsl\(\d+ \d+% 0%\)")

    def test_delta_pill_tokens_in_both_themes(self):
        root = self.block(":root {")
        for token in ("--up-bg: #dcfce7", "--up-fg: #15803d", "--down-bg: #fee2e2", "--down-fg: #b91c1c", "--flat-bg: hsl(220 13% 91%)", "--flat-fg: hsl(220 9% 46%)"):
            self.assertIn(token, root)
        dark = self.block(':root[data-theme="dark"] {')
        for token in ("--up-bg: hsl(160 84% 51% / .10)", "--up-fg: hsl(160 84% 51%)", "--down-bg: hsl(0 91% 71% / .10)", "--down-fg: hsl(0 91% 71%)"):
            self.assertIn(token, dark)

    def test_type_radius_and_series_tokens(self):
        self.assertIn("family=DM+Sans:wght@400;500;600;700", self.html)
        self.assertIn("family=Roboto+Mono", self.html)
        self.assertNotIn("Plus+Jakarta", self.html)
        root = self.block(":root {")
        self.assertIn('--font-body: "DM Sans", "Inter", system-ui', root)
        self.assertIn('--font-mono: "Roboto Mono"', root)
        for n, color in enumerate(("#6366f1", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4", "#f43f5e"), 1):
            self.assertIn("--series-%d: %s" % (n, color), root)
        self.assertIn("--series-neutral: #64748b", root)
        self.assertIn("--radius: 10px", root)
        self.assertIn("--radius-sm: 6px", root)
        self.assertRegex(self.css, r"html \{[^}]*font-size: 15px")
        self.assertRegex(self.css, r"body \{[^}]*font-variant-numeric: tabular-nums")

    def test_charts_read_the_series_tokens(self):
        self.assertRegex(self.css, r"svg \.bar \{[^}]*fill: var\(--series-1\)")
        self.assertRegex(self.css, r"svg\.spark path \{[^}]*stroke: var\(--series-1\)")
        self.assertRegex(self.css, r"svg \.line \{[^}]*stroke: var\(--series-2\)")

    def test_cards_have_a_border_a_soft_shadow_and_a_tinted_hover_without_movement(self):
        self.assertRegex(self.css, r"section\.card \{[^}]*border: 1px solid var\(--border\)[^}]*border-radius: var\(--radius\)")
        self.assertIn("--shadow: 0 1px 2px rgb(0 0 0 / .05)", self.block(":root {"))
        self.assertIn("--hover-border: hsl(251 97% 60% / .4)", self.block(":root {"))
        self.assertIn("--hover-shadow: 0 4px 12px hsl(251 97% 60% / .08)", self.block(":root {"))
        hover = self.block(".kpi:hover {")
        self.assertIn("border-color: var(--hover-border)", hover)
        self.assertIn("box-shadow: var(--hover-shadow)", hover)
        self.assertNotIn("transform", hover)

    def test_the_top_bar_is_one_row_lockup_title_badge_and_theme_toggle(self):
        bar = re.search(r'<div class="topbar">.*?</div>\s*<div class="scope-bar"', self.header, re.S).group(0)
        order = [bar.index(m) for m in ('class="lockup"', "<h1>", 'class="status ok"', 'data-action="theme"')]
        self.assertEqual(order, sorted(order))
        self.assertIn("Acme creative <span class=\"grad\">review</span>", bar)
        self.assertRegex(self.css, r"\.topbar \{[^}]*height: 56px")
        self.assertRegex(self.css, r"\.page \{[^}]*max-width: 1536px[^}]*padding:[^;}]*24px")

    def test_the_theme_toggle_is_a_labelled_button_that_sets_data_theme_and_survives_blocked_storage(self):
        button = re.search(r'<button[^>]*data-action="theme"[^>]*>', self.header).group(0)
        self.assertIn('type="button"', button)
        self.assertIn("aria-label=", button)
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        self.assertIn('setAttribute("data-theme"', script)
        self.assertRegex(script, r"try \{ return storage\.getItem\(THEME_KEY\); \} catch")
        self.assertRegex(script, r"try \{ storage\.setItem\(THEME_KEY, value\); \} catch")
        self.assertRegex(self.css, r"\.theme-toggle \{[^}]*display: none")
        self.assertRegex(self.css, r"\.js \.theme-toggle \{[^}]*display: inline-flex")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_toggle_flips_the_theme_when_storage_throws_and_a_stored_choice_is_applied_on_load(self):
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        harness = HARNESS_JS
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toggle.js"
            path.write_text("var SCRIPT = %s;\n%s" % (json.dumps(script), harness))
            done = subprocess.run(["node", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {"afterBlockedClick": "dark", "afterSecondClick": "light", "storedApplied": "dark"})

    def test_group_sort_and_previews_move_into_the_filters_popover_on_a_phone_instead_of_vanishing(self):
        pop = re.search(r'<details class="facets".*?</details>', self.html, re.S).group(0)
        self.assertEqual(pop.count('class="fb-view fb-view-pop"'), 1)
        for control in ('data-action="group"', 'data-action="sort"', 'data-action="previews-only"'):
            self.assertIn(control, pop)
        self.assertRegex(self.css, r"\.fb-view-pop \{[^}]*display: none")
        small = self.css[self.css.index("@media (max-width: 640px) { .topbar"):]
        small = small[:small.index("} }") + 1]
        self.assertRegex(small, r"\.js \.fb-view-pop \{[^}]*display: flex")
        self.assertRegex(small, r"\.js \.fb-view-row \{[^}]*display: none")

    def test_the_dark_logos_follow_the_chosen_theme_as_well_as_the_system(self):
        self.assertIn(':root[data-theme="dark"] .logo-light { display: none; }', self.css)
        self.assertIn(':root[data-theme="dark"] .logo-dark { display: inline-block; }', self.css)
        self.assertIn(':root:not([data-theme="light"]) .logo-dark { display: inline-block; }', self.css)

    def test_the_scope_bar_reads_window_currency_source_and_attribution(self):
        bar = re.search(r'<div class="scope-bar".*?</div>\s*</header>', self.header, re.S).group(0)
        segments = re.findall(r'<div class="scope-seg"><span class="scope-label">([^<]*)</span> <b>([^<]*)</b></div>', bar)
        self.assertEqual(segments, [("Window", "1 Mar – 30 Mar 2026"), ("Scope", "all ads in the data"), ("Currency", "USD"), ("Source", "Meta ads connector"), ("Attribution", "7-day click")])
        self.assertRegex(self.css, r"\.scope-bar \{[^}]*background: var\(--bar\)[^}]*border-radius: 12px")
        self.assertRegex(self.css, r"\.scope-seg \{[^}]*border-right: 1px solid var\(--bar-border\)")
        self.assertRegex(self.css, r"\.scope-bar \{[^}]*flex-wrap: wrap")

    def test_a_window_across_two_years_names_both(self):
        self.assertEqual(report.format_window("2025-12-30", "2026-01-02"), "30 Dec 2025 – 2 Jan 2026")
        self.assertEqual(report.format_window("2026-09-07", "2026-10-06"), "7 Sep – 6 Oct 2026")
        self.assertEqual(report.format_window(None, None), "n/a (no dates)")

    def test_the_sub_nav_lists_six_tabs_each_with_a_stroke_icon_and_sits_beside_the_content(self):
        nav = re.search(r'<nav class="tabs".*?</nav>', self.html, re.S).group(0)
        links = re.findall(r"<a [^>]*>.*?</a>", nav, re.S)
        self.assertEqual(len(links), 6)
        for link in links:
            self.assertRegex(link, r'<svg class="ico" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"[^>]*stroke="currentColor"')
        self.assertNotIn("<nav", self.header)
        self.assertLess(self.html.index('<nav class="tabs"'), self.html.index('<main'))
        self.assertRegex(self.css, r"nav\.tabs \{[^}]*position: sticky[^}]*top: 16px")
        self.assertRegex(self.css, r"\.shell \{[^}]*grid-template-columns: 208px minmax\(0, 1fr\)")
        self.assertRegex(self.css, r'nav\.tabs a\[aria-current="true"\] \{[^}]*background: var\(--accent-soft\)[^}]*color: var\(--accent\)')

    def test_under_1024px_the_sub_nav_becomes_a_segmented_control(self):
        narrow = self.block("@media (max-width: 1023px) {")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", narrow)
        self.assertRegex(narrow, r"nav\.tabs \{[^}]*position: static[^}]*background: var\(--surface-muted\)")
        self.assertRegex(narrow, r'nav\.tabs a\[aria-current="true"\] \{[^}]*background: var\(--surface-raised\)[^}]*box-shadow: 0 1px 3px rgb\(0 0 0 / \.06\)')

    def test_there_is_no_tab_name_heading_above_the_first_card(self):
        self.assertNotIn('class="tab-title"', self.html)
        self.assertRegex(self.html, r'<section class="tab" id="tab-overview" aria-label="Overview analysis">')
        first = re.search(r'<section class="tab" id="tab-pareto"[^>]*>(.*?)<h3>', self.html, re.S).group(1)
        self.assertTrue(first.strip().startswith('<section class="card panel"'))

    def test_section_cards_use_eyebrow_title_and_the_agreed_padding_and_gap(self):
        self.assertRegex(self.css, r"section\.card \{[^}]*padding: 20px[^}]*margin: 16px 0")
        self.assertRegex(self.css, r"section\.panel > h3:first-of-type \{[^}]*font-size: 20px[^}]*font-weight: 600")
        self.assertRegex(self.css, r"\.eyebrow \{[^}]*font: 600 12px[^}]*text-transform: uppercase[^}]*color: var\(--accent\)")

    def test_the_filter_row_is_one_sticky_row_with_search_filters_clear_count_and_view_controls(self):
        main_at = self.html.index("<main")
        row = re.search(r'<div class="filterbar".*?</div>\s*(?=<div class="fb-status")', self.html[:main_at], re.S).group(0)
        parts = [row.index(m) for m in ('type="search"', "<details", "Filters", 'data-action="clear"', 'class="fb-count"', 'class="fb-view fb-view-row"')]
        view = row[row.index('class="fb-view fb-view-row"'):]
        self.assertLess(view.index('data-action="group"'), view.index('data-action="sort"'))
        self.assertEqual(parts, sorted(parts))
        self.assertIn("fb-clear", re.search(r'<button[^>]*data-action="clear"[^>]*>', row).group(0))
        self.assertRegex(self.css, r"\.fb-clear \{[^}]*display: none")
        self.assertRegex(self.css, r"\.fb-clear\.show \{[^}]*display: inline-block")
        self.assertLess(self.html.index('<nav class="tabs"'), self.html.index('class="filterbar"'))
        self.assertRegex(self.css, r"\.js \.filterbar \{[^}]*position: sticky[^}]*top: 0[^}]*background: var\(--bg\)[^}]*border-bottom")
        self.assertRegex(self.css, r"\.filterbar \{[^}]*display: none")

    def test_the_popover_holds_the_smart_views_and_the_facets_and_the_summary_sits_below_unpinned(self):
        pop = re.search(r'<details class="facets".*?</details>', self.html, re.S).group(0)
        for text in ("Money at risk", "Ready to scale", "Verdict", "account-wide"):
            self.assertIn(text, pop)
        status = re.search(r'<div class="fb-status".*?</div>\s*</div>|<div class="fb-status".*?</p>\s*</div>', self.html, re.S).group(0)
        self.assertIn('class="fb-summary"', status)
        self.assertNotRegex(self.css, r"\.fb-status \{[^}]*position: sticky")
        self.assertRegex(self.css, r"\.fb-summary \{[^}]*white-space: nowrap")

    def test_the_filter_row_height_is_bounded_on_desktop_and_phone(self):
        self.assertRegex(self.css, r"\.filterbar \{[^}]*max-height: 56px")
        phone = self.block("@media (max-width: 480px) {")
        self.assertRegex(phone, r"\.filterbar \{[^}]*max-height: 96px")
        self.assertRegex(phone, r"\.fb-search \{[^}]*flex: 1 1 100%")

    def test_headings_clear_the_sticky_row(self):
        self.assertRegex(self.css, r"section\.panel \{[^}]*scroll-margin-top: 72px")
        self.assertNotIn("top.style.top", self.html)
        self.assertNotIn("function pin", self.html)

    def test_the_kpi_strip_is_an_auto_fill_grid_of_compact_tiles(self):
        self.assertRegex(self.css, r"\.kpis \{[^}]*grid-template-columns: repeat\(auto-fill, minmax\(180px, 1fr\)\)[^}]*gap: 12px")
        self.assertRegex(self.css, r"\.kpi-name \{[^}]*font: 600 12px[^}]*letter-spacing: \.04em[^}]*text-transform: uppercase[^}]*color: var\(--text-muted\)")
        self.assertRegex(self.css, r"\.kpi-value \{[^}]*font: 700 24px")
        self.assertRegex(self.css, r"svg\.spark \{[^}]*width: 100%[^}]*height: 28px")
        self.assertRegex(self.css, r"\.kpi\.unknown \.kpi-value \{[^}]*color: var\(--text-muted\)")
        self.assertNotRegex(self.css, r"\.kpi\.unknown \{[^}]*dashed")
        for tone in ("up", "down", "flat"):
            self.assertRegex(self.css, r"\.pill\.%s \{[^}]*background: var\(--%s-bg\)[^}]*color: var\(--%s-fg\)" % (tone, tone, tone))

    def test_at_390px_nothing_forces_a_sideways_scroll(self):
        phone = self.block("@media (max-width: 480px) {")
        self.assertRegex(phone, r"\.page \{[^}]*padding:[^;}]*16px")
        self.assertRegex(self.css, r"\.content \{[^}]*min-width: 0")
        self.assertRegex(self.css, r"\.scroll \{[^}]*overflow-x: auto")
        self.assertRegex(self.css, r"@media \(max-width: 640px\) \{ table\.stack thead \{ display: none; \}[^@]*table\.stack td \{")

    def test_print_keeps_light_tokens_hides_the_chrome_and_prints_every_tab(self):
        printed = self.block("@media print {")
        self.assertIn(':root, :root[data-theme="dark"], :root:not([data-theme="light"]) {', printed)
        for token in ("--bg: #ffffff", "--surface: #ffffff", "--text: hsl(222 47% 11%)", "--bar: #ffffff"):
            self.assertIn(token, printed)
        hidden = " ".join(re.findall(r"([^{}]*)\{ display: none !important; \}", printed))
        for selector in ("nav.tabs", ".filterbar", ".fb-status", ".theme-toggle"):
            self.assertIn(selector, hidden)
        self.assertRegex(self.html, r"@media print[^@]*section\.tab\[hidden\]\s*\{\s*display: block !important")
        self.assertEqual(self.css.count("@media print"), 1)


class ReviewFixesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.html = report.build_html(rows=cls.rows, verdicts=acme_verdicts(), grade=acme_grade(), currency="USD", title="Acme")
        cls.css = squash(re.search(r"<style>(.*?)</style>", cls.html, re.S).group(1))

    def test_every_chart_svg_scales_with_its_card_and_has_no_fixed_size(self):
        svgs = re.findall(r"<figure class=\"chart[^\"]*\"><svg[^>]*>", self.html)
        self.assertGreater(len(svgs), 5)
        for tag in svgs:
            self.assertIn("viewBox=", tag)
            self.assertNotRegex(tag, r'\swidth="(?!100%)|\sheight="')
        self.assertRegex(self.css, r"\.chart svg \{[^}]*width: 100%[^}]*height: auto[^}]*max-height: 360px")
        self.assertNotRegex(self.css, r"\.chart(\.wide)? svg \{[^}]*max-width: 6[04]0px")

    def test_wide_charts_are_drawn_wide_enough_to_fill_a_desktop_card_under_the_height_cap(self):
        import charts
        svg = charts.combo_chart(["2026-03-01", "2026-03-02"], [1.0, 2.0], [1.0, 2.0], "a", "b", "x")
        w, h = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
        self.assertGreaterEqual(w / h, 2.8)
        svg = charts.pareto_chart([3.0, 2.0], [60.0, 100.0], None, 1, "x", "USD")
        w, h = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
        self.assertGreaterEqual(w / h, 2.8)

    def test_the_all_missing_note_is_a_compact_info_note_not_a_warning(self):
        tab = report.build_html(rows=NO_VIDEO, currency="USD", title="Acme").split('id="tab-overview"')[1].split('id="tab-pareto"')[0]
        note = re.search(r'<div class="banner".*?</div>', tab, re.S).group(0)
        self.assertRegex(note, r'<svg class="ico"[^>]*aria-hidden="true"')
        rule = re.search(r"\.banner \{[^}]*\}", self.css).group(0)
        for want in ("background: var(--surface-muted)", "color: var(--text-muted)", "font-size: 13px"):
            self.assertIn(want, rule)
        self.assertNotIn("warning", rule)
        self.assertNotIn("border-left-width", rule)

    def test_prior_period_is_said_once_in_the_caption_when_no_tile_has_one(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD"))
        self.assertEqual(html.count("No prior period supplied"), 1)
        self.assertNotIn("kpi-delta", html)
        prior = [dict(r, spend=(r.get("spend") or 0) / 2) for r in cm.load_rows(str(FIXTURE))]
        with_prior, _ = panels.kpi_strip(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD", prior=prior))
        self.assertNotIn("No prior period supplied", with_prior)
        self.assertEqual(with_prior.count("kpi-delta"), 12)

    def test_the_video_sub_label_is_short_and_muted(self):
        html, _ = panels.kpi_strip(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD"))
        self.assertRegex(html, r'<p class="kpi-note">video ads \u00b7 \d+ of \d+</p>')
        self.assertRegex(self.css, r"\.kpi-note \{[^}]*color: var\(--text-muted\)")
