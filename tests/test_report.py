import html as html_lib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))

import report  # noqa: E402

FIXTURE = ROOT / "examples" / "acme" / "ads_daily.csv"
HEADINGS = ("Overview analysis", "Key numbers", "Performance over time", "Do these first", "Funnel", "Pareto",
            "Verdict board", "Fatigue", "Format", "White space", "Briefing", "Data and method", "Missing data and caveats")
BALANCED = ("section", "table", "svg", "div", "ul", "thead", "tbody", "tr", "td", "th", "article", "details", "nav", "footer")


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag in BALANCED:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in BALANCED:
            if not self.stack or self.stack[-1] != tag:
                self.errors.append("unexpected </%s> with %s open" % (tag, self.stack[-3:]))
            else:
                self.stack.pop()


def run_json(skill, script, *extra):
    path = ROOT / "skills" / skill / "scripts" / script
    out = subprocess.run([sys.executable, str(path), str(FIXTURE), "--json"] + list(extra),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.grade, cls.verdicts, cls.mix = tmp / "grade.json", tmp / "verdicts.json", tmp / "mix.json"
        cls.grade.write_text(run_json("creative-grader", "grade.py"))
        cls.verdicts.write_text(run_json("keep-or-kill", "verdicts.py"))
        cls.mix.write_text(run_json("creative-mix", "mix.py"))
        cls.out = tmp / "report.html"
        code = report.main([str(FIXTURE), "--grade", str(cls.grade), "--verdicts", str(cls.verdicts),
                            "--mix", str(cls.mix), "--profile",
                            str(ROOT / "examples" / "acme" / "brand-profile.md"),
                            "--title", "Acme creative review", "--csv", str(FIXTURE), "-o", str(cls.out)])
        assert code == 0
        cls.html = cls.out.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_section_heading_is_present(self):
        for heading in HEADINGS:
            self.assertIn(heading, self.html)

    def test_tokens_and_svg(self):
        self.assertIn("--accent: hsl(251 97% 60%)", self.html)
        self.assertIn("--bar: hsl(222 47% 8%)", self.html)
        self.assertIn("<svg", self.html)
        self.assertIn("prefers-color-scheme: dark", self.html)
        self.assertIn("@media print", self.html)

    def test_no_external_scripts_and_only_font_hosts(self):
        self.assertNotIn("<script src=", self.html)
        self.assertNotRegex(self.html, r"<script[^>]+src=")
        hosts = set(re.findall(r"https?://([^/\"'\s)]+)", self.html))
        self.assertLessEqual(hosts, {"fonts.googleapis.com", "fonts.gstatic.com"})

    def test_every_missing_note_from_inputs_is_surfaced(self):
        notes = set()
        for path in (self.grade, self.verdicts, self.mix):
            notes |= set(re.findall(r"n/a \(missing [^)]*\)", path.read_text()))
        self.assertTrue(notes, "fixture should carry at least one missing-data note")
        for note in notes:
            self.assertIn(report.interact.plain_ids(note), self.html)

    def test_html_is_balanced(self):
        parser = Balance()
        parser.feed(self.html)
        self.assertEqual(parser.errors, [])
        self.assertEqual(parser.stack, [])

    def test_basis_and_footer_text(self):
        self.assertIn("never benchmarks", self.html)
        self.assertIn("by Elephant Room", self.html)
        self.assertIn("only outside request this page makes is the font stylesheet", self.html)

    def test_currency_is_read_from_the_export_header(self):
        self.assertIn("Spend (USD)", self.html)
        self.assertIn("CPA (USD)", self.html)
        self.assertNotIn("(account currency)", self.html)

    def test_currency_falls_back_to_a_plain_label(self):
        html = report.build_html(rows=report.cm.load_rows(str(FIXTURE)), verdicts=json.loads(self.verdicts.read_text()))
        self.assertIn("Spend (account currency)", html)

    def test_metric_names_use_display_labels(self):
        for text in ("ROAS", "Hook rate", "CTR", "CPA"):
            self.assertIn(text, self.html)
        self.assertNotRegex(self.html, r"(?<![\w_-])(cpa|roas|ctr|cpm) (top|middle|bottom)")
        self.assertIn('role="img"', self.html)

    def test_title_uses_gradient_keyword(self):
        self.assertIn('class="grad"', self.html)
        self.assertIn("Acme", self.html)

    def heading_text(self, **kw):
        html = report.build_html(rows=report.cm.load_rows(str(FIXTURE)), **kw)
        h1 = re.search(r"<h1>(.*?)</h1>", html, re.S).group(1)
        return html_lib.unescape(re.sub(r"<[^>]+>", "", h1)), html_lib.unescape(re.search(r"<title>(.*?)</title>", html).group(1))

    def test_scope_goes_in_the_title_after_the_account(self):
        self.assertEqual(self.heading_text(title="Acme", scope="Prospecting"), ("Acme · Prospecting creative review",) * 2)
        self.assertEqual(self.heading_text(title="Acme"), ("Acme creative review",) * 2)

    def test_scope_is_escaped_and_blank_scope_is_ignored(self):
        self.assertEqual(self.heading_text(title="Acme", scope="  "), ("Acme creative review",) * 2)
        html = report.build_html(rows=report.cm.load_rows(str(FIXTURE)), title="Acme", scope="<b>x</b>")
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("Acme · &lt;b&gt;x&lt;/b&gt; creative review", html)

    def test_an_explicit_title_wins_over_the_profile_name(self):
        profile = "# Creative profile: Profile Name\n- Name: Profile Name\n"
        self.assertEqual(self.heading_text(title="Explicit", profile=profile), ("Explicit creative review",) * 2)
        self.assertEqual(self.heading_text(profile=profile), ("Profile Name creative review",) * 2)
        self.assertEqual(self.heading_text(title="Explicit", profile=profile, scope="Retention"), ("Explicit · Retention creative review",) * 2)

    def test_a_title_already_ending_in_review_keeps_one_review(self):
        self.assertEqual(self.heading_text(title="Acme creative review", scope="Retention"), ("Acme · Retention creative review",) * 2)

    def test_the_scope_flag_reaches_the_page(self):
        out = Path(self._tmp.name) / "scope.html"
        self.assertEqual(report.main([str(FIXTURE), "--title", "Acme", "--scope", "Prospecting", "-o", str(out)]), 0)
        self.assertIn("Acme · Prospecting creative review", out.read_text(encoding="utf-8"))

    def test_verdict_and_mix_content_rendered(self):
        self.assertIn("Pause it:", self.html)
        self.assertIn("ugc-video", self.html)
        self.assertIn("Pause", self.html)
        self.assertIn("Scale it gradually", self.html)

    def test_html_escapes_input_text(self):
        html = report.build_html(rows=[{"ad_name": "<img src=x onerror=alert(1)> | static | c | bau | p | t | 2026-03-01",
                                        "ad_id": "1", "date": "2026-03-01", "spend": 5.0,
                                        "impressions": 5000.0}])
        self.assertNotIn("<img src=x", html)

    def test_the_committed_example_claims_a_reconcile_that_really_passes_on_its_own_totals(self):
        import contextlib
        import io
        sys.path.insert(0, str(ROOT / "shared"))
        import from_mcp
        rows = report.cm.load_rows(str(FIXTURE))
        pulled = Path(self._tmp.name) / "acme_rows.json"
        pulled.write_text(json.dumps({"data": rows}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = from_mcp.main([str(pulled), "-o", str(Path(self._tmp.name) / "acme_ads.csv"),
                                  "--expect-spend", str(sum(r["spend"] for r in rows)),
                                  "--expect-impressions", str(sum(r["impressions"] for r in rows))])
        self.assertEqual(code, 0)
        self.assertIn("reconciled against the expected totals", out.getvalue())
        example = (ROOT / "examples" / "acme" / "report.html").read_text(encoding="utf-8")
        self.assertIn('<span class="status ok">Reconciled</span>', example)
        self.assertNotIn("Not reconciled", example.split("<footer>")[0])

    def test_cli_flags_reach_the_page(self):
        out = Path(self._tmp.name) / "flags.html"
        account = Path(self._tmp.name) / "account.json"
        account.write_text('{"reach": 98765, "frequency": 2.5}')
        code = report.main([str(FIXTURE), "--verdicts", str(self.verdicts), "--title", "Acme", "--source", "Meta ads connector",
                            "--attribution", "7-day click", "--completeness", "incomplete:8", "--account", str(account),
                            "--top-n", "4", "--pareto-share", "75", "--previews", str(Path(self._tmp.name) / "none"), "-o", str(out)])
        self.assertEqual(code, 0)
        html = out.read_text(encoding="utf-8")
        for text in ("Meta ads connector", "7-day click", "Incomplete 8%", "98,765", "N=4", "75%", "placeholders"):
            self.assertIn(text, html)

    def test_csv_mode_runs_and_names_missing_sections(self):
        out = Path(self._tmp.name) / "csv.html"
        self.assertEqual(report.main([str(FIXTURE), "-o", str(out)]), 0)
        html = out.read_text(encoding="utf-8")
        for heading in HEADINGS:
            self.assertIn(heading, html)
        self.assertIn("keep-or-kill", html)
        self.assertEqual(html.count('data-state="empty"'), 13)
        parser = Balance()
        parser.feed(html)
        self.assertEqual((parser.errors, parser.stack), ([], []))


if __name__ == "__main__":
    unittest.main()
