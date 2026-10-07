import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))

import benchmarks  # noqa: E402
import charts  # noqa: E402
import creative_metrics as cm  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
TEMPLATE = ROOT / "skills" / "creative-report" / "assets" / "report-template.html"
FORMATS = ("ugc-video", "static", "founder-video", "partnership", "carousel")


def acme(**changes):
    return panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="USD", **changes)


def row(ad_id, name, day, spend=100.0, impressions=10000.0, **extra):
    base = {"ad_id": ad_id, "ad_name": name, "date": day, "spend": spend, "impressions": impressions, "link_clicks": 100.0,
            "conversions": 5.0, "conversion_value": spend * 3}
    base.update(extra)
    return base


def name_of(fmt, n=1):
    return "angle%d | %s | creator | bau | product | tone | 2026-03-01" % (n, fmt)


def tips(html):
    return re.findall(r' data-tip="([^"]*)"', html)


def group(html, series):
    found = re.search(r'<g data-series="%s"[^>]*>(.*?)</g>' % re.escape(series), html, re.S)
    return found.group(1) if found else None


def view(html, key):
    return html.split('<div class="pick" data-view="%s">' % key)[1].split('<div class="pick"')[0]


class PlumbingTest(unittest.TestCase):
    def test_formats_take_series_one_to_six_by_total_spend_and_the_rest_the_muted_tone(self):
        spend = {"a": 10.0, "b": 70.0, "c": 50.0, "d": 40.0, "e": 30.0, "f": 20.0, "g": 5.0, "h": 1.0}
        colours = charts.format_colours(spend)
        self.assertEqual([colours[k] for k in "bcdefa"], ["var(--series-%d)" % n for n in range(1, 7)])
        self.assertEqual({colours["g"], colours["h"]}, {"var(--series-other)"})

    def test_equal_spend_breaks_a_tie_by_name_so_the_colours_are_stable(self):
        self.assertEqual(charts.format_colours({"b": 5.0, "a": 5.0}), {"a": "var(--series-1)", "b": "var(--series-2)"})

    def test_a_rolling_average_skips_gaps_and_needs_enough_real_values(self):
        values = [1.0, 2.0, None, 4.0, 5.0, 6.0, 7.0, 8.0]
        out = charts.rolling(values, window=7, need=5)
        self.assertEqual(out[:4], [None, None, None, None])
        self.assertIsNone(out[4])
        self.assertAlmostEqual(out[5], (1 + 2 + 4 + 5 + 6) / 5)
        self.assertAlmostEqual(out[7], (2 + 4 + 5 + 6 + 7 + 8) / 6)

    def test_the_default_rolling_average_is_seven_days_needing_five_real_values(self):
        out = charts.rolling([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(out[:4], [None] * 4)
        self.assertAlmostEqual(out[4], 3.0)
        self.assertEqual((charts.SPARK_AVERAGE_DAYS, charts.ROLLING_MIN_VALUES), (7, 5))

    def test_a_day_reads_as_day_and_short_month(self):
        self.assertEqual(charts.day_label("2026-09-07"), "7 Sep")
        self.assertEqual(charts.day_label("week 3"), "week 3")

    def test_hover_text_is_escaped(self):
        self.assertEqual(charts.tip('a"<b>'), ' data-tip="a&quot;&lt;b&gt;"')

    def test_x_labels_are_at_most_eight_and_five_on_a_phone_and_the_phone_set_is_inside_the_wide_set(self):
        for count in (3, 8, 9, 30, 90, 400):
            wide, narrow = charts.x_ticks(count)
            self.assertLessEqual(len(wide), charts.TICKS_WIDE)
            self.assertLessEqual(len(narrow), charts.TICKS_NARROW)
            self.assertTrue(set(narrow) <= set(wide))

    def test_a_narrow_plot_writes_fewer_labels_so_neighbours_never_touch(self):
        wide, _ = charts.x_ticks(30, plot_w=200)
        self.assertLessEqual(len(wide), 200 // charts.LABEL_SLOT)

    def test_drawn_x_labels_keep_a_gap_and_the_phone_ones_are_marked_to_stay(self):
        days = ["2026-03-%02d" % d for d in range(1, 31)]
        svg = charts.line_chart(days, [{"name": "a", "values": [float(i) for i in range(30)]}], "t", str, "u")
        marks = re.findall(r'<text class="tk( tk-wide)?" x="([\d.]+)"', svg)
        xs = [float(x) for _, x in marks]
        self.assertLessEqual(len(xs), charts.TICKS_WIDE)
        self.assertTrue(all(b - a >= charts.LABEL_SLOT for a, b in zip(xs, xs[1:])), xs)
        self.assertLessEqual(sum(1 for flag, _ in marks if not flag), charts.TICKS_NARROW)

    def test_chips_are_buttons_that_start_pressed_and_carry_the_series_name(self):
        html = charts.chips([("Static", "var(--series-1)"), ("A & B", "var(--series-2)")])
        self.assertEqual(re.findall(r'<button type="button" class="legend-chip" data-series="([^"]*)" aria-pressed="true"', html), ["Static", "A &amp; B"])

    def test_a_switcher_with_scripts_off_shows_every_view_stacked_under_its_heading(self):
        html = charts.switcher("x", [("a", "First", "<p>one</p>"), ("b", "Second", "<p>two</p>")])
        self.assertNotIn("hidden", html)
        self.assertEqual(re.findall(r'<h4 class="pick-title">([^<]*)</h4>', html), ["First", "Second"])
        self.assertIn("<p>one</p>", html)
        self.assertIn("<p>two</p>", html)

    def test_a_sparkline_with_hover_text_has_a_column_per_point_and_a_faint_average(self):
        svg = charts.sparkline([1.0, 2.0, None, 4.0], "x", tips=["a", "b", "", "d"], average=[None, 1.5, None, 2.0])
        self.assertEqual(tips(svg), ["a", "b", "d"])
        self.assertIn('<path class="avg"', svg)
        plain = charts.sparkline([1.0, 2.0], "x")
        self.assertNotIn("data-tip", plain)
        self.assertNotIn('class="avg"', plain)


class BenchmarkRulesTest(unittest.TestCase):
    KEYS = ["image", "video", "carousel", "dynamic", "catalog"]

    def test_our_format_words_map_to_a_source_format_or_to_nothing(self):
        table = {"static": "image", "image": "image", "ugc-video": "video", "founder-video": "video", "reel": "video", "video": "video",
                 "carousel": "carousel", "collection": "catalog", "catalogue": "catalog", "dpa": "dynamic", "dynamic": "dynamic",
                 "partnership": None, "ugc": None, "story": None, "unknown": None, "": None}
        for word, key in table.items():
            self.assertEqual(benchmarks.source_key(word, self.KEYS), key, word)

    def test_a_video_word_does_not_map_when_the_source_has_no_video_key(self):
        self.assertIsNone(benchmarks.source_key("ugc-video", ["image", "carousel"]))

    def test_money_figures_show_only_in_the_sources_currency(self):
        band, _ = benchmarks.lookup("cpm", "static", "USD")
        self.assertEqual(band["value"], 6.0)
        band, why = benchmarks.lookup("cpm", "static", "AUD")
        self.assertIsNone(band)
        self.assertEqual(why, "industry figure is in USD; not shown for AUD accounts")
        self.assertIsNone(benchmarks.lookup("cpm", "static", None)[0])

    def test_hold_rate_never_gets_a_band_because_the_definitions_differ(self):
        band, why = benchmarks.lookup("hold_rate", "ugc-video", "USD")
        self.assertIsNone(band)
        self.assertIn("not the same measure", why)

    def test_hook_rate_applies_to_every_video_format_with_the_sources_range(self):
        for fmt in ("ugc-video", "founder-video", "video"):
            band, _ = benchmarks.lookup("hook_rate", fmt, "AUD")
            self.assertEqual((band["value"], band["high"]), (25.44, 29))
        self.assertIsNone(benchmarks.lookup("hook_rate", "static", "USD")[0])

    def test_a_format_the_source_does_not_cover_has_no_band_and_says_so(self):
        band, why = benchmarks.lookup("ctr", "partnership", "USD")
        self.assertIsNone(band)
        self.assertEqual(why, benchmarks.NOT_COVERED)

    def test_ctr_carries_the_clicks_caveat_and_every_band_carries_its_citation(self):
        band, _ = benchmarks.lookup("ctr", "static", "USD")
        text = benchmarks.citation(band)
        self.assertIn("does not say whether clicks are link clicks or all clicks", text)
        self.assertIn("Lebesgue", text)
        self.assertIn("2024", text)
        self.assertIn("A guide, not a target", text)

    def test_every_entry_names_its_source_url_year_and_sample(self):
        for entry in benchmarks.load():
            for field in ("source", "url", "published", "sample", "metric", "metric_definition", "formats", "unit", "caveat"):
                self.assertTrue(entry.get(field), (entry["metric"], field))
            self.assertTrue(entry["url"].startswith("https://"))


class OverTimeTest(unittest.TestCase):
    def setUp(self):
        self.html, self.state = panels.over_time(acme())

    def test_one_view_per_measure_each_with_a_daily_line_and_a_seven_day_average(self):
        self.assertEqual(self.state, "data")
        self.assertEqual(re.findall(r'data-pick="(\w+)"', self.html), ["spend", "roas", "cpa", "ctr", "cpm", "hook_rate"])
        for key in ("spend", "roas", "cpa", "ctr", "cpm", "hook_rate"):
            chart = view(self.html, key)
            self.assertIsNotNone(group(chart, "Daily"), key)
            self.assertIsNotNone(group(chart, "7-day average"), key)

    def test_spend_bars_sit_behind_every_measure_but_spend_itself(self):
        self.assertIsNone(group(view(self.html, "spend"), "Spend"))
        self.assertIsNotNone(group(view(self.html, "roas"), "Spend"))

    def test_a_days_roas_is_the_ratio_of_that_days_sums_never_an_average_of_ads(self):
        rows = [r for r in cm.load_rows(str(FIXTURE)) if r["date"] == "2026-03-07"]
        expected = sum(r["conversion_value"] for r in rows) / sum(r["spend"] for r in rows)
        self.assertIn("Daily, 7 Mar: %.2fx" % expected, tips(view(self.html, "roas")))

    def test_a_missing_day_is_a_gap_in_the_line_and_never_a_zero(self):
        rows = [row("a", name_of("static"), d) for d in ("2026-03-01", "2026-03-02", "2026-03-04", "2026-03-05")]
        html, _ = panels.over_time(panels.Ctx(rows=rows, currency="USD"))
        chart = view(html, "spend")
        self.assertEqual(len(re.findall(r'class="line daily" style="[^"]*" d="([^"]*)"', chart)[0].split("M")) - 1, 2)
        self.assertFalse([t for t in tips(chart) if t.startswith("Daily, 3 Mar")])
        self.assertTrue(any(t.startswith("Daily, 4 Mar") for t in tips(chart)))

    def test_a_measure_with_no_data_is_left_out_and_named(self):
        rows = [{"ad_id": "a", "ad_name": name_of("static"), "date": d, "spend": 5.0, "impressions": 900.0} for d in ("2026-03-01", "2026-03-02")]
        html, state = panels.over_time(panels.Ctx(rows=rows, currency="USD"))
        self.assertEqual(state, "data")
        self.assertEqual(re.findall(r'data-pick="(\w+)"', html), ["spend", "cpm"])
        self.assertIn("Not shown, no data for it: ROAS, CPA, CTR, Hook rate.", html)

    def test_without_dates_it_is_a_labelled_empty_state(self):
        rows = [{"ad_id": "a", "ad_name": name_of("static"), "spend": 5.0, "impressions": 900.0}]
        html, state = panels.over_time(panels.Ctx(rows=rows, currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("Why this is empty:", html)
        self.assertIn("How to get it:", html)

    def test_the_axis_names_each_measures_unit(self):
        self.assertIn(">ROAS (x)</text>", view(self.html, "roas"))
        self.assertIn(">CTR (%)</text>", view(self.html, "ctr"))
        self.assertIn(">Spend (USD)</text>", view(self.html, "roas"))

    def test_every_point_has_hover_text_with_its_exact_value(self):
        chart = view(self.html, "cpa")
        self.assertEqual(len([t for t in tips(chart) if t.startswith("Daily,")]), 30)
        self.assertTrue(all(re.search(r"USD [\d,]+\.\d\d$", t) for t in tips(chart) if t.startswith("Daily,")))


class SpendByFormatTest(unittest.TestCase):
    def test_each_format_is_a_band_in_the_one_colour_it_has_everywhere(self):
        ctx = acme()
        html, state = panels.spend_by_format(ctx)
        self.assertEqual(state, "data")
        for fmt in FORMATS:
            name = ctx.format_name(fmt)
            self.assertIn('<g data-series="%s" data-dim="1"><path class="area" style="fill:%s"' % (name, ctx.colour(fmt)), html)
        self.assertEqual(len(set(ctx.colour(f) for f in FORMATS)), 5)

    def test_hovering_a_day_lists_every_formats_share_and_they_add_to_a_hundred(self):
        html, _ = panels.spend_by_format(acme())
        day = [t for t in tips(html) if t.startswith("7 Mar:")][0]
        shares = [float(n) for n in re.findall(r"(\d+)%", day)]
        self.assertAlmostEqual(sum(shares), 100, delta=len(shares) * 0.5)

    def test_one_format_is_an_empty_state(self):
        rows = [row("a", name_of("static"), "2026-03-01"), row("a", name_of("static"), "2026-03-02")]
        html, state = panels.spend_by_format(panels.Ctx(rows=rows, currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("Fewer than two formats", html)

    def test_turning_a_chip_off_dims_a_band_instead_of_leaving_a_gap(self):
        self.assertIn('svg g.is-off[data-dim] { display: inline; opacity: 0.12; }', TEMPLATE.read_text())


class FormatBenchmarksTest(unittest.TestCase):
    def setUp(self):
        self.ctx = acme()
        self.html, self.state = panels.format_benchmarks(self.ctx)

    def ratio_of_sums(self, fmt, num, den, scale=1.0, rows=None):
        picked = [r for r in (rows or self.ctx.rows_of_format(fmt))]
        return sum(r[num] for r in picked if r.get(num) is not None) / sum(r[den] for r in picked if r.get(den) is not None) * scale

    def test_one_view_per_measure_and_never_one_for_hold_rate(self):
        self.assertEqual(self.state, "data")
        self.assertEqual(re.findall(r'data-pick="(\w+)"', self.html), ["ctr", "cpm", "roas", "cvr", "hook_rate"])
        self.assertIn("not the same measure", self.html)

    def test_a_format_row_is_a_dot_a_band_tick_and_a_shared_median_line(self):
        ctr = view(self.html, "ctr")
        self.assertEqual(len(re.findall(r'<circle class="pt"', ctr)), 5)
        self.assertEqual(len(re.findall(r'class="band-tick"', ctr)), 4)
        self.assertEqual(len(re.findall(r'class="guide"', ctr)), 1)

    def test_the_dot_is_the_ratio_of_summed_counts_for_that_format(self):
        expected = self.ratio_of_sums("static", "link_clicks", "impressions", 100)
        self.assertIn("Static: %.2f%%" % expected, tips(view(self.html, "ctr")))

    def test_the_median_line_is_the_median_across_the_accounts_formats(self):
        values = [self.ratio_of_sums(f, "link_clicks", "impressions", 100) for f in FORMATS]
        self.assertIn("Median across your formats: %.2f%%" % statistics.median(values), tips(view(self.html, "ctr")))

    def test_a_format_with_no_public_figure_has_no_band_and_the_panel_names_it(self):
        ctr = view(self.html, "ctr")
        partnership = group(ctr, "Partnership")
        self.assertNotIn("band", partnership)
        self.assertIn("No industry band for Partnership: no public figure for this format.", ctr)

    def test_every_band_is_cited_under_the_chart_with_its_not_a_target_warning(self):
        ctr = view(self.html, "ctr")
        self.assertIn("Industry figure: Lebesgue, Facebook Ads Creatives Benchmarks, 2024, ecommerce advertisers", ctr)
        self.assertIn("The source does not say whether clicks are link clicks or all clicks.", ctr)
        self.assertEqual(ctr.count("A guide, not a target"), 1)
        self.assertIn("Billo, Hook to Hold, 2026", view(self.html, "hook_rate"))

    def test_hook_rate_bands_read_as_a_range_on_video_formats_only(self):
        hook = view(self.html, "hook_rate")
        self.assertEqual(len(re.findall(r'class="band"', hook)), 2)
        self.assertIn("(range 25.44% to 29.00%)", hook)
        self.assertEqual(len(re.findall(r'class="band-tick"', hook)), 2)
        self.assertIn(">n/a</text>", group(hook, "Static"))

    def test_money_bands_are_left_off_an_account_in_another_currency_and_say_why(self):
        html, _ = panels.format_benchmarks(panels.Ctx(rows=cm.load_rows(str(FIXTURE)), currency="AUD"))
        cpm = view(html, "cpm")
        self.assertNotIn('class="band-tick"', cpm)
        self.assertIn("industry figure is in USD; not shown for AUD accounts", cpm)
        self.assertIn('class="band-tick"', view(html, "ctr"))

    def test_the_footer_lists_each_source_drawn_with_its_url_and_year(self):
        page = report.build_html(rows=cm.load_rows(str(FIXTURE)), currency="USD")
        line = re.search(r"Industry figures: ([^\n]*)", page).group(1)
        self.assertIn("Lebesgue, Facebook Ads Creatives Benchmarks (2024), https://lebesgue.io/", line)
        self.assertIn("Billo, Hook to Hold (2026), https://billo.app/", line)
        self.assertIn("never change a grade", line)

    def test_a_page_with_no_band_drawn_says_none_shown(self):
        rows = [row("a", name_of("partnership"), "2026-03-01"), row("b", name_of("story"), "2026-03-01")]
        page = report.build_html(rows=rows, currency="USD")
        self.assertIn("Industry figures: none shown.", page)

    def test_benchmarks_never_change_a_verdict_a_grade_or_what_to_do_first(self):
        verdicts = json.loads(subprocess.run([sys.executable, str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"), str(FIXTURE), "--json"],
                                             capture_output=True, text=True, check=True).stdout)
        outputs = []
        for entries in (None, []):
            original = benchmarks.load
            if entries is not None:
                benchmarks.load = lambda path=None: []
            try:
                ctx = panels.Ctx(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, currency="USD")
                outputs.append((panels.verdict_board(ctx), panels.do_first(ctx), panels.all_ads(ctx)))
            finally:
                benchmarks.load = original
        self.assertEqual(outputs[0], outputs[1])

    def test_without_rows_or_formats_it_is_a_labelled_empty_state(self):
        for ctx in (panels.Ctx(), panels.Ctx(rows=[row("a", "plain name", "2026-03-01")], currency="USD")):
            html, state = panels.format_benchmarks(ctx)
            self.assertEqual(state, "empty")
            self.assertIn("Why this is empty:", html)
            self.assertIn("How to get it:", html)


class FormatsOverTimeTest(unittest.TestCase):
    def setUp(self):
        self.ctx = acme()
        self.html, self.state = panels.formats_over_time(self.ctx)

    def test_four_small_charts_one_line_per_format_and_a_dashed_account_line(self):
        self.assertEqual(self.state, "data")
        self.assertEqual(re.findall(r"<h4>([^<]*)</h4>", self.html), ["CTR", "CPM", "ROAS", "Hook rate"])
        ctr = self.html.split("<h4>CTR</h4>")[1].split("</figure>")[0]
        for fmt in ("ugc-video", "static", "founder-video", "partnership", "carousel"):
            self.assertIsNotNone(group(ctr, self.ctx.format_name(fmt)))
        self.assertIn('class="line dashed"', group(ctr, panels.ALL_FORMATS))

    def test_a_point_is_that_weeks_ratio_of_sums_for_that_format(self):
        rows = [r for r in self.ctx.rows_of_format("static") if "2026-03-09" <= r["date"] <= "2026-03-15"]
        expected = sum(r["link_clicks"] for r in rows) / sum(r["impressions"] for r in rows) * 100
        ctr = self.html.split("<h4>CTR</h4>")[1].split("</figure>")[0]
        self.assertIn("Static, 9 Mar: %.2f%%" % expected, tips(ctr))

    def test_part_weeks_are_labelled_and_weeks_start_on_monday(self):
        self.assertIn("1 Mar (part)", self.html)
        self.assertIn("30 Mar (part)", self.html)
        start = panels.week_axis(__import__("datetime").date(2026, 3, 1), __import__("datetime").date(2026, 3, 30))
        self.assertTrue(all(d.weekday() == 0 for d, _ in start))

    def test_a_format_week_under_the_impressions_floor_is_left_off_its_line(self):
        rows = [row("a", name_of("static"), d, impressions=5000.0) for d in ("2026-03-02", "2026-03-03", "2026-03-09")]
        rows += [row("b", name_of("carousel"), d, impressions=5000.0) for d in ("2026-03-02", "2026-03-03", "2026-03-09", "2026-03-10", "2026-03-16", "2026-03-17")]
        rows += [row("a", name_of("static"), "2026-03-16", impressions=999.0)]
        html, _ = panels.formats_over_time(panels.Ctx(rows=rows, currency="USD"))
        ctr = html.split("<h4>CTR</h4>")[1].split("</figure>")[0]
        self.assertEqual(charts.MIN_WEEK_IMPRESSIONS, 1000)
        self.assertFalse([t for t in tips(ctr) if t.startswith("Static, 16 Mar")])
        self.assertTrue([t for t in tips(ctr) if t.startswith("Static, 9 Mar")])
        self.assertTrue([t for t in tips(ctr) if t.startswith("Carousel, 16 Mar")])

    def test_less_than_two_weeks_is_an_empty_state(self):
        rows = [row("a", name_of("static"), "2026-03-02"), row("b", name_of("carousel"), "2026-03-03")]
        html, state = panels.formats_over_time(panels.Ctx(rows=rows, currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("less than two calendar weeks", html)

    def test_one_row_of_chips_toggles_all_four_charts_and_the_charts_hold_no_chips_of_their_own(self):
        self.assertEqual(self.html.count('class="legend-chips"'), 1)
        self.assertIn('class="multiples-wrap" data-scope="1"', self.html)

    def test_a_small_chart_has_no_rotated_title_to_collide_with_its_ticks(self):
        self.assertNotIn("rotate(-90", self.html)

    def test_the_account_line_is_neutral_and_formats_keep_their_page_colours(self):
        ctr = self.html.split("<h4>CTR</h4>")[1].split("</figure>")[0]
        self.assertIn('style="stroke:var(--heading)"', group(ctr, panels.ALL_FORMATS))
        self.assertIn('style="stroke:%s"' % self.ctx.colour("static"), group(ctr, "Static"))


class SpendReturnTest(unittest.TestCase):
    def setUp(self):
        self.ctx = acme()
        self.html, self.state = panels.spend_vs_return(self.ctx)

    def test_one_bubble_per_format_in_its_colour_with_purchases_as_the_area(self):
        self.assertEqual(self.state, "data")
        discs = re.findall(r'<circle class="bub"[^>]*style="fill:([^;]*);', self.html)
        self.assertEqual(sorted(discs), sorted(self.ctx.colour(f) for f in FORMATS))
        self.assertIn("Bubble area is purchases", self.html)

    def test_the_dashed_line_is_the_account_roas_and_there_is_no_vertical_one(self):
        account = cm.compute_metrics(panels.totals(self.ctx.rows))["roas"]
        self.assertIn("(%.2fx)" % account, self.html)
        self.assertEqual(self.html.count('class="guide"'), 1)
        self.assertRegex(self.html, r'<line class="guide" x1="[\d.]+" y1="([\d.]+)" x2="[\d.]+" y2="\1"')

    def test_a_bubbles_x_is_that_formats_share_of_spend(self):
        total = sum(self.ctx.format_spend.values())
        share = self.ctx.format_spend["static"] / total * 100
        self.assertRegex(self.html, r"Static: Share of spend \(%%\) %.2f" % share)

    def test_without_purchase_value_it_is_an_empty_state(self):
        rows = [{"ad_id": "a", "ad_name": name_of("static"), "date": "2026-03-01", "spend": 5.0, "impressions": 900.0},
                {"ad_id": "b", "ad_name": name_of("carousel"), "date": "2026-03-01", "spend": 5.0, "impressions": 900.0}]
        html, state = panels.spend_vs_return(panels.Ctx(rows=rows, currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("Why this is empty:", html)


class AdAgeTest(unittest.TestCase):
    def setUp(self):
        self.ctx = acme()
        self.html, self.state = panels.ad_age(self.ctx)

    def test_five_buckets_each_with_its_ad_count_and_the_counts_add_to_every_ad(self):
        self.assertEqual(self.state, "data")
        roas = view(self.html, "roas")
        self.assertEqual(re.findall(r'<text class="tk" x="[\d.]+" y="\d+" text-anchor="middle">([^<]*)</text>', roas),
                         ["0-6 days", "7-15 days", "16-32 days", "33-65 days", "66+ days"])
        counts = [int(n) for n in re.findall(r'class="count"[^>]*>(\d+) ads?[:<]', roas)]
        self.assertEqual(sum(counts), len(self.ctx.ads))

    def test_spend_shares_add_to_a_hundred(self):
        shares = [float(n) for n in re.findall(r"([\d.]+)% of spend", view(self.html, "roas"))]
        self.assertAlmostEqual(sum(shares), 100, delta=0.3)

    def test_a_buckets_dot_is_the_ratio_of_sums_for_the_ads_in_it(self):
        young = [a for a in self.ctx.ads if a["age_days"] < panels.AGE_EDGES[0]]
        rows = [r for a in young for r in self.ctx.rows_by_ad[str(a["ad_id"])]]
        expected = sum(r["conversion_value"] for r in rows) / sum(r["spend"] for r in rows)
        self.assertIn("0-6 days, ROAS: %.2fx" % expected, tips(view(self.html, "roas")))

    def test_roas_and_ctr_share_the_bars_with_one_right_axis_each_behind_a_switcher(self):
        self.assertEqual(re.findall(r'data-pick="(\w+)"', self.html), ["roas", "ctr"])

    def test_the_caption_says_whether_age_comes_from_creation_or_first_delivery(self):
        self.assertIn("first day of delivery", self.html)
        rows = [row("a", name_of("static"), d, created_time="2025-12-01") for d in ("2026-03-01", "2026-03-02")]
        html, _ = panels.ad_age(panels.Ctx(rows=rows, currency="USD"))
        self.assertIn("from each ad's creation date", html)
        self.assertIn("66+ days, ROAS", " ".join(tips(html)))

    def test_without_dates_it_is_a_labelled_empty_state(self):
        html, state = panels.ad_age(panels.Ctx(rows=[{"ad_id": "a", "ad_name": name_of("static"), "spend": 5.0}], currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("How to get it:", html)

    def test_the_bucket_edges_avoid_the_values_a_default_may_not_use(self):
        self.assertEqual(panels.AGE_EDGES, (7, 16, 33, 66))


class LaunchesTest(unittest.TestCase):
    def setUp(self):
        self.ctx = acme()
        self.html, self.state = panels.launches(self.ctx)

    def test_every_ad_is_counted_once_in_the_week_it_first_delivered(self):
        self.assertEqual(self.state, "data")
        counted = sum(int(n) for n in re.findall(r": (\d+) new ads?\"", self.html))
        self.assertEqual(counted, len(self.ctx.ads))

    def test_the_bars_are_split_by_format_in_the_page_colours(self):
        for fmt in FORMATS:
            self.assertIn('<g data-series="%s" data-dim="1"><rect class="seg-bar" style="fill:%s"' % (self.ctx.format_name(fmt), self.ctx.colour(fmt)), self.html)

    def test_the_caption_gives_the_average_per_week_and_the_first_week_caveat(self):
        self.assertIn("On average %.1f new ads a week over 6 weeks" % (len(self.ctx.ads) / 6), self.html)
        self.assertIn("already running at the start of the data fall in its first week", self.html)

    def test_without_dates_it_is_a_labelled_empty_state(self):
        html, state = panels.launches(panels.Ctx(rows=[{"ad_id": "a", "ad_name": name_of("static"), "spend": 5.0}], currency="USD"))
        self.assertEqual(state, "empty")
        self.assertIn("Why this is empty:", html)


class KpiSparklineTest(unittest.TestCase):
    def test_each_tile_line_has_hover_text_per_day_and_a_faint_seven_day_average(self):
        html, _ = panels.kpi_strip(acme())
        tile = re.search(r'<div class="kpi[^"]*"><p class="kpi-name">ROAS.*?</div></div>', html, re.S).group(0)
        rows = [r for r in cm.load_rows(str(FIXTURE)) if r["date"] == "2026-03-07"]
        expected = sum(r["conversion_value"] for r in rows) / sum(r["spend"] for r in rows)
        self.assertIn("7 Mar: %.2fx" % expected, tips(tile))
        self.assertIn('<path class="avg"', tile)

    def test_a_day_with_no_value_has_no_hover_column(self):
        rows = [row("a", name_of("static"), d) for d in ("2026-03-01", "2026-03-02", "2026-03-04")]
        html, _ = panels.kpi_strip(panels.Ctx(rows=rows, currency="USD"))
        tile = re.search(r'<p class="kpi-name">Spend.*?</div></div>', html, re.S).group(0)
        self.assertEqual(len(tips(tile)), 3)


class EveryChartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = acme()
        cls.page = report.build_html(rows=cls.ctx.rows, currency="USD")

    def test_each_new_panel_is_data_on_acme_and_a_labelled_empty_state_without_its_source(self):
        ids = ("time", "money-by-format", "format-benchmarks", "formats-over-time", "spend-return", "ad-age", "launches")
        fns = {pid: fn for _, _, tab in panels.TABS for pid, _, _, fn in tab}
        for pid in ids:
            html, state = fns[pid](self.ctx)
            self.assertEqual(state, "data", pid)
            html, state = fns[pid](panels.Ctx())
            self.assertEqual(state, "empty", pid)
            self.assertIn("Why this is empty:", html, pid)
            self.assertIn("How to get it:", html, pid)

    def test_a_format_has_one_colour_across_every_format_chart(self):
        spend = {}
        for r in self.ctx.rows:
            fmt = r["ad_name"].split(" | ")[1]
            spend[fmt] = spend.get(fmt, 0.0) + r["spend"]
        expected = charts.format_colours(spend)
        self.assertEqual(len(set(expected.values())), 5)
        for fmt in FORMATS:
            colour, name = expected[fmt], self.ctx.format_name(fmt)
            for html in (panels.spend_by_format(self.ctx)[0], panels.launches(self.ctx)[0]):
                self.assertIn('<g data-series="%s" data-dim="1"><' % name, html)
                self.assertIn(colour, group(html, name))
            self.assertIn('style="fill:%s"' % colour, group(view(panels.format_benchmarks(self.ctx)[0], "ctr"), name))
            self.assertIn('stroke:%s' % colour, group(panels.formats_over_time(self.ctx)[0], name))
            self.assertIn('style="fill:%s;stroke:%s"' % (colour, colour), panels.spend_vs_return(self.ctx)[0])

    def test_marks_carry_hover_text_and_points_are_keyboard_reachable_in_small_charts(self):
        for html in (panels.over_time(self.ctx)[0], panels.format_benchmarks(self.ctx)[0], panels.ad_age(self.ctx)[0]):
            self.assertTrue(tips(html))
            self.assertRegex(html, r'<circle class="pt[ "]')
            self.assertRegex(html, r'<circle class="pt[^"]*"[^>]*tabindex="0"')

    def test_a_chart_with_many_points_is_hover_only(self):
        days = ["2027-01-%02d" % d for d in range(1, 29)] + ["2027-02-%02d" % d for d in range(1, 29)] + ["2027-03-%02d" % d for d in range(1, 10)]
        svg = charts.line_chart(days, [{"name": "a", "values": [1.0] * len(days)}], "t", str, "u")
        self.assertGreater(len(days), charts.POINT_FOCUS_MAX)
        self.assertNotIn("tabindex", svg)

    def test_the_page_carries_the_tooltip_chips_and_switcher_script_and_the_phone_tick_rule(self):
        template = TEMPLATE.read_text()
        self.assertIn('document.addEventListener(name, function (event) { var t = tipFor(event.target); if (t) { showTip(t); } });', template)
        self.assertRegex(template, r"@media \(max-width: 480px\) \{\s*svg \.tk-wide \{ display: none; \}")

    def test_no_chart_uses_a_colour_that_is_not_a_page_token(self):
        for panel in ("money-by-format", "format-benchmarks", "formats-over-time", "spend-return", "ad-age", "launches", "time"):
            html = {pid: fn for _, _, tab in panels.TABS for pid, _, _, fn in tab}[panel](self.ctx)[0]
            self.assertNotRegex(html, r'(?:fill|stroke|background):\s*#[0-9a-fA-F]{3,8}', panel)

    def test_the_footer_names_the_chart_settings_that_are_arbitrary(self):
        self.assertIn("rolling averages cover 7 days and need 5 days with data", self.page)
        self.assertIn("new ad-age buckets start at 7, 16, 33 and 66 days", self.page)


def day_rows(n, **fields):
    """n daily rows for one ad from 1 Mar, each with the given fields (a field of None is absent that day)."""
    out = []
    for i in range(n):
        base = {"ad_id": "a", "ad_name": name_of("static"), "date": "2026-03-%02d" % (i + 1)}
        base.update({k: (v(i) if callable(v) else v) for k, v in fields.items()})
        out.append(base)
    return out


class RollingAverageTest(unittest.TestCase):
    def roll(self, rows, key):
        return panels.rolling_values(panels.calendar(rows), key)

    def test_a_count_measure_averages_per_day_it_never_sums_the_window(self):
        out = self.roll(day_rows(8, spend=10.0, impressions=1000.0), "impressions")
        self.assertAlmostEqual(out[7], 1000.0)
        self.assertAlmostEqual(self.roll(day_rows(8, spend=10.0, impressions=1000.0), "spend")[7], 10.0)

    def test_a_ratio_counts_and_sums_only_days_that_carry_both_operands(self):
        rows = day_rows(8, spend=10.0, impressions=1000.0, conversion_value=lambda i: None if i < 3 else 50.0)
        out = self.roll(rows, "roas")
        self.assertIsNone(out[6])
        self.assertAlmostEqual(out[7], 5.0)

    def test_a_day_with_rows_but_no_spend_is_not_a_zero_in_the_average(self):
        rows = day_rows(7, impressions=1000.0, spend=lambda i: None if i == 2 else 10.0)
        self.assertAlmostEqual(self.roll(rows, "spend")[6], 10.0)


class BenchmarkDefinitionRuleTest(unittest.TestCase):
    ENTRY = {"source": "S", "url": "https://x.example/", "published": "2026-01-01", "sample": "s", "metric": "ctr", "metric_definition": "d",
             "unit": "pct", "caveat": "the caveat", "formats": {"video": {"value": 1.0}}}

    def lookup(self, definition):
        return benchmarks.lookup("ctr", "video", "USD", [dict(self.ENTRY, definition=definition)])

    def test_a_definition_that_differs_from_ours_gets_no_band(self):
        band, why = self.lookup("differs")
        self.assertIsNone(band)
        self.assertIn("differs from ours", why)

    def test_a_definition_the_source_does_not_state_gets_a_band_with_its_caveat(self):
        band, _ = self.lookup("not_stated")
        self.assertEqual(band["value"], 1.0)
        self.assertIn("the caveat", benchmarks.citation(band))

    def test_a_matching_definition_gets_a_band(self):
        self.assertEqual(self.lookup("matches")[0]["value"], 1.0)

    def test_every_entry_says_which_of_the_three_cases_it_is(self):
        found = {e["metric"]: e["definition"] for e in benchmarks.load()}
        self.assertEqual(found, {"ctr": "not_stated", "cpm": "matches", "cvr": "not_stated", "roas": "matches", "hook_rate": "matches"})

    def test_the_panel_and_the_docs_state_the_two_case_rule(self):
        html, _ = panels.format_benchmarks(acme())
        self.assertIn("differs from ours", html)
        self.assertIn("does not state", html)
        skill = (ROOT / "skills" / "creative-report" / "SKILL.md").read_text()
        design = (ROOT / "skills" / "creative-report" / "references" / "report-design.md").read_text()
        for text in (skill, design):
            self.assertIn("not_stated", text)
            self.assertIn("differs", text)


class ReviewCodeFixesTest(unittest.TestCase):
    def test_axis_labels_and_counts_sit_outside_every_series_group(self):
        ctx = acme()
        for html in (panels.ad_age(ctx)[0], panels.launches(ctx)[0], panels.formats_over_time(ctx)[0], panels.format_benchmarks(ctx)[0], panels.over_time(ctx)[0]):
            for body in re.findall(r'<g data-series="[^"]*"[^>]*>(.*?)</g>', html, re.S):
                self.assertNotIn('class="tk', body)
                self.assertNotIn('class="count"', body)

    def test_the_dead_notice_leftovers_are_gone(self):
        self.assertFalse(hasattr(panels, "NEEDS_ACCOUNT"))
        self.assertNotIn(".notice", TEMPLATE.read_text())
        self.assertIn("banner", (ROOT / "skills" / "creative-report" / "references" / "report-design.md").read_text().split("## Panels and states")[1])

    def test_buckets_are_described_by_where_they_start(self):
        html, _ = panels.ad_age(acme())
        self.assertIn("new buckets start at 7, 16, 33 and 66 days", html)
        page = report.build_html(rows=cm.load_rows(str(FIXTURE)), currency="USD")
        self.assertIn("new ad-age buckets start at 7, 16, 33 and 66 days", page)

    def test_benchmarks_never_change_the_verdict_do_first_or_grade_sections_of_the_whole_report(self):
        verdicts = json.loads(subprocess.run([sys.executable, str(ROOT / "skills" / "keep-or-kill" / "scripts" / "verdicts.py"), str(FIXTURE), "--json"],
                                             capture_output=True, text=True, check=True).stdout)
        grade = json.loads(subprocess.run([sys.executable, str(ROOT / "skills" / "creative-grader" / "scripts" / "grade.py"), str(FIXTURE), "--json"],
                                          capture_output=True, text=True, check=True).stdout)

        def sections(page):
            return [re.search(r'<section class="card panel" id="panel-%s".*?</section>' % pid, page, re.S).group(0) for pid in ("board", "do-first", "improve", "all-ads")]

        with_ = report.build_html(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, grade=grade, currency="USD")
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "none.json"
            empty.write_text("[]")
            original = benchmarks.DATA
            benchmarks.DATA = empty
            try:
                without = report.build_html(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, grade=grade, currency="USD")
            finally:
                benchmarks.DATA = original
        self.assertIn("Lebesgue", with_)
        self.assertNotIn("Lebesgue", without)
        self.assertEqual(sections(with_), sections(without))


class NiceTicksTest(unittest.TestCase):
    def test_a_domain_is_rounded_out_to_a_step_of_one_two_two_and_a_half_or_five(self):
        for low, high in ((0, 5044), (0, 1.56), (0, 100), (3.0, 6.0), (0, 91), (0.9, 1.9), (0, 6.33)):
            lo, hi, ticks = charts.nice_scale(low, high)
            self.assertLessEqual(lo, low)
            self.assertGreaterEqual(hi, high)
            self.assertTrue(3 <= len(ticks) <= 5, (low, high, ticks))
            step = ticks[1] - ticks[0]
            mantissa = step / 10 ** __import__("math").floor(__import__("math").log10(step))
            self.assertTrue(any(abs(mantissa - m) < 1e-9 for m in (1, 2, 2.5, 5)), (low, high, step))

    def test_known_domains(self):
        self.assertEqual(charts.nice_scale(0, 100)[2], [0, 25, 50, 75, 100])
        self.assertEqual(charts.nice_scale(0, 1.56)[2], [0, 0.5, 1.0, 1.5, 2.0])
        self.assertEqual(charts.nice_scale(0, 5044)[2], [0, 2000, 4000, 6000])

    def test_the_time_chart_axis_uses_them(self):
        days = ["2026-03-%02d" % d for d in range(1, 9)]
        svg = charts.line_chart(days, [{"name": "a", "values": [0.0, 5044.0] + [100.0] * 6}], "t", charts.axis_format("money", "USD"), "u")
        left = re.findall(r'<text x="[\d.]+" y="[\d.]+" text-anchor="end">([^<]*)</text>', svg)
        self.assertEqual(left, ["0", "2,000", "4,000", "6,000"])


class ReviewVisualFixesTest(unittest.TestCase):
    def test_the_benchmark_chart_fits_a_phone_and_its_scale_covers_every_dot(self):
        rows = [{"name": n, "value": v, "colour": "var(--series-1)", "band": None} for n, v in (("A", 1.30), ("B", 1.56), ("C", 1.47))]
        svg = charts.benchmark_rows(rows, 1.47, charts.axis_format("pct"), "t", "CTR (%)", tip_fmt=lambda v: "%.2f%%" % v)
        self.assertLessEqual(int(re.search(r'viewBox="0 0 (\d+)', svg).group(1)), 480)
        self.assertIn("wide fit", svg)
        ticks = [float(t.rstrip("%")) for t in re.findall(r'text-anchor="middle">([\d.]+%)</text>', svg)]
        self.assertGreaterEqual(max(ticks), 1.56)

    def test_the_first_six_series_hues_are_at_least_thirty_degrees_apart(self):
        import colorsys
        css = TEMPLATE.read_text()
        hues = []
        for n in range(1, 7):
            hexed = re.search(r"--series-%d: #([0-9a-fA-F]{6})" % n, css).group(1)
            r, g, b = (int(hexed[i:i + 2], 16) / 255 for i in (0, 2, 4))
            hues.append(colorsys.rgb_to_hsv(r, g, b)[0] * 360)
        for i in range(6):
            for j in range(i + 1, 6):
                gap = abs(hues[i] - hues[j])
                self.assertGreaterEqual(min(gap, 360 - gap), 30, (i + 1, j + 1, hues))

    def test_legend_chips_are_neutral_and_do_not_share_the_filter_chip_class(self):
        html = charts.chips([("A", "var(--series-1)")])
        self.assertIn('class="legend-chip"', html)
        self.assertNotIn('class="chip"', html)
        css = TEMPLATE.read_text()
        self.assertRegex(css, r"\.legend-chip \{[^}]*background: var\(--surface\)")
        self.assertRegex(css, r'\.legend-chip\[aria-pressed="false"\] \{[^}]*color: var\(--text-muted\)')
        self.assertRegex(css, r'\.legend-chip\[aria-pressed="false"\] \.sw \{[^}]*background: transparent')

    def test_the_industry_mark_is_labelled_and_the_chart_has_a_key_and_two_decimals(self):
        html = panels.format_benchmarks(acme())[0]
        ctr = html.split('<div class="pick" data-view="ctr">')[1].split('<div class="pick"')[0]
        self.assertIn("industry 0.91%", ctr)
        self.assertIn("1.30%", ctr)
        self.assertIn("Dot = your value", ctr)
        self.assertNotIn(">1.3%<", ctr)

    def test_a_part_week_is_labelled_by_its_first_day_with_data(self):
        html = panels.formats_over_time(acme())[0]
        self.assertIn("1 Mar (part)", html)
        self.assertNotIn("23 Feb", html)
        self.assertIn("fewer than 1,000 impressions", html)

    def test_age_dots_are_labelled_and_a_thin_bucket_says_so(self):
        html = panels.ad_age(acme())[0]
        self.assertRegex(html, r'class="dot-label"[^>]*>[\d.]+x<')
        self.assertIn("1 ad: too few to read", html)
        self.assertIn('class="thin"', html)

    def test_the_daily_line_is_a_light_tint_and_the_average_is_the_solid_line(self):
        chart = panels.over_time(acme())[0].split('<div class="pick" data-view="roas">')[1]
        self.assertIn('class="line daily"', chart)
        self.assertRegex(TEMPLATE.read_text(), r"svg \.line\.daily \{[^}]*opacity")

    def test_all_formats_the_unknown_format_and_the_seventh_format_have_three_different_greys(self):
        self.assertEqual(charts.OTHER_COLOUR, "var(--series-other)")
        self.assertEqual(panels.ALL_FORMATS_COLOUR, "var(--heading)")
        self.assertEqual(len({charts.OTHER_COLOUR, panels.ALL_FORMATS_COLOUR, "var(--series-neutral)"}), 3)
        self.assertIn("--series-other:", TEMPLATE.read_text())


HARNESS = r"""
function Node(tag, attrs) {
  this.tag = tag; this.attrs = attrs || {}; this.children = []; this.parent = null; this.handlers = {}; this.hidden = false;
  var self = this, set = {};
  this.classList = {
    toggle: function (c, on) { if (on === undefined ? !set[c] : on) { set[c] = true; } else { delete set[c]; } },
    add: function (c) { set[c] = true; }, contains: function (c) { return !!set[c]; }
  };
}
Node.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Node.prototype.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; };
Node.prototype.add = function (c) { c.parent = this; this.children.push(c); return c; };
Node.prototype.addEventListener = function (n, f) { (this.handlers[n] = this.handlers[n] || []).push(f); };
Node.prototype.click = function () { (this.handlers.click || []).forEach(function (f) { f({ target: this }); }.bind(this)); };
Node.prototype.closest = function (sel) {
  var k = sel.slice(1, -1), n = this;
  while (n) { if (n.getAttribute(k) !== null) { return n; } n = n.parent; }
  return null;
};
Node.prototype.all = function (pred) {
  var out = [];
  (function walk(n) { n.children.forEach(function (c) { if (pred(c)) { out.push(c); } walk(c); }); })(this);
  return out;
};
Node.prototype.querySelector = function (sel) { return this.all(function (n) { return n.cls === sel.slice(1); })[0] || null; };
function el(tag, cls, attrs, parent) { var n = new Node(tag, attrs); n.cls = cls; parent.add(n); return n; }
var root = new Node("root");
var fig = el("figure", "", { "data-scope": "1" }, root);
var chips = ["A", "B"].map(function (s) { return el("button", "legend-chip", { "data-series": s, "aria-pressed": "true" }, fig); });
var groups = ["A", "B"].map(function (s) { return el("g", "", { "data-series": s }, fig); });
var sw = el("div", "switch", {}, root);
var bar = el("div", "seg", {}, sw);
var btns = ["x", "y"].map(function (k, i) { return el("button", "", { "data-pick": k, "aria-pressed": i ? "false" : "true" }, bar); });
var views = ["x", "y"].map(function (k) { return el("div", "pick", { "data-view": k }, sw); });
function matches(n, sel) {
  if (sel === ".legend-chip") { return n.cls === "legend-chip"; }
  if (sel === ".switch") { return n.cls === "switch"; }
  if (sel === ".pick") { return n.cls === "pick"; }
  if (sel === "g[data-series]") { return n.tag === "g" && n.getAttribute("data-series") !== null; }
  if (sel === "[data-pick]") { return n.getAttribute("data-pick") !== null; }
  return false;
}
function $all(sel, from) { return (from || root).all(function (n) { return matches(n, sel); }); }
var handlers = {};
var document = { addEventListener: function (n, f) { handlers[n] = f; }, createElement: function () { return new Node("div"); }, body: new Node("body") };
var window = { addEventListener: function () {}, innerWidth: 800 };
%s
var out = {};
function pressedOf() { return chips.map(function (c) { return c.getAttribute("aria-pressed"); }); }
chips[0].click();
out.afterOff = [pressedOf(), groups.map(function (g) { return g.classList.contains("is-off"); })];
chips[1].click();
out.lastStays = [pressedOf(), groups.map(function (g) { return g.classList.contains("is-off"); })];
chips[0].click();
out.backOn = [pressedOf(), groups.map(function (g) { return g.classList.contains("is-off"); })];
out.startViews = views.map(function (v) { return v.hidden; });
btns[1].click();
out.afterPick = [views.map(function (v) { return v.hidden; }), btns.map(function (b) { return b.getAttribute("aria-pressed"); })];
out.switchOn = sw.classList.contains("on");
console.log(JSON.stringify(out));
"""


class ScriptTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_chips_toggle_a_series_the_last_one_stays_on_and_the_switcher_shows_one_view(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        start = template.index("  var tipBox = null;")
        end = template.index('  $all("article.ad-card").forEach(enhanceCard);')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chips.js"
            path.write_text(HARNESS % template[start:end])
            done = subprocess.run(["node", str(path)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["afterOff"], [["false", "true"], [True, False]])
        self.assertEqual(out["lastStays"], [["false", "true"], [True, False]])
        self.assertEqual(out["backOn"], [["true", "true"], [False, False]])
        self.assertEqual(out["startViews"], [False, True])
        self.assertEqual(out["afterPick"], [[True, False], ["false", "true"]])
        self.assertTrue(out["switchOn"])


if __name__ == "__main__":
    unittest.main()
