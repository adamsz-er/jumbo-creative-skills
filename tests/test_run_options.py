import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
for skill in ("creative-report", "creative-grader", "creative-mix", "keep-or-kill", "creative-context", "creative-brief"):
    sys.path.insert(0, str(ROOT / "skills" / skill / "scripts"))

import creative_metrics as cm  # noqa: E402
import detect_naming  # noqa: E402
import evidence  # noqa: E402
import grade  # noqa: E402
import mix  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
import verdicts  # noqa: E402

KEYED = "TYPE:{t} | PX:{c} | Calm | {who} | FMT:{f} | {m} | 2026/03/01"


def rows_for(ads, days=10):
    """Daily rows for synthetic ads: (id, name, spend per day, impressions per day, purchases per day)."""
    rows = []
    for ad_id, name, spend, impressions, conv in ads:
        for d in range(1, days + 1):
            rows.append({"Ad ID": ad_id, "Ad name": name, "Day": "2026-03-%02d" % d, "Amount spent (USD)": spend,
                         "Impressions": impressions, "Link clicks": impressions // 50, "Purchases": conv,
                         "Purchases conversion value": conv * 80})
    return rows


ADS = [("u%d" % i, KEYED.format(t="BAU", c="Trail", who="Ana", f="Video", m="US"), 50 + i, 5000, 2) for i in range(6)] + \
      [("c%d" % i, KEYED.format(t="Atelier", c="Camp", who="Bo", f="Image", m="CA"), 40 + i, 4000, 1) for i in range(6)]


