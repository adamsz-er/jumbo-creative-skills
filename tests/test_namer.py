import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "ad-namer" / "scripts"
SCRIPT = SCRIPTS / "namer.py"
sys.path.insert(0, str(SCRIPTS))

import creative_metrics as cm  # noqa: E402
import namer  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
MAP_FIELDS = "concept,format,funnel_stage,version,launch_date"
MAP_FILL = "funnel_stage=prospecting,version=1"
SPECS = [
    {"ad_id": "a1", "Concept": "Trail Test", "Format": "UGC Video", "Ad type": "sale", "Market": "us",
     "Version": "2", "Launch date": "01/03/2026"},
    {"ad_id": "a2", "Concept": "Pack_Light", "Format": "Static", "Ad type": "bau", "Market": "AU",
     "Version": "v1", "Launch date": "2026/03/09"},
]


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)


class TempCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp = Path(self._dir.name)

    def specs(self, rows=SPECS, name="specs.csv"):
        path = self.tmp / name
        keys = list(rows[0])
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def read_map(self, path):
        with open(path, newline="") as handle:
            return list(csv.DictReader(handle))


class SlugTest(unittest.TestCase):
    def test_slug_rules(self):
        self.assertEqual(namer.slug("concept", "  Trail  Test_v2! "), "trail-test-v2")
        self.assertEqual(namer.slug("market", "us"), "US")
        self.assertEqual(namer.slug("version", "3"), "v3")
        self.assertEqual(namer.slug("version", "Beta 2"), "beta-2")
        self.assertEqual(namer.slug("ad_type", "sale"), "promo")
        self.assertEqual(namer.slug("launch_date", "01/03/2026"), "2026-03-01")
        self.assertEqual(namer.slug("launch_date", "2026/3/9"), "2026-03-09")
        self.assertEqual(namer.slug("concept", "  "), "")
        self.assertEqual(namer.slug("concept", None), "")

    def test_bad_values_raise(self):
        with self.assertRaises(ValueError) as ctx:
            namer.slug("ad_type", "weird")
        for word in ("weird",) + cm.AD_TYPES:
            self.assertIn(word, str(ctx.exception))
        with self.assertRaises(ValueError):
            namer.slug("launch_date", "2026-02-30")

    def test_every_preferred_key_maps_back(self):
        self.assertEqual(set(namer.PREFERRED_KEYS), set(namer.SCHEMA_FIELDS))
        for field, key in namer.PREFERRED_KEYS.items():
            self.assertEqual(cm.KEY_MAP[key], field)

    def test_unknown_field_lists_the_allowed_ones(self):
        with self.assertRaises(ValueError) as ctx:
            namer.parse_fields("concept,colour")
        self.assertIn("colour", str(ctx.exception))
        self.assertIn("launch_date", str(ctx.exception))


