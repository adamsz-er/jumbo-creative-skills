import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "creative-review" / "scripts"))

import creative_metrics as cm  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
from review_support import FIXTURE, Scratch, run  # noqa: E402

DERIVED = "derived: spend / cost per 3-second view"


def video_row(ad_id, impressions, plays=None, thru=None, source=None, fmt="video", day="2026-03-01"):
    row = {"ad_id": ad_id, "ad_name": "ad %s | FMT:%s" % (ad_id, fmt), "date": day, "spend": 100.0, "impressions": float(impressions),
           "conversion_value": 300.0, "conversions": 5.0, "link_clicks": 50.0}
    if plays is not None:
        row["video_views_3s"] = float(plays)
        row["video_views_3s_source"] = source or "reported"
    if thru is not None:
        row["video_thruplay"] = float(thru)
    return row


def mixed_rows():
    """Two video ads (one reported, one derived plays), one video ad with ThruPlays but no plays, one static ad."""
    return [video_row("a", 1000, plays=400, thru=100),
            video_row("b", 2000, plays=600, thru=200, source=DERIVED),
            video_row("c", 5000, thru=3000),
            video_row("d", 2000, fmt="static")]


def tracked(text):
    return [(int(n), int(m)) for n, m in re.findall(r"(\d+) of (\d+) video ads", text)]


class FunnelBasisTest(unittest.TestCase):
    def test_a_video_share_is_read_on_the_rows_that_carry_the_step(self):
        ctx = panels.Ctx(rows=mixed_rows())
        html, _ = panels.funnel(ctx)
        thru = next(r for r in html.split("<tr>") if r.startswith("<td>ThruPlays"))
        share = float(re.search(r"([\d.]+)% of video impressions", thru).group(1))
        self.assertLessEqual(share, 100.0)
        self.assertAlmostEqual(share, (100 + 200 + 3000) / (1000 + 2000 + 5000) * 100, places=2)
        self.assertIn("on 3 video ads", thru)

    def test_a_share_over_a_hundred_percent_reads_inconsistent_counts(self):
        rows = [video_row("a", 1000, plays=400, thru=9000)]
        html, _ = panels.funnel(panels.Ctx(rows=rows))
        thru = next(r for r in html.split("<tr>") if r.startswith("<td>ThruPlays"))
        self.assertIn("inconsistent counts", thru)
        self.assertNotRegex(thru, r"\d{3,}\.\d\d% of video impressions")

    def test_the_hold_step_rate_still_reads_on_ads_with_both_counts(self):
        html, _ = panels.funnel(panels.Ctx(rows=mixed_rows()))
        thru = next(r for r in html.split("<tr>") if r.startswith("<td>ThruPlays"))
        self.assertIn("30.00% of 3-second plays", thru)


class CoverageBasisTest(unittest.TestCase):
    def setUp(self):
        self.rows = mixed_rows() + [video_row("e", 3000, plays=900, thru=300, day="2026-03-02"), video_row("f", 3000, plays=300, thru=60, source=DERIVED, day="2026-03-02")]
        self.ctx = panels.Ctx(rows=self.rows, mix={"by_format": [
            {"format": "video", "ads": 5, "share": 90.0, "roas": 3.0, "cpa": 20.0}, {"format": "static", "ads": 1, "share": 10.0, "roas": 3.0, "cpa": 20.0}]})

    def test_one_helper_states_the_basis_with_derived_named(self):
        self.assertEqual(panels.video_basis(self.ctx, "hook_rate"), "(derived, 4 of 6 video ads)")
        self.assertEqual(panels.video_basis(panels.Ctx(rows=[video_row("a", 1000, plays=300, thru=90)]), "hook_rate"), "(1 of 1 video ads)")

    def test_tiles_funnel_scorecard_and_scatter_state_the_same_basis(self):
        expected = panels.video_basis(self.ctx, "hook_rate")
        outputs = {"tiles": panels.kpi_strip(self.ctx)[0], "funnel": panels.funnel(self.ctx)[0],
                   "scorecard": panels.format_scorecard(self.ctx)[0], "scatter": panels.video_hook_hold(self.ctx)[0]}
        for name, html in outputs.items():
            self.assertIn(expected, html, name)
            self.assertEqual({n for n, _ in tracked(html)}, {4}, name)

    def test_the_scatter_says_how_many_of_those_ads_also_have_hold(self):
        html, _ = panels.video_hook_hold(self.ctx)
        self.assertRegex(html, r"\d+ of these also have a hold rate")


class QuietNaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.page = report.build_html(rows=cls.rows, currency="USD")

    def test_table_cells_read_n_a_with_the_reason_in_a_tooltip(self):
        self.assertEqual(len(re.findall(r"<td[^>]*>n/a \(", self.page)), 0)
        self.assertRegex(self.page, r'<span class="na" title="missing checkouts">n/a</span>')

    def test_each_panel_lists_its_distinct_reasons_once_with_counts(self):
        funnel = self.page.split('id="panel-funnel"')[1].split("</section>")[0]
        notes = re.findall(r'<p class="muted na-notes">(.*?)</p>', funnel)
        self.assertEqual(len(notes), 1)
        self.assertRegex(notes[0], r"missing checkouts \(1 cell\)")
        self.assertEqual(notes[0].count("missing checkouts"), 1)

    def test_a_reason_with_markup_is_escaped_in_the_tooltip_and_the_note(self):
        ctx = panels.Ctx(rows=self.rows)
        cell = panels.na_cell(ctx, 'n/a (a<b & "c">)')
        self.assertIn('title="a&lt;b &amp; &quot;c&quot;&gt;"', cell)
        self.assertNotIn("<b", cell)
        self.assertIn("a&lt;b &amp; &quot;c&quot;&gt;", panels.na_footnote(ctx))

    def test_a_cell_that_is_not_n_a_is_escaped_and_not_collected(self):
        ctx = panels.Ctx(rows=self.rows)
        self.assertEqual(panels.na_cell(ctx, "<5%"), "&lt;5%")
        self.assertEqual(panels.na_footnote(ctx), "")

    def test_data_and_method_and_the_tiles_keep_their_readable_reasons(self):
        footer = self.page.split("<footer>")[1].split("</footer>")[0]
        self.assertNotIn('class="na"', footer)
        bare = [{k: v for k, v in r.items() if k not in ("conversions", "conversion_value")} for r in self.rows]
        tiles = panels.kpi_strip(panels.Ctx(rows=bare, currency="USD"))[0]
        self.assertRegex(tiles, r'kpi-value">n/a</p><p class="kpi-note">[^<]*missing')
        self.assertNotIn('class="na"', tiles)

    def test_the_ad_detail_graded_metrics_are_quiet_too(self):
        pool = self.page.split('<template id="ad-pool">')[1].split("</template>")[0]
        self.assertEqual(len(re.findall(r"<td[^>]*>n/a \(", pool)), 0)
        self.assertIn('class="muted na-notes"', pool)


class CaptionTest(unittest.TestCase):
    def label(self, changes):
        ctx = panels.Ctx(rows=[video_row("a", 1000, plays=300, thru=90)])
        ctx.changes = changes
        return ctx.prior_label()

    def test_the_caption_names_the_run_day_and_the_data_end(self):
        self.assertEqual(self.label({"previous_at": "2026-10-08T09:30:00+11:00", "previous_window_to": "2026-10-07", "prior_is_previous_run": True}),
                         "last review (run 8 Oct, data to 7 Oct)")

    def test_an_old_record_without_a_window_keeps_the_old_caption(self):
        self.assertEqual(self.label({"previous_at": "2026-10-08T09:30:00+11:00", "prior_is_previous_run": True}), "last review (2026-10-08)")

    def test_a_prior_that_is_not_the_previous_run_stays_prior_period(self):
        self.assertEqual(self.label({"previous_at": "2026-10-08T09:30:00+11:00", "previous_window_to": "2026-10-07"}), "prior period")

    def test_compare_passes_the_previous_window_end_through(self):
        work = Scratch(self).path
        run(["run", FIXTURE], work)
        run(["run", FIXTURE], work)
        folders = sorted(p for account in (work / "creative-review-runs").iterdir() for p in account.iterdir())
        first = json.loads((folders[0] / "run.json").read_text())
        found = json.loads((folders[-1] / "changes.json").read_text())
        self.assertEqual(found["previous_window_to"], first["window_to"])
        tiles = (folders[-1] / "report.html").read_text().split('id="panel-kpis"')[1].split("</section>")[0]
        self.assertIn("data to ", tiles)


if __name__ == "__main__":
    unittest.main()