def write_csv(path, rows):
    import csv
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quiet(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, out.getvalue(), err.getvalue()


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.csv = self.dir / "ads.csv"
        write_csv(self.csv, rows_for(ADS))
        cm.set_type_map(None)

    def tearDown(self):
        cm.set_type_map(None)
        self.tmp.cleanup()


class NamingOptionsTest(TmpCase):
    def test_a_position_in_the_key_map_names_an_unkeyed_segment(self):
        fields = cm.parse_name(ADS[0][1], key_map={"PX": "concept", "3": "tone", "4": "creator"})
        self.assertEqual((fields["tone"], fields["creator"], fields["concept"]), ("calm", "Ana", "Trail"))

    def test_without_it_the_segment_stays_unlabelled(self):
        self.assertEqual(cm.parse_name(ADS[0][1])["segment_4"], "Ana")

    def test_type_map_turns_an_account_word_into_a_known_type(self):
        self.assertEqual(cm.normalise_ad_type("Atelier"), "atelier")
        cm.set_type_map(cm.parse_type_map("atelier=bau"))
        self.assertEqual(cm.normalise_ad_type("Atelier"), "bau")
        ad = next(a for a in cm.aggregate_by_ad(cm.load_rows(str(self.csv))) if a["ad_id"] == "c0")
        self.assertEqual(ad["ad_type"], "bau")

    def test_type_map_refuses_an_unknown_type(self):
        with self.assertRaises(ValueError):
            cm.parse_type_map("atelier=couture")

    def test_detection_takes_the_confirmed_answers_from_the_profile(self):
        profile = self.dir / "profile.md"
        profile.write_text("# Creative profile: Acme\n\n## Script settings\n- key-map: PX=concept,4=creator\n"
                           "- type-map: atelier=bau\n- target: unknown\n\n## Constraints\n- key-map: ignored\n")
        code, out, _ = quiet(detect_naming.main, [str(self.csv), "--json", "--profile", str(profile)])
        self.assertEqual(code, 0)
        found = json.loads(out)
        self.assertEqual(found["unknown_ad_types"], {})
        self.assertEqual([u["position"] for u in found["unlabelled"]], [3])

    def test_without_the_profile_detection_still_asks(self):
        code, out, _ = quiet(detect_naming.main, [str(self.csv), "--json"])
        found = json.loads(out)
        self.assertEqual(found["unknown_ad_types"], {"atelier": 1})
        self.assertEqual([u["position"] for u in found["unlabelled"]], [3, 4])


class SettingsTest(TmpCase):
    def test_only_the_script_settings_block_is_read_and_unknown_is_skipped(self):
        profile = self.dir / "p.md"
        profile.write_text("## Data\n- currency: EUR\n\n## Script settings\n- currency: `USD`\ntarget: cpa=40\n"
                           "- where: unknown\n\n## Next\n- target: cpa=1\n")
        self.assertEqual(cm.read_settings(profile), {"currency": "USD", "target": "cpa=40"})

    def test_the_blank_template_block_and_its_comment_yield_nothing(self):
        template = ROOT / "skills" / "creative-context" / "references" / "brand-profile-template.md"
        block = template.read_text().split("```")[1]
        profile = self.dir / "t.md"
        profile.write_text(block + "\n## Script settings\n<!--\n- target: cpa=1\n-->\n")
        self.assertEqual(cm.read_settings(profile), {})

    def test_a_flag_on_the_command_line_beats_the_profile(self):
        profile = self.dir / "p.md"
        profile.write_text("## Script settings\n- target: cpa=40\n- currency: USD\n")
        args = type("A", (), {"target": "cpa=10", "currency": None, "key_map": None})()
        taken = cm.apply_settings(args, profile)
        self.assertEqual((args.target, args.currency), ("cpa=10", "USD"))
        self.assertEqual(taken, ["currency: USD"])


class WhereTest(TmpCase):
    def test_where_keeps_one_market_from_the_names(self):
        rows = cm.filter_rows(cm.load_rows(str(self.csv)), cm.parse_where(["market=us"]))
        self.assertEqual({r["ad_id"][0] for r in rows}, {"u"})

    def test_where_on_ad_type_goes_through_the_type_map(self):
        cm.set_type_map({"atelier": "bau"})
        rows = cm.filter_rows(cm.load_rows(str(self.csv)), cm.parse_where(["ad_type=bau"]))
        self.assertEqual(len({r["ad_id"] for r in rows}), 12)

    def test_an_unknown_field_is_an_error_not_an_empty_result(self):
        with self.assertRaises(cm.GroupColumnError):
            cm.filter_rows(cm.load_rows(str(self.csv)), cm.parse_where(["region=US"]))

    def test_bad_where_text_is_refused(self):
        for bad in ("market", "=US", "market="):
            with self.assertRaises(ValueError):
                cm.parse_where([bad])

    def test_scripts_print_the_scope_they_kept(self):
        for fn, extra in ((grade.main, []), (mix.main, []), (verdicts.main, [])):
            code, out, err = quiet(fn, [str(self.csv), "--where", "market=CA"] + extra)
            self.assertEqual(code, 0, err)
            self.assertIn("scope: market CA (60 of 120 rows)", out)

    def test_brief_evidence_reads_keyed_names_and_scope(self):
        code, out, err = quiet(evidence.main, [str(self.csv), "--json", "--key-map", "PX=concept",
                                               "--where", "market=US"])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertTrue(result["available"])
        self.assertEqual(result["ads"], 6)
        self.assertEqual(result["run_notes"], ["scope: market US (60 of 120 rows)"])

    def test_bad_input_is_a_message_and_exit_2_never_a_traceback(self):
        for fn in (grade.main, mix.main, verdicts.main, evidence.main):
            code, _, err = quiet(fn, [str(self.csv), "--profile", str(self.dir / "missing.md")])
            self.assertEqual(code, 2, fn)
            self.assertIn("cannot read --profile", err)
        code, _, err = quiet(verdicts.main, [str(self.csv), "--target", "nonsense=3"])
        self.assertEqual(code, 2)
        self.assertIn("not a metric id", err)

    def test_verdicts_json_carries_scope_and_targets(self):
        code, out, _ = quiet(verdicts.main, [str(self.csv), "--json", "--where", "market=US", "--target", "cpa=20"])
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["settings"]["targets"], {"cpa": 20.0})
        self.assertTrue(all(a["ad"].startswith("u") for a in result["ads"]))


