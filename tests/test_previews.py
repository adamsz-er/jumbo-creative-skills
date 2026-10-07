import re
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "creative-report" / "scripts"
sys.path.insert(0, str(SCRIPT))

import panels  # noqa: E402
import previews  # noqa: E402


def png(width=2, height=2, pad=0):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x7c\x3a\xed" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"tEXt", b"pad\x00" + b"x" * pad) + chunk(b"IEND", b""))


def jpeg():
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00\xff\xd9")


def webp():
    body = b"WEBPVP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (1).to_bytes(3, "little") + (1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", len(body)) + body


class PreviewsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def put(self, name, data, sub="previews"):
        folder = self.dir / sub
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(data)
        return folder

    def test_png_jpeg_webp_gif_are_sniffed_and_embedded(self):
        folder = self.put("1.png", png())
        self.put("2.jpg", jpeg())
        self.put("3.webp", webp())
        self.put("4.gif", b"GIF89a\x02\x00\x02\x00" + b"\x00" * 8)
        found = previews.Previews(str(folder))
        for ad_id, mime in (("1", "image/png"), ("2", "image/jpeg"), ("3", "image/webp"), ("4", "image/gif")):
            uri = found.embed(ad_id)
            self.assertTrue(uri and uri.startswith("data:%s;base64," % mime), (ad_id, uri))
        self.assertEqual(found.kinds["preview"], 4)

    def test_dimensions_are_read_from_headers(self):
        self.assertEqual(previews.dimensions(png(2, 2), "image/png"), (2, 2))
        self.assertEqual(previews.dimensions(jpeg(), "image/jpeg"), (3, 2))
        self.assertEqual(previews.dimensions(webp(), "image/webp"), (2, 2))

    def test_unknown_bytes_are_skipped_with_a_reason(self):
        folder = self.put("9.png", b"this is not an image at all")
        found = previews.Previews(str(folder))
        shown = found.resolve("9")
        self.assertEqual((shown["kind"], shown["reason"]), ("placeholder", previews.UNRECOGNISED))
        self.assertIsNone(found.embed("9"))

    def test_a_file_over_the_cap_is_skipped(self):
        folder = self.put("5.png", png(pad=3000))
        found = previews.Previews(str(folder), max_kb=1)
        self.assertEqual(found.resolve("5")["reason"], previews.TOO_LARGE)
        self.assertEqual(previews.Previews(str(folder), max_kb=8).resolve("5")["kind"], "preview")

    def test_the_total_budget_stops_embedding(self):
        folder = self.dir / "previews"
        folder.mkdir()
        for i in range(4):
            (folder / ("%d.png" % i)).write_bytes(png(pad=1500))
        found = previews.Previews(str(folder), budget_kb=3)
        kinds = [found.resolve(str(i))["kind"] for i in range(4)]
        self.assertEqual(kinds[0], "preview")
        self.assertEqual(kinds[-1], "placeholder")
        self.assertEqual(found.reasons[previews.BUDGET], kinds.count("placeholder"))

    def test_preference_is_preview_then_thumbnail_then_placeholder(self):
        previews_dir = self.put("1.png", png())
        thumbs_dir = self.put("1.jpg", jpeg(), sub="thumbs")
        self.put("2.jpg", jpeg(), sub="thumbs")
        found = previews.Previews(str(previews_dir), str(thumbs_dir))
        self.assertEqual(found.resolve("1")["kind"], "preview")
        self.assertEqual(found.resolve("2")["kind"], "thumbnail")
        missing = found.resolve("3")
        self.assertEqual((missing["kind"], missing["reason"]), ("placeholder", previews.NO_PREVIEW))

    def test_a_bad_preview_falls_back_to_the_thumbnail_but_keeps_nothing_silently(self):
        previews_dir = self.put("1.png", b"junk")
        thumbs_dir = self.put("1.jpg", jpeg(), sub="thumbs")
        found = previews.Previews(str(previews_dir), str(thumbs_dir))
        self.assertEqual(found.resolve("1")["kind"], "thumbnail")

    def test_an_unsafe_ad_id_never_reaches_the_filesystem(self):
        folder = self.put("1.png", png())
        found = previews.Previews(str(folder))
        self.assertEqual(found.resolve("../previews/1")["reason"], previews.NO_PREVIEW)

    def test_the_footer_sentence_counts_each_kind_and_reason(self):
        folder = self.put("1.png", png())
        self.put("2.png", b"junk")
        found = previews.Previews(str(folder), str(self.put("3.jpg", jpeg(), sub="thumbs")))
        for ad_id in ("1", "2", "3", "4"):
            found.resolve(ad_id)
        text = found.summary()
        self.assertIn("previews embedded 1", text)
        self.assertIn("thumbnails used 1", text)
        self.assertIn("placeholders 2", text)
        self.assertIn("%s: 1" % previews.UNRECOGNISED, text)
        self.assertIn("%s: 1" % previews.NO_PREVIEW, text)
        self.assertRegex(text, r"[\d.]+ KB embedded in total")


    def test_the_budget_is_never_overshot_by_a_file(self):
        folder = self.dir / "previews"
        folder.mkdir()
        for i in range(5):
            (folder / ("%d.png" % i)).write_bytes(png(pad=230 * 1024))
        found = previews.Previews(str(folder), max_kb=240, budget_kb=1000)
        kinds = [found.resolve(str(i))["kind"] for i in range(5)]
        self.assertLessEqual(found.total_bytes, 1000 * 1024)
        self.assertEqual(kinds.count("preview"), 4)
        self.assertEqual(found.resolve("4")["reason"], previews.BUDGET)

    def test_a_file_over_the_cap_is_rejected_by_size_without_being_read(self):
        folder = self.put("6.png", b"\x00" * (3 * 1024))
        found = previews.Previews(str(folder), max_kb=1)
        self.assertEqual(found.resolve("6")["reason"], previews.TOO_LARGE)

    def test_each_ad_is_resolved_once_and_embedded_once(self):
        folder = self.put("1.png", png())
        found = previews.Previews(str(folder))
        first = found.resolve("1")
        self.assertIs(found.resolve("1"), first)
        found.resolve("2")
        found.resolve("2")
        self.assertEqual((found.kinds["preview"], found.kinds["placeholder"]), (1, 1))
        self.assertEqual(found.sprite().count("data:image/png"), 1)
        self.assertEqual(previews.Previews().sprite(), "")


class CardImageTest(unittest.TestCase):
    def test_cards_reference_one_symbol_with_a_label_and_placeholders_say_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "7.png").write_bytes(png())
            ctx = panels.Ctx(previews=previews.Previews(str(folder)))
            with_image = panels.ad_card(ctx, {"ad": "7", "ad_name": "x", "format": "static"})
            again = panels.ad_card(ctx, {"ad": "7", "ad_name": "x", "format": "static"})
            without = panels.ad_card(ctx, {"ad": "8", "ad_name": "x", "format": "static"})
        self.assertRegex(with_image, r'<svg class="pv" role="img" aria-label="[^"]+\(static\)" viewBox="0 0 2 2" width="2" height="2"><use href="#pv-7" width="2" height="2"/></svg>')
        self.assertNotIn("data:image", with_image)
        self.assertEqual(ctx.previews.sprite().count("data:image/png"), 1)
        self.assertEqual(with_image, again)
        self.assertIn("preview unavailable:", without)
        self.assertIn(previews.NO_PREVIEW, without)
        self.assertIsNone(re.search(r'(src|href)="https?:', with_image + without))


if __name__ == "__main__":
    unittest.main()
