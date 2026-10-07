import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "colour-grade" / "scripts"
sys.path.insert(0, str(SCRIPT))
sys.path.insert(0, str(ROOT / "tools"))

import make_swatch  # noqa: E402
import palette  # noqa: E402

SWATCH = ROOT / "examples" / "acme" / "swatch.png"
EXPECTED = {"#2F4A3A": 36, "#E6DCC8": 24, "#B5532A": 18, "#3B4A5A": 13, "#D9A441": 9}


class PaletteTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"CREATIVE_SKILLS_NO_PILLOW": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_swatch_file_matches_generator(self):
        self.assertEqual(SWATCH.read_bytes(), make_swatch.png_bytes())

    def test_stdlib_png_returns_exact_swatch_colours(self):
        result = palette.analyse_image(str(SWATCH), k=6)
        found = {c["hex"].upper(): c["share"] for c in result["colours"]}
        self.assertEqual(set(found), set(EXPECTED))
        for hex_code, share in EXPECTED.items():
            self.assertAlmostEqual(found[hex_code], share, delta=0.5)
        self.assertAlmostEqual(sum(found.values()), 100.0, delta=0.5)

    def test_top_k_limits_colours(self):
        result = palette.analyse_image(str(SWATCH), k=2)
        self.assertEqual([c["hex"].upper() for c in result["colours"]], ["#2F4A3A", "#E6DCC8"])

    def test_numbers_are_reported(self):
        result = palette.analyse_image(str(SWATCH), k=6)
        for key in ("brightness", "saturation", "warm_share", "cool_share", "contrast_spread",
                    "text_contrast_ratio"):
            self.assertIsNotNone(result[key], key)
        self.assertGreater(result["text_contrast_ratio"], 1.0)

    def test_wcag_black_on_white_is_21(self):
        self.assertEqual(round(palette.contrast_ratio("#000000", "#FFFFFF"), 1), 21.0)
        self.assertEqual(round(palette.contrast_ratio("#FFFFFF", "#FFFFFF"), 1), 1.0)

    def test_unsupported_format_without_pillow_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "ad.jpg"
            fake.write_bytes(b"\xff\xd8\xff\xe0not really a jpeg")
            out = subprocess.run([sys.executable, str(SCRIPT / "palette.py"), str(fake)],
                                 capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(out.returncode, 2)
        self.assertIn("install Pillow (pip install pillow)", out.stderr)

    def test_directory_flags_shared_dominant_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                (Path(tmp) / ("ad%d.png" % i)).write_bytes(make_swatch.png_bytes())
            out = subprocess.run([sys.executable, str(SCRIPT / "palette.py"), tmp],
                                 capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("share a dominant colour family", out.stdout)

    def test_json_output(self):
        out = subprocess.run([sys.executable, str(SCRIPT / "palette.py"), str(SWATCH), "--json"],
                             capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('"colours"', out.stdout)


if __name__ == "__main__":
    unittest.main()