class ReportOptionsTest(TmpCase):
    def build(self, *flags):
        out = self.dir / "r.html"
        code, text, err = quiet(report.main, [str(self.csv), "-o", str(out)] + list(flags))
        self.assertEqual(code, 0, err)
        return out, out.read_text(encoding="utf-8"), text

    def test_title_beats_the_profile_and_scope_comes_from_where(self):
        profile = self.dir / "p.md"
        profile.write_text("# Creative profile: Brand From Profile\n")
        _, html, _ = self.build("--profile", str(profile), "--title", "Acme", "--where", "market=US")
        self.assertIn("<title>Acme, market US creative review</title>", html)
        self.assertIn("<span>Scope</span> market US", html)
        self.assertIn("Scope: market US only", html)

    def test_profile_brand_is_used_when_there_is_no_title(self):
        profile = self.dir / "p.md"
        profile.write_text("# Creative profile: Brand From Profile\n")
        _, html, _ = self.build("--profile", str(profile))
        self.assertIn("<title>Brand From Profile creative review</title>", html)
        self.assertIn("<span>Scope</span> all ads in the data", html)

    def test_key_map_reaches_the_report_facets(self):
        _, html, _ = self.build("--key-map", "PX=concept,4=creator")
        self.assertIn('data-facet="creator"', html)

    def test_metrics_no_ad_can_show_are_named_once_up_front(self):
        _, html, _ = self.build()
        self.assertIn("Not in this pull", html)
        self.assertIn("<b>Hook rate</b>: missing 3-second plays", html)
        self.assertIn("<b>Hold rate</b>: missing ThruPlays", html)
        self.assertIn("3-second video plays column", html)

    def test_a_refused_derivation_is_named_as_the_reason(self):
        rows = cm.load_rows([{"ad_id": "1", "ad_name": "a", "date": "2026-03-0%d" % d, "spend": 10,
                              "impressions": 1000, "cost_per_video_view": "0.02", "video_thruplay": 5} for d in (1, 2)])
        banner = panels.missing_everywhere(panels.Ctx(rows=rows))
        self.assertIn("<b>Hook rate and Hold rate</b>: not derived: cost per 3-second view is rounded", banner)

    def test_check_passes_a_built_page_and_names_what_breaks(self):
        out, html, _ = self.build()
        code, text, _ = quiet(report.main, ["--check", str(out)])
        self.assertEqual(code, 0, text)
        self.assertIn("not a visual check", text)
        broken = html.replace('id="panel-pareto"', 'id="panel-gone"').replace(
            "</body>", '<img src="https://tracker.example/x.gif"></body>')
        problems = report.check_html(broken)
        self.assertTrue(any("panel pareto" in p for p in problems), problems)
        self.assertTrue(any("tracker.example" in p for p in problems), problems)


class PriorTotalsTest(unittest.TestCase):
    def test_undated_ad_totals_are_enough_for_the_change_on_every_tile(self):
        rows = cm.load_rows(str(ROOT / "examples" / "acme" / "ads_daily.csv"))
        prior = [{"ad_id": a["ad_id"], "ad_name": a["ad_name"], "date_stop": "2026-02-28", "spend": a["spend"] / 2,
                  "impressions": a["impressions"], "conversions": a.get("conversions")} for a in cm.aggregate_by_ad(rows)]
        html, _ = panels.kpi_strip(panels.Ctx(rows=rows, prior=cm.load_rows(prior), currency="USD"))
        self.assertIn("+100.0% vs prior period", html)
        self.assertNotIn("no prior period", html)


class GroupSizeCardTest(unittest.TestCase):
    def test_a_judged_card_says_how_many_ads_it_was_compared_with(self):
        entry = {"ad": "1", "ad_name": "a", "verdict_id": "keep", "verdict": "Keep", "confidence": "Early read",
                 "sentence": "Keep it running.", "group_size": 6, "thin": True, "spend_at_stake": 5}
        html = panels.ad_card(panels.Ctx(verdicts={"ads": [entry]}), entry)
        self.assertIn("vs 6 similar ads: small group", html)


if __name__ == "__main__":
    unittest.main()