class MakeTest(TempCase):
    def test_positional_names(self):
        result = namer.make_names(namer.read_specs(self.specs()), ["concept", "format", "ad_type", "market", "version",
                                  "launch_date"], " | ", False, False, False, None)
        self.assertEqual([n["name"] for n in result["names"]], [
            "trail-test | ugc-video | promo | US | v2 | 2026-03-01",
            "pack-light | static | bau | AU | v1 | 2026-03-09"])
        self.assertTrue(all(n["parses_back"] for n in result["names"]))
        self.assertEqual(result["names"][0]["ad_id"], "a1")
        self.assertEqual(result["warnings"], [])

    def test_keyed_names(self):
        result = namer.make_names(namer.read_specs(self.specs()), ["concept", "format", "version", "launch_date"],
                                  " | ", True, False, False, None)
        self.assertEqual(result["names"][0]["name"], "CONCEPT:trail-test | FMT:ugc-video | VER:v2 | DATE:2026-03-01")
        self.assertTrue(all(n["parses_back"] for n in result["names"]))

    def test_missing_field_is_an_error_listing_rows(self):
        rows = [dict(SPECS[0]), dict(SPECS[1], Concept="")]
        with self.assertRaises(ValueError) as ctx:
            namer.make_names(namer.read_specs(self.specs(rows)), ["concept", "persona"], " | ", False, False, False, None)
        self.assertIn("row 1 is missing: persona", str(ctx.exception))
        self.assertIn("row 2 is missing: concept, persona", str(ctx.exception))

    def test_allow_missing_writes_unknown_and_warns(self):
        result = namer.make_names(namer.read_specs(self.specs()), ["concept", "persona"], " | ", False, True, False, None)
        self.assertEqual(result["names"][0]["name"], "trail-test | unknown")
        self.assertTrue(result["names"][0]["parses_back"])
        self.assertIn("row 1: unknown written for persona", result["warnings"])

    def test_separator_inside_a_value_does_not_parse_back(self):
        result = namer.make_names(namer.read_specs(self.specs()), ["concept", "format"], "-", False, False, False, None)
        first = result["names"][0]
        self.assertFalse(first["parses_back"])
        self.assertEqual(first["problems"][0], "will not parse back: concept read as nothing")
        self.assertIn("row 1: will not parse back: concept read as nothing", result["warnings"])

    def test_duplicates_are_reported_then_numbered_with_dedupe(self):
        rows = [dict(SPECS[0]), dict(SPECS[0], ad_id="a3"), dict(SPECS[0], ad_id="a4")]
        path = self.specs(rows)
        plain = namer.make_names(namer.read_specs(path), ["concept", "version"], " | ", False, False, False, None)
        self.assertTrue(any("rows 1, 2, 3 share the name trail-test | v2" in w for w in plain["warnings"]))
        fixed = namer.make_names(namer.read_specs(path), ["concept", "version"], " | ", False, False, True, None)
        self.assertEqual([n["name"] for n in fixed["names"]],
                         ["trail-test | v2", "trail-test | v2-v2", "trail-test | v2-v3"])
        self.assertEqual(fixed["warnings"], [])
        last = namer.make_names(namer.read_specs(path), ["concept", "format"], " | ", False, False, True, None)
        self.assertEqual([n["name"] for n in last["names"]][1:],
                         ["trail-test | ugc-video-v2", "trail-test | ugc-video-v3"])

    def test_json_specs_are_read(self):
        path = self.tmp / "specs.json"
        path.write_text(json.dumps([{"Concept": "A b", "Funnel stage": "prospecting", "version": 1}]))
        result = namer.make_names(namer.read_specs(str(path)), ["concept", "funnel_stage", "version"],
                                  " | ", False, False, False, None)
        self.assertEqual(result["names"][0]["name"], "a-b | prospecting | v1")

    def test_cli_names_json_and_output_file(self):
        path = self.specs()
        done = run("make", path, "--fields", "concept,format,ad_type", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        data = json.loads(done.stdout)
        self.assertEqual(data["names"][0]["name"], "trail-test | ugc-video | promo")
        self.assertEqual(data["settings"]["fields"], ["concept", "format", "ad_type"])
        out = self.tmp / "names.csv"
        done = run("make", path, "--fields", "concept,format", "-o", out)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.read_map(out)[1], {"ad_id": "a2", "name": "pack-light | static"})
        self.assertNotIn("pack-light | static", done.stdout)
        text = run("make", path, "--fields", "concept,format")
        self.assertEqual(text.stdout.splitlines()[:2], ["trail-test | ugc-video", "pack-light | static"])

    def test_make_output_refuses_an_existing_file_unless_forced(self):
        path = self.specs()
        out = self.tmp / "names.csv"
        out.write_text("keep me")
        done = run("make", path, "--fields", "concept,format", "-o", out)
        self.assertEqual(done.returncode, 2)
        self.assertIn("already exists", done.stderr)
        self.assertEqual(out.read_text(), "keep me")
        done = run("make", path, "--fields", "concept,format", "-o", out, "--force")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.read_map(out)[0]["name"], "trail-test | ugc-video")

    def test_cli_exit_2(self):
        path = self.specs()
        bad_type = self.specs([dict(SPECS[0], **{"Ad type": "weird"})], "bad_type.csv")
        bad_date = self.specs([dict(SPECS[0], **{"Launch date": "2026-13-45"})], "bad_date.csv")
        done = run("make", bad_type, "--fields", "concept,ad_type")
        self.assertEqual(done.returncode, 2)
        for word in ("weird",) + cm.AD_TYPES:
            self.assertIn(word, done.stderr)
        self.assertEqual(run("make", bad_date, "--fields", "concept,launch_date").returncode, 2)
        done = run("make", path, "--fields", "concept,persona")
        self.assertEqual(done.returncode, 2)
        self.assertIn("row 1 is missing: persona", done.stderr)
        self.assertIn("row 2 is missing: persona", done.stderr)
        allowed = run("make", path, "--fields", "concept,persona", "--allow-missing")
        self.assertEqual(allowed.returncode, 0)
        self.assertIn("trail-test | unknown", allowed.stdout)
        self.assertIn("row 1: unknown written for persona", allowed.stdout)
        done = run("make", path, "--fields", "concept,colour")
        self.assertEqual(done.returncode, 2)
        self.assertIn("launch_date", done.stderr)
        self.assertEqual(run("make", path).returncode, 2)
        self.assertEqual(run("make", self.tmp / "none.csv", "--fields", "concept").returncode, 2)
        self.assertNotIn("Traceback", done.stderr)


