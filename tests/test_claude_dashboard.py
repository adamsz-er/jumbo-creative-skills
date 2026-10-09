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
        self.assertEqual(manifest["files"], ["index.html", "dashboard.css", "dashboard.js"])
        self.assertEqual([s["doc"] for s in manifest["store"]], ["dash/meta", "files/index.html", "files/dashboard.css", "files/dashboard.js"])
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

    def test_without_thumbnails_the_page_has_no_thumbnail_column(self):
        self.assertNotIn('data-field="thumb"', (self.bundle / "files" / "index.html").read_text())
        self.assertTrue(all("thumb" not in r for r in rows_of(self.bundle, "verdicts")))
        images = next(r for r in rows_of(self.bundle, "header") if r["fact"] == "Ad images")
        self.assertEqual(images["value"], dashboard.THUMBS_NONE)

    # ---------- size limits ----------

    def test_thumbnails_ride_in_the_ad_list_when_they_fit(self):
        thumbs = self.tmp / "thumbs"
        thumbs.mkdir(exist_ok=True)
        for ad in ("120000000001", "120000000002"):
            shutil.copy(EXAMPLE / "previews" / ("%s.png" % ad), thumbs / ("%s.png" % ad))
        _, ctx = self.build(previews=Previews(None, str(thumbs)))
        out = self.tmp / "thumbs-bundle"
        dashboard.write_bundle(ctx, str(out))
        with_thumb = [r for r in rows_of(out, "verdicts") if r.get("thumb")]
        self.assertEqual(sorted(r["ad_id"] for r in with_thumb), ["120000000001", "120000000002"])
        self.assertTrue(all(r["thumb"].startswith("data:image/png;base64,") for r in with_thumb))
        self.assertIn('data-field="thumb"', (out / "files" / "index.html").read_text())
        self.assertEqual(dashboard.check_bundle(str(out)), [])

    def test_an_oversize_ad_list_drops_the_thumbnails_and_says_so(self):
        thumbs = self.tmp / "thumbs-big"
        thumbs.mkdir(exist_ok=True)
        for png in (EXAMPLE / "previews").glob("*.png"):
            shutil.copy(png, thumbs / png.name)
        _, ctx = self.build(previews=Previews(None, str(thumbs)))
        out = self.tmp / "oversize-bundle"
        with mock.patch.object(dashboard, "DATASET_MAX", 64 * 1024):
            dashboard.write_bundle(ctx, str(out))
            self.assertEqual(dashboard.check_bundle(str(out)), [])
        self.assertTrue(all("thumb" not in r for r in rows_of(out, "verdicts")))
        self.assertNotIn('data-field="thumb"', (out / "files" / "index.html").read_text())
        images = next(r for r in rows_of(out, "header") if r["fact"] == "Ad images")
        self.assertEqual(images["value"], dashboard.THUMBS_LEFT_OUT)

    # ---------- the same numbers as the HTML ----------

    def test_every_dataset_carries_what_the_html_path_computed(self):
        ctx, num = self.ctx, dashboard._num
        out = self.tmp / "parity"
        dashboard.write_bundle(ctx, str(out))
        tiles = panels.kpi_tiles(ctx)
        self.assertEqual([(r["metric"], r["value"], r["shown"]) for r in rows_of(out, "kpis")],
                         [(t["metric"], num(t["value"]), t["shown"]) for t in tiles])
        days, series = panels.time_series(ctx)
        self.assertEqual([(r["day"], r["metric"], r["value"], r["average"]) for r in rows_of(out, "daily")],
                         [(d, s["key"], num(v), num(a)) for s in series for d, v, a in zip(days, s["values"], s["average"])])
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
                         (".text((c) => c);", ".html((c) => c);")):
            b = self.copy()
            self.edit(b, "files/dashboard.js", old, new)
            store = b / "store" / "files-dashboard.js.json"
            store.write_text(json.dumps({"text": (b / "files" / "dashboard.js").read_text()}))
            self.assertFlags(b, "writes markup from script")

    def test_check_flags_an_on_attribute(self):
        b = self.copy()
        self.edit(b, "files/index.html", '<nav class="cr-jump" id="jump"', '<nav class="cr-jump" onclick="go()" id="jump"')
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
        self.assertFlags(b, "dataset header does not carry schema version 1")

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


needs_dom = unittest.skipUnless(shutil.which("node") and os.environ.get("CR_JSDOM") and os.environ.get("CR_D3"),
                                "set CR_JSDOM (a jsdom install) and CR_D3 (d3.min.js, v7) and have node to run the page in a DOM")


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
            self.assertFalse(probe[holder]["hidden"], holder)
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


PARENT = "9d21f51"  # main as this feature branched: the report scripts before any Claude dashboard code


class ParentHtmlTest(unittest.TestCase):
    """Without the flag the report is the one the scripts wrote before this feature, byte for byte."""

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
            self.assertEqual(made["parent"], made["now"])


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
            self.assertEqual((EXAMPLE / "claude-dashboard" / "files" / name).read_text(), dashboard.page_text(name, False), name)


if __name__ == "__main__":
    unittest.main()
