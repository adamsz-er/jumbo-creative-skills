import contextlib
import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
for skill, _ in (("creative-context", 0), ("creative-grader", 0), ("keep-or-kill", 0), ("creative-mix", 0)):
    sys.path.insert(0, str(ROOT / "skills" / skill / "scripts"))

import creative_metrics as cm  # noqa: E402
import detect_naming  # noqa: E402
import grade  # noqa: E402
import mix  # noqa: E402
import verdicts  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
KEYED = "FMT:Carousel | CONCEPT:Dusk | MKT:US | TYPE:Offer"


def run(main, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def fixture_with_market(directory):
    """The Acme fixture with a Market column: alternating US and UK by ad."""
    with open(FIXTURE, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    ids = sorted({r["Ad ID"] for r in rows})
    for row in rows:
        row["Market"] = "US" if ids.index(row["Ad ID"]) % 2 == 0 else "UK"
    path = Path(directory) / "with_market.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


class KeyedParsingTest(unittest.TestCase):
    def test_keyed_pipe_name(self):
        parsed = cm.parse_name(KEYED)
        self.assertEqual(parsed, {"format": "carousel", "concept": "Dusk", "market": "US", "ad_type": "promo"})
        parsed = cm.parse_name("THEME:campfire | FMT:reel | TYPE:launch | 2026/07/21")
        self.assertEqual((parsed["concept"], parsed["format"], parsed["ad_type"], parsed["launch_date"]),
                         ("campfire", "reel", "launch", "2026-07-21"))

    def test_equals_sign_and_underscore_separator(self):
        parsed = cm.parse_name("TYPE=BAU_ANGLE=Durability_FMT=Static")
        self.assertEqual((parsed["ad_type"], parsed["concept"], parsed["format"]),
                         ("bau", "Durability", "static"))

    def test_dash_separator_wins_when_values_hold_underscores(self):
        parsed = cm.parse_name("TYPE:BAU - ANGLE:trail_gear - FMT:reel")
        self.assertEqual((parsed["concept"], parsed["format"]), ("trail_gear", "reel"))

    def test_keys_are_case_insensitive(self):
        self.assertEqual(cm.parse_name("type:aon | fmt:Static")["ad_type"], "bau")

    def test_custom_key_map(self):
        parsed = cm.parse_name("PX:Dusk | FMT:Reel", key_map={"px": "concept"})
        self.assertEqual((parsed["concept"], parsed["format"]), ("Dusk", "reel"))

    def test_key_map_text(self):
        self.assertEqual(cm.parse_key_map("PX=concept, KND=ad_type"),
                         {"PX": "concept", "KND": "ad_type"})
        with self.assertRaises(ValueError):
            cm.parse_key_map("PX")

    def test_unkeyed_segments_are_read_by_shape(self):
        parsed = cm.parse_name("Carousel | CA | 21/07/2026 | spring-hero")
        self.assertEqual((parsed["format"], parsed["market"], parsed["launch_date"]),
                         ("carousel", "CA", "2026-07-21"))
        self.assertEqual(parsed["segment_4"], "spring-hero")

    def test_unknown_key_is_kept_under_its_lowercase_name(self):
        self.assertEqual(cm.parse_name("TYPE:BAU | ZZZ:one")["zzz"], "one")

    def test_a_repeat_of_a_field_is_not_overwritten(self):
        parsed = cm.parse_name("FMT:Video | FMT:Static")
        self.assertEqual(parsed["format"], "video")
        self.assertEqual(parsed["segment_2"], "Static")

    def test_legacy_positional_still_parses_and_new_fields_are_known(self):
        parsed = cm.parse_name("a_static_house_promo_tent-2p_polished_2026-03-01")
        self.assertEqual((parsed["ad_type"], parsed["product"]), ("promo", "tent-2p"))
        for field in ("market", "funnel_stage", "collection", "range", "launch_date"):
            self.assertIn(field, cm.NAME_FIELDS)

    def test_unreadable_names_stay_empty(self):
        for name in (None, "", "plain name", "a | b | c", "x | y"):
            self.assertEqual(cm.parse_name(name), {}, name)


class ReviewFixesTest(unittest.TestCase):
    def test_keys_in_no_list_are_read_by_their_values(self):
        names = ["KND:sale | THM:outdoor-%d | MED:video | CTY:US" % i for i in range(6)]
        found = cm.detect_convention(names)
        self.assertEqual(found["inferred_keys"]["KND"]["field"], "ad_type")
        self.assertEqual(found["inferred_keys"]["MED"]["field"], "format")
        self.assertEqual(found["inferred_keys"]["CTY"]["field"], "market")
        self.assertEqual(found["inferred_keys"]["MED"]["share"], 100.0)
        self.assertEqual(found["match_rate"], 100.0)
        self.assertIn("Key MED was read as format because 100% of its values are format words", found["description"])
        self.assertEqual(found["inferred_keys"]["THM"]["field"], "concept")
        learned = cm.learn_names(names)
        parsed = cm.parse_name(names[0], learned=learned)
        self.assertEqual((parsed["ad_type"], parsed["format"], parsed["market"]), ("promo", "video", "US"))
        self.assertEqual(parsed["concept"], "outdoor-0")

    def test_the_only_free_text_key_is_read_as_the_concept(self):
        names = ["KND:sale | THM:outdoor-%d | MED:video" % i for i in range(6)]
        found = cm.detect_convention(names)
        self.assertEqual(found["inferred_keys"]["THM"]["field"], "concept")
        self.assertIsNone(found["inferred_keys"]["THM"]["share"])
        self.assertEqual(found["concept_candidates"], [])
        self.assertIn("Key THM was read as concept: the only free-text key (key in 100% of names).", found["description"])
        self.assertEqual(cm.parse_name(names[0], learned=cm.learn_names(names))["concept"], "outdoor-0")
        result = mix.analyse_mix(cm.load_rows([{"Ad name": n, "Amount spent": 1, "Impressions": 9,
                                                "Day": "2026-03-01"} for n in names]))
        self.assertEqual(len(result["by_concept"]), 6)

    def test_two_free_text_keys_leave_the_concept_to_one_question(self):
        names = ["KND:sale | THM:outdoor-%d | HRO:hero-%d | MED:video" % (i, i) for i in range(6)]
        found = cm.detect_convention(names)
        self.assertEqual(found["concept_candidates"], ["HRO", "THM"])
        self.assertNotIn("concept", {v["field"] for v in found["inferred_keys"].values()})
        self.assertIn("could be it, so ask the user which", found["description"])
        self.assertNotIn("concept", cm.parse_name(names[0], learned=cm.learn_names(names)))
        code, out, _ = run(detect_naming.main, [self._write(names)])
        self.assertIn("Ask the user ONE question", out)

    def test_a_key_with_one_value_is_not_the_concept(self):
        names = ["KND:sale | THM:same | MED:video"] * 4
        self.assertIsNone(cm.detect_convention(names)["inferred_keys"].get("THM"))

    def test_an_existing_concept_key_blocks_the_guess(self):
        names = ["TYPE:sale | ANGLE:a-%d | THM:b-%d" % (i, i) for i in range(4)]
        found = cm.detect_convention(names)
        self.assertNotIn("THM", found["inferred_keys"])
        self.assertEqual(found["concept_candidates"], [])

    def _write(self, names):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "names.txt"
        path.write_text("\n".join(names) + "\n", encoding="utf-8")
        return str(path)

    def test_every_built_in_key_can_be_matched(self):
        for key in cm.KEY_MAP:
            read = cm._read_name("%s:x | ZZ:y" % key.lower())
            self.assertEqual(read["keys"][0], (key, cm.KEY_MAP[key], True), key)

    def test_a_numeric_key_is_not_the_concept(self):
        names = ["KND:sale | VER:%d | MED:video" % i for i in range(1, 7)]
        found = cm.detect_convention(names)
        self.assertNotIn("VER", found["inferred_keys"])
        self.assertEqual(found["concept_candidates"], [])

    def test_keyed_market_codes_match_in_any_case(self):
        names = ["KND:sale | CTY:%s | MED:video" % c for c in ("us", "uk", "us", "uk")]
        found = cm.detect_convention(names)
        self.assertEqual(found["inferred_keys"]["CTY"]["field"], "market")
        learned = cm.learn_names(names)
        self.assertEqual(cm.parse_name(names[0], learned=learned)["market"], "US")

    def test_date_issue_counts_are_not_truncated(self):
        names = ["static | %02d/03/2026" % d for d in range(1, 13)]
        names += ["video | 0%d/0%d/2026" % (a, b) for a in range(1, 4) for b in range(4, 9) if a != b]
        issues = cm.detect_convention(names)["date_issues"]
        self.assertGreater(issues["ambiguous_count"], cm.UNPARSED_SHOWN)
        self.assertEqual(len(issues["ambiguous"]), cm.UNPARSED_SHOWN)
        found = cm.detect_convention(names)
        self.assertIn("%d ambiguous" % issues["ambiguous_count"], found["description"])

    def test_a_key_in_few_names_is_not_inferred(self):
        names = ["KND:sale | MED:video | N:%d" % i for i in range(8)] + ["KND:sale | THM:odd-%d | MED:video" % i for i in range(2)]
        found = cm.detect_convention(names)
        self.assertNotIn("THM", found["inferred_keys"])
        self.assertEqual(found["concept_candidates"], [])
        self.assertEqual(found["inferred_keys"]["MED"]["coverage"], 100.0)

    def test_coverage_counts_names_as_given_duplicates_included(self):
        names = ["KND:sale | MED:video", "KND:sale | MED:video", "KND:sale | THM:a | MED:video"] + \
                ["KND:sale | MED:video"] * 3
        found = cm.detect_convention(names)
        self.assertNotIn("THM", found["inferred_keys"])
        self.assertEqual(found["inferred_keys"]["MED"]["coverage"], 100.0)
        names = ["KND:sale | MED:video"] * 5 + ["stray name"]
        found = cm.detect_convention(names)
        self.assertEqual(found["inferred_keys"]["MED"]["field"], "format")
        self.assertAlmostEqual(found["inferred_keys"]["MED"]["coverage"], 5 / 6 * 100)
        self.assertAlmostEqual(found["match_rate"], 5 / 6 * 100)

    def test_a_creator_like_key_is_never_assigned_the_concept(self):
        for who in (("jane", "sam", "influencer", "collab"), ("ugc", "ugc", "jane", "ugc")):
            names = ["KND:sale | WHO:%s | MED:video" % who[i % len(who)] for i in range(6)]
            found = cm.detect_convention(names)
            self.assertNotIn("concept", {v["field"] for v in found["inferred_keys"].values()}, who)
            learned = cm.learn_names(names)
            self.assertNotIn("concept", cm.parse_name(names[0], learned=learned), who)

    def test_a_key_that_overlaps_format_or_type_words_goes_to_the_question(self):
        names = ["KND:sale | WHO:%s | MED:video" % w for w in ("jane", "sam", "influencer", "collab")] * 2
        found = cm.detect_convention(names)
        self.assertEqual(found["concept_candidates"], ["WHO"])
        self.assertIn("could be it, so ask the user which", found["description"])

    def test_a_who_key_of_plain_names_goes_to_the_question(self):
        names = ["KND:sale | WHO:%s | MED:video" % w for w in ("jane", "sam")] * 3
        found = cm.detect_convention(names)
        self.assertEqual(found["concept_candidates"], ["WHO"])
        self.assertNotIn("WHO", found["inferred_keys"])

    def test_versioned_numbers_are_not_a_concept(self):
        for values in ("v%d", "%d", "V%d"):
            names = ["KND:sale | VER:%s | MED:video" % (values % i) for i in range(1, 7)]
            found = cm.detect_convention(names)
            self.assertNotIn("VER", found["inferred_keys"], values)
            self.assertEqual(found["concept_candidates"], [], values)

    def test_bare_market_codes_match_in_any_case(self):
        names = ["video | hero-%d | us" % i for i in range(4)]
        learned = cm.learn_names(names)
        self.assertEqual(cm.parse_name(names[0], learned=learned)["market"], "US")
        self.assertEqual(cm.detect_convention(names)["fields"]["market"]["count"], 4)

    def test_a_lower_case_word_is_not_a_market_without_a_learned_position(self):
        self.assertNotIn("market", cm.parse_name("video | no | hero"))
        self.assertNotIn("market", cm.parse_name("video | hero | it"))

    def test_a_person_key_is_not_an_ad_type(self):
        names = ["WHO:%s | MED:video" % w for w in ("jane", "sam", "creator", "jane", "new", "sam")]
        found = cm.detect_convention(names)
        self.assertNotEqual(found["inferred_keys"].get("WHO", {}).get("field"), "ad_type")

    def test_key_map_overrides_an_inferred_key(self):
        names = ["KND:sale | MED:video"] * 3
        learned = cm.learn_names(names, {"MED": "concept"})
        self.assertNotIn("MED", learned["key_map"])
        self.assertEqual(cm.parse_name(names[0], key_map={"MED": "concept"}, learned=learned)["concept"], "video")

    def test_a_name_with_only_market_or_date_is_not_read(self):
        self.assertEqual(cm.parse_name("US | hero"), {})
        self.assertEqual(cm.parse_name("US | 2026-03-01"), {})
        names = ["US | hero", "Video | hero"]
        self.assertEqual(cm.detect_convention(names)["matched"], 1)
        result = mix.analyse_mix(cm.load_rows([{"Ad name": n, "Amount spent": 1, "Impressions": 9,
                                                "Day": "2026-03-01"} for n in names]))
        self.assertEqual((result["classified"], result["unclassified"]["count"]), (1, 1))

    def test_a_prefix_with_a_colon_does_not_make_a_name_keyed(self):
        name = "promo: 2 for 1 | static | house | promo | tent | polished | 2026-03-01"
        parsed = cm.parse_name(name)
        self.assertEqual((parsed["concept"], parsed["format"], parsed["ad_type"]),
                         ("promo: 2 for 1", "static", "promo"))

    def test_dates_must_parse_and_ambiguous_ones_are_listed(self):
        self.assertEqual(cm.parse_name("static | 25-03-2026 | hero")["launch_date"], "2026-03-25")
        self.assertEqual(cm.parse_name("static | 2026-03-05")["launch_date"], "2026-03-05")
        parsed = cm.parse_name("static | 05/06/2026")
        self.assertNotIn("launch_date", parsed)
        self.assertEqual(parsed["segment_2"], "05/06/2026")
        parsed = cm.parse_name("static | 31/02/2026")
        self.assertNotIn("launch_date", parsed)
        found = cm.detect_convention(["static | 05/06/2026", "video | 2026-03-05"])
        self.assertEqual(found["date_issues"]["ambiguous"], ["05/06/2026"])
        self.assertIn("Dates left unlabelled", found["description"])
        found = cm.detect_convention(["static | 40/13/2026", "video | 2026-03-05"])
        self.assertEqual(found["date_issues"]["unparseable"], ["40/13/2026"])

    def test_another_name_settles_day_month_order(self):
        names = ["static | 05/06/2026", "video | 25/06/2026"]
        learned = cm.learn_names(names)
        self.assertEqual(learned["date_order"], "dmy")
        self.assertEqual(cm.parse_name(names[0], learned=learned)["launch_date"], "2026-06-05")
        self.assertEqual(cm.detect_convention(names)["date_issues"]["ambiguous"], [])

    def test_a_bare_market_code_must_sit_where_most_names_carry_one(self):
        names = ["video | hero-%d | DE" % i for i in range(5)] + ["video | IT | hero"]
        learned = cm.learn_names(names)
        self.assertEqual(learned["market_positions"], {3})
        self.assertEqual(cm.parse_name(names[0], learned=learned)["market"], "DE")
        self.assertNotIn("market", cm.parse_name(names[-1], learned=learned))


class AdTypeSynonymTest(unittest.TestCase):
    def test_synonyms_map_to_the_six_types(self):
        expected = {
            "promo": ("sale", "promo", "offer", "discount", "bfcm"),
            "bau": ("bau", "evergreen", "always-on", "aon"),
            "launch": ("launch", "drop", "newin"),
            "hype": ("hype", "teaser", "tease"),
            "partnership": ("collab", "partnership", "influencer", "whitelist", "spark"),
            "retention": ("retention", "rtg", "existing", "loyalty"),
        }
        for canonical, words in expected.items():
            for word in words:
                self.assertEqual(cm.normalise_ad_type(word.upper()), canonical, word)

    def test_unknown_type_is_kept_as_is(self):
        self.assertEqual(cm.normalise_ad_type("Clearout"), "clearout")
        self.assertEqual(cm.parse_name("TYPE:Clearout | FMT:static")["ad_type"], "clearout")

    def test_a_carried_ad_type_column_is_normalised(self):
        ads = cm.aggregate_by_ad(cm.load_rows([{"Ad name": "x", "Ad type": "Sale", "ad_type": "Sale",
                                                "Amount spent": 5, "Impressions": 100}]))
        self.assertEqual(ads[0]["ad_type"], "promo")


class DetectConventionTest(unittest.TestCase):
    def test_acme_names_match_fully_with_one_convention(self):
        names = sorted({r["ad_name"] for r in cm.load_rows(FIXTURE)})
        found = cm.detect_convention(names)
        self.assertEqual(found["match_rate"], 100.0)
        self.assertEqual(len(found["conventions"]), 1)
        self.assertEqual(found["separator"], " | ")
        self.assertFalse(found["ask"])
        self.assertEqual(found["unparsed"], [])
        self.assertEqual(found["fields"]["concept"]["coverage"], 100.0)

    def test_keyed_names_report_their_keys(self):
        names = ["FMT:Video | ANGLE:Outdoor-%d | MKT:UK | TYPE:SALE" % i for i in range(6)]
        found = cm.detect_convention(names)
        self.assertEqual(found["keys"]["TYPE"], {"field": "ad_type", "count": 6})
        self.assertEqual(found["fields"]["market"]["coverage"], 100.0)
        self.assertEqual(found["conventions"][0]["style"], "keyed")
        self.assertIn("100%", found["description"])

    def test_two_conventions_are_both_reported_with_counts(self):
        keyed = ["TYPE:BAU | ANGLE:Hero-%d | FMT:Static" % i for i in range(6)]
        positional = ["c%d_static_house_bau_tent_polished_2026-03-01" % i for i in range(3)]
        found = cm.detect_convention(keyed + positional)
        counts = sorted(c["count"] for c in found["conventions"])
        self.assertEqual(counts, [3, 6])
        self.assertTrue(found["coexisting"])
        self.assertTrue(found["ask"])
        self.assertTrue(any("two" in reason or "coexist" in reason for reason in found["ask_reasons"]))

    def test_a_stray_second_style_is_listed_not_asked_about(self):
        keyed = ["TYPE:BAU | ANGLE:Hero-%d | FMT:Static" % i for i in range(39)]
        found = cm.detect_convention(keyed + ["c_static_house_bau_tent_polished_2026-03-01"])
        self.assertEqual(len(found["conventions"]), 2)
        self.assertLess(found["conventions"][1]["share"], cm.COEXIST_SHARE)
        self.assertFalse(found["ask"])
        self.assertEqual(found["ask_reasons"], [])

    def test_a_second_style_at_the_share_line_is_asked_about(self):
        keyed = ["TYPE:BAU | ANGLE:Hero-%d | FMT:Static" % i for i in range(19)]
        found = cm.detect_convention(keyed + ["c_static_house_bau_tent_polished_2026-03-01"])
        self.assertEqual(found["conventions"][1]["share"], 5.0)
        self.assertTrue(found["ask"])

    def test_low_match_rate_goes_down_the_ask_path(self):
        names = ["TYPE:BAU | FMT:Static", "TYPE:SALE | FMT:Video"] + ["Spring hero v%d" % i for i in range(7)]
        found = cm.detect_convention(names)
        self.assertLess(found["match_rate"], 85.0)
        self.assertTrue(found["ask"])
        self.assertEqual(found["unparsed_count"], 7)
        self.assertEqual(len(found["unparsed"]), 7)

    def test_threshold_is_settable(self):
        names = ["TYPE:BAU | FMT:Static", "plain one", "TYPE:SALE | FMT:Video"]
        self.assertTrue(cm.detect_convention(names)["ask"])
        self.assertFalse(cm.detect_convention(names, min_match_rate=60.0)["ask"])

    def test_unparsed_examples_are_capped(self):
        found = cm.detect_convention(["nothing %d" % i for i in range(20)])
        self.assertEqual(found["unparsed_count"], 20)
        self.assertEqual(len(found["unparsed"]), cm.UNPARSED_SHOWN)

    def test_unknown_ad_types_and_keys_are_listed(self):
        names = ["TYPE:Clearout | ZZZ:one | FMT:Static", "TYPE:BAU | FMT:Video", "TYPE:Clearout | FMT:Static"]
        found = cm.detect_convention(names)
        self.assertEqual(found["unknown_ad_types"], {"clearout": 2})
        self.assertEqual(found["unknown_keys"], {"ZZZ": 1})

    def test_unlabelled_positions_are_listed(self):
        names = ["Video | hero-%d | DE" % i for i in range(5)]
        found = cm.detect_convention(names)
        self.assertEqual(found["unlabelled"][0]["position"], 2)
        self.assertEqual(found["unlabelled"][0]["count"], 5)

    def test_no_names_is_not_a_match(self):
        found = cm.detect_convention([])
        self.assertIsNone(found["match_rate"])
        self.assertTrue(found["ask"])


class GroupingPassThroughTest(unittest.TestCase):
    def test_extra_columns_are_carried_with_the_most_common_value(self):
        rows = cm.load_rows([
            {"Ad name": "x", "Market": "US", "Campaign name": "c1", "Amount spent": 1, "Impressions": 5},
            {"Ad name": "x", "Market": "US", "Campaign name": "c1", "Amount spent": 1, "Impressions": 5},
            {"Ad name": "x", "Market": "UK", "Campaign name": "c1", "Amount spent": 1, "Impressions": 5},
        ])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertEqual((ad["market"], ad["campaign_name"]), ("US", "c1"))

    def test_numeric_columns_and_metric_columns_are_not_carried(self):
        rows = cm.load_rows([{"Ad name": "x", "Video plays at 25%": 5, "Amount spent": 1, "Impressions": 5}])
        ad = cm.aggregate_by_ad(rows)[0]
        self.assertNotIn("video_plays_at_25", ad)
        self.assertNotIn("Video plays at 25%", ad)

    def test_adset_name_heading_maps_to_adset_name(self):
        rows = cm.load_rows([{"Ad name": "x", "Ad set name": "s1", "Amount spent": 1, "Impressions": 5}])
        self.assertEqual(cm.aggregate_by_ad(rows)[0]["adset_name"], "s1")

    def test_missing_group_column_names_what_is_available(self):
        ads = cm.aggregate_by_ad(cm.load_rows(FIXTURE))
        with self.assertRaises(cm.GroupColumnError) as caught:
            cm.resolve_group_by(ads, ("nope",))
        self.assertIn("column nope not in the data; available:", str(caught.exception))
        self.assertIn("format", str(caught.exception))

    def test_name_fields_and_carried_columns_resolve(self):
        rows = cm.load_rows([{"Ad name": "x", "Market": "US", "Amount spent": 1, "Impressions": 5}])
        ads = cm.aggregate_by_ad(rows)
        self.assertEqual(cm.resolve_group_by(ads, ("Market", "format")), ("market", "format"))


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = fixture_with_market(self.tmp.name)

    def test_grade_groups_by_market(self):
        code, out, _ = run(grade.main, [str(self.path), "--group-by", "market"])
        self.assertEqual(code, 0)
        self.assertIn("Grouped by: market", out)
        self.assertIn("US (sales) n=", out)
        self.assertIn("UK (sales) n=", out)

    def test_grade_groups_by_several_columns(self):
        code, out, _ = run(grade.main, [str(self.path), "--group-by", "format,ad_type,market"])
        self.assertEqual(code, 0)
        self.assertIn("Grouped by: format, ad_type, market", out)

    def test_grade_missing_column_exits_2(self):
        code, out, err = run(grade.main, [str(self.path), "--group-by", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("column nope not in the data; available:", err)
        self.assertEqual(out, "")

    def test_verdicts_group_by_market(self):
        code, out, _ = run(verdicts.main, [str(self.path), "--group-by", "market"])
        self.assertEqual(code, 0)
        self.assertIn("same market group", out)

    def test_verdicts_missing_column_exits_2(self):
        code, _, err = run(verdicts.main, [str(self.path), "--group-by", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("column nope not in the data; available:", err)

    def test_mix_groups_by_market(self):
        code, out, _ = run(mix.main, [str(self.path), "--group-by", "market"])
        self.assertEqual(code, 0)
        self.assertIn("By market", out)
        self.assertIn("US", out)

    def test_mix_missing_column_exits_2(self):
        code, _, err = run(mix.main, [str(self.path), "--group-by", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("column nope not in the data; available:", err)

    def test_mix_lists_unknown_ad_types_and_says_to_ask(self):
        rows = [{"Ad name": "TYPE:Clearout | ANGLE:Hero | FMT:Static", "Amount spent": 9, "Impressions": 900,
                 "Day": "2026-03-01"},
                {"Ad name": "TYPE:BAU | ANGLE:Hero | FMT:Static", "Amount spent": 9, "Impressions": 900,
                 "Day": "2026-03-01"}]
        result = mix.analyse_mix(cm.load_rows(rows))
        self.assertEqual(result["unknown_types"], ["clearout"])
        self.assertIn("Ask the user which type", mix.render(result))

    def test_key_map_flag_reaches_the_parser(self):
        rows = [{"Ad name": "PX:Dusk | FMT:Reel", "Amount spent": 9, "Impressions": 900, "Day": "2026-03-01"}]
        result = mix.analyse_mix(cm.load_rows(rows), key_map={"PX": "concept"})
        self.assertEqual(result["classified"], 1)
        self.assertEqual(result["by_concept"][0]["concept"], "Dusk")
        code, _, _ = run(grade.main, [str(self.path), "--key-map", "PX=concept"])
        self.assertEqual(code, 0)


class DetectNamingCliTest(unittest.TestCase):
    def test_csv_input_reports_full_match_in_plain_english_first(self):
        code, out, _ = run(detect_naming.main, [str(FIXTURE)])
        self.assertEqual(code, 0)
        self.assertIn("100%", out.splitlines()[0])
        self.assertIn("concept", out)
        self.assertNotIn("Traceback", out)

    def test_text_file_input_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "names.txt"
            path.write_text(KEYED + "\n" + "Spring hero v1\n", encoding="utf-8")
            code, out, _ = run(detect_naming.main, [str(path), "--json"])
            self.assertEqual(code, 0)
            self.assertIn('"match_rate": 50.0', out)
            code, out, _ = run(detect_naming.main, [str(path)])
            self.assertIn("Spring hero v1", out)
            self.assertIn("Ask the user", out)

    def test_empty_input_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("\n", encoding="utf-8")
            code, _, err = run(detect_naming.main, [str(path)])
            self.assertEqual(code, 2)
            self.assertIn("no ad names", err)


if __name__ == "__main__":
    unittest.main()