class AuditTest(TempCase):
    def test_fixture_is_fully_read_and_persona_is_missing_everywhere(self):
        done = run("audit", FIXTURE, "--fields", "concept,format,persona", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        data = json.loads(done.stdout)
        self.assertEqual(data["match_rate"], 100.0)
        self.assertEqual(data["names"], 30)
        self.assertEqual(data["separator"], " | ")
        self.assertEqual(data["target"]["persona"]["count"], 0)
        self.assertEqual(data["target"]["persona"]["missing_count"], 30)
        self.assertEqual(len(data["target"]["persona"]["missing_names"]), 8)
        self.assertEqual(data["target"]["concept"]["missing_count"], 0)
        self.assertEqual(data["verdict"], "100% of 30 names follow one convention; 1 target field is missing from most names.")

    def test_text_leads_with_the_verdict_and_caps_the_list(self):
        done = run("audit", FIXTURE, "--fields", "concept,format,persona,funnel_stage,version")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0],
                         "100% of 30 names follow one convention; 3 target fields are missing from most names.")
        self.assertIn("persona: on 0 of 30 names (0%)", done.stdout)
        self.assertIn("... 22 more", done.stdout)

    def test_audit_without_fields(self):
        done = run("audit", FIXTURE)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "100% of 30 names follow one convention.")
        self.assertNotIn("Target fields", done.stdout)

    def test_duplicates_and_case_variants(self):
        rows = [{"Ad name": "Trail Test | UGC | v1", "Ad ID": "1", "Day": "2026-03-01"},
                {"Ad name": "Trail Test | UGC | v1", "Ad ID": "2", "Day": "2026-03-01"},
                {"Ad name": "trail test | ugc | v1", "Ad ID": "3", "Day": "2026-03-01"},
                {"Ad name": "Other | static | v1", "Ad ID": "4", "Day": "2026-03-01"}]
        path = self.specs(rows, "ads.csv")
        data = json.loads(run("audit", path, "--json").stdout)
        self.assertEqual(data["duplicate_names"], [{"name": "Trail Test | UGC | v1", "ad_ids": ["1", "2"]}])
        self.assertEqual(data["case_or_spacing_variants"], [["Trail Test | UGC | v1", "trail test | ugc | v1"]])
        text = run("audit", path).stdout
        self.assertIn("Names used by more than one ad id", text)
        self.assertIn("differ only by case or spacing", text)

    def test_text_file_of_names(self):
        path = self.tmp / "names.txt"
        path.write_text("CONCEPT:a | FMT:video\nCONCEPT:b | FMT:static\n\n")
        data = json.loads(run("audit", path, "--fields", "concept,persona", "--json").stdout)
        self.assertEqual(data["names"], 2)
        self.assertEqual(data["style"], "keyed")
        self.assertEqual(data["target"]["concept"]["count"], 2)
        self.assertEqual(data["target"]["persona"]["missing_count"], 2)
        self.assertEqual(data["duplicate_names"], [])

    def test_exit_2(self):
        empty = self.tmp / "empty.txt"
        empty.write_text("")
        self.assertEqual(run("audit", empty).returncode, 2)
        self.assertEqual(run("audit", FIXTURE, "--fields", "nope").returncode, 2)
        self.assertEqual(run("audit", FIXTURE, "--where", "nope=1").returncode, 2)


class MapTest(TempCase):
    def make_map(self, *extra, out=None):
        out = out or self.tmp / "rename-map.csv"
        return run("map", FIXTURE, "--fields", MAP_FIELDS, "-o", out, *extra), out

    def test_fixture_map_with_fill(self):
        done, out = self.make_map("--fill", MAP_FILL)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.read_text().splitlines()[0], "ad_id,old_name,new_name,missing_fields,changed")
        rows = self.read_map(out)
        self.assertEqual(len(rows), 30)
        first = next(r for r in rows if r["ad_id"] == "120000000001")
        self.assertEqual(first["new_name"], "durability-test | ugc-video | prospecting | v1 | 2026-03-01")
        self.assertEqual(first["changed"], "yes")
        self.assertEqual(first["missing_fields"], "")
        self.assertIn("30 of their names change", done.stdout)
        self.assertIn("This file is a plan: nothing in your ad account has been renamed. Apply it yourself in "
                      "Ads Manager (or bulk edit), after checking it.", done.stdout)

    def test_unchanged_name_is_marked_no(self):
        rows = [{"Ad name": "CONCEPT:a | FMT:video", "Ad ID": "1", "Day": "2026-03-01"}]
        path = self.specs(rows, "ads.csv")
        out = self.tmp / "m.csv"
        done = run("map", path, "--fields", "concept,format", "--keyed", "-o", out)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.read_map(out)[0]["changed"], "no")

    def test_a_separator_inside_the_tokens_is_flagged(self):
        done, out = self.make_map("--fill", MAP_FILL, "--sep", "-")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("will not parse back with this separator", done.stdout)

    def test_the_default_separator_raises_no_parse_warning(self):
        done, _ = self.make_map("--fill", MAP_FILL)
        self.assertNotIn("will not parse back", done.stdout)

    def test_without_fill_missing_fields_become_unknown(self):
        done, out = self.make_map()
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = self.read_map(out)
        self.assertEqual(rows[0]["missing_fields"], "funnel_stage;version")
        self.assertEqual(rows[0]["new_name"], "durability-test | ugc-video | unknown | unknown | 2026-03-01")
        self.assertIn("funnel_stage (30)", done.stdout)
        self.assertIn("version (30)", done.stdout)

    def test_collisions_are_counted(self):
        done, out = self.make_map("--fill", MAP_FILL, "--json")
        data = json.loads(done.stdout)
        self.assertEqual(data["summary"]["ads"], 30)
        self.assertEqual(data["summary"]["colliding_names"], 0)
        shared = run("map", FIXTURE, "--fields", "format", "-o", self.tmp / "c.csv", "--json")
        summary = json.loads(shared.stdout)["summary"]
        self.assertGreater(summary["colliding_names"], 0)
        self.assertGreater(summary["colliding_ads"], summary["colliding_names"])

    def test_json_still_writes_the_csv(self):
        done, out = self.make_map("--fill", MAP_FILL, "--json")
        data = json.loads(done.stdout)
        self.assertEqual(len(data["rows"]), 30)
        self.assertTrue(out.exists())
        self.assertEqual(len(self.read_map(out)), 30)
        self.assertEqual(data["settings"]["fill"], {"funnel_stage": "prospecting", "version": "v1"})

    def test_refuses_to_overwrite_without_force(self):
        out = self.tmp / "keep.csv"
        out.write_text("precious")
        done, _ = self.make_map("--fill", MAP_FILL, out=out)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--force", done.stderr)
        self.assertEqual(out.read_text(), "precious")
        done, _ = self.make_map("--fill", MAP_FILL, "--force", out=out)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.read_map(out)), 30)

    def test_where_keeps_only_promo_ads(self):
        all_ads = {a["ad_id"] for a in cm.aggregate_by_ad(cm.load_rows(str(FIXTURE)))}
        promo = {a["ad_id"] for a in cm.aggregate_by_ad(cm.load_rows(str(FIXTURE))) if a["ad_type"] == "promo"}
        self.assertTrue(promo and promo < all_ads)
        done, out = self.make_map("--fill", MAP_FILL, "--where", "ad_type=promo")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual({r["ad_id"] for r in self.read_map(out)}, promo)
        self.assertIn("scope:", done.stdout)

    def test_keyed_new_names(self):
        done, out = self.make_map("--fill", MAP_FILL, "--keyed")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.read_map(out)[0]["new_name"],
                         "CONCEPT:durability-test | FMT:ugc-video | STAGE:prospecting | VER:v1 | DATE:2026-03-01")

    def test_exit_2(self):
        out = self.tmp / "x.csv"
        self.assertEqual(run("map", FIXTURE, "-o", out).returncode, 2)
        self.assertEqual(run("map", FIXTURE, "--fields", MAP_FIELDS).returncode, 2)
        done = run("map", FIXTURE, "--fields", "concept", "--fill", "persona=x", "-o", out)
        self.assertEqual(done.returncode, 2)
        self.assertIn("not in --fields", done.stderr)
        self.assertEqual(run("map", FIXTURE, "--fields", "concept", "--fill", "concept", "-o", out).returncode, 2)
        self.assertFalse(out.exists())
        no_ids = self.specs([{"Ad name": "a | video", "Day": "2026-03-01"}], "noids.csv")
        done = run("map", no_ids, "--fields", "concept", "-o", out)
        self.assertEqual(done.returncode, 2)
        self.assertIn("Ad ID", done.stderr)
        bad = run("map", FIXTURE, "--fields", "ad_type", "--type-map", "bau=nonsense", "-o", out)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("Traceback", bad.stderr)
        self.assertEqual(run("audit").returncode, 2)


if __name__ == "__main__":
    unittest.main()
