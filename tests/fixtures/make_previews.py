#!/usr/bin/env python3
"""Draw a fictional mock ad for every ad in the Acme example, so the example dashboard shows real previews.

Standard library only: a minimal PNG writer over zlib. Each ad gets a 1080 x 1350 picture from a fixed six-colour
palette (chosen by concept), a large product block, grey bars where the headline would sit and a call-to-action pill;
a video gets a play triangle and a carousel gets its dots. No words are drawn: colour and layout are enough to tell
the ads apart. Deterministic: the same CSV always writes the same files. The pictures are invented.

Usage: python3 tests/fixtures/make_previews.py --out examples/acme/previews
"""
from __future__ import annotations

import argparse
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "creative-report" / "scripts"))

import creative_metrics as cm  # noqa: E402

WIDTH, HEIGHT = 1080, 1350
RGB = Tuple[int, int, int]
Span = Tuple[int, int, RGB]
Shape = Callable[[int], List[Span]]

# background, product colour: six fixed pairs, picked by concept
PALETTE: Sequence[Tuple[RGB, RGB]] = (
    ((232, 221, 203), (64, 104, 92)),
    ((200, 219, 206), (176, 92, 64)),
    ((206, 214, 232), (232, 168, 56)),
    ((240, 214, 205), (52, 76, 120)),
    ((222, 208, 232), (84, 124, 84)),
    ((246, 230, 170), (140, 64, 96)),
)
INK: RGB = (52, 56, 66)
PAPER: RGB = (250, 250, 247)
GREY: RGB = (176, 178, 184)


def _rounded(x0: int, y0: int, x1: int, y1: int, radius: int, colour: RGB) -> Shape:
    def spans(y: int) -> List[Span]:
        if y < y0 or y >= y1:
            return []
        edge = min(y - y0, y1 - 1 - y)
        inset = 0 if edge >= radius else int(round(radius - math.sqrt(max(radius * radius - (radius - edge) ** 2, 0))))
        return [(x0 + inset, x1 - inset, colour)]
    return spans


def _circle(cx: int, cy: int, radius: int, colour: RGB) -> Shape:
    def spans(y: int) -> List[Span]:
        dy = abs(y - cy)
        if dy > radius:
            return []
        dx = int(math.sqrt(radius * radius - dy * dy))
        return [(cx - dx, cx + dx, colour)]
    return spans


def _play(cx: int, cy: int, half: int, colour: RGB) -> Shape:
    def spans(y: int) -> List[Span]:
        dy = abs(y - cy)
        if dy > half:
            return []
        left = cx - half // 2
        return [(left, left + int((half - dy) * 1.5), colour)]
    return spans


def _number(ad_id: str) -> int:
    digits = re.sub(r"\D", "", str(ad_id))
    return int(digits) if digits else sum(map(ord, str(ad_id)))


def _concept_index(concept: str) -> int:
    return sum(ord(c) * (n + 1) for n, c in enumerate(str(concept))) % len(PALETTE)


def mock_shapes(ad_id: str, concept: str, fmt: str) -> Tuple[RGB, List[Shape]]:
    """The background colour and the shapes, back to front, for one ad."""
    background, accent = PALETTE[_concept_index(concept)]
    n = _number(ad_id)
    layout, shift = n % 4, (n * 37) % 90
    bars_top = layout in (1, 2)
    shapes: List[Shape] = []
    if layout == 0:
        shapes += [_circle(540, 640, 320 + shift // 3, accent), _circle(540, 640, 220 + shift // 3, PAPER)]
    elif layout == 1:
        shapes += [_rounded(120 + shift, 420, 760 + shift, 1060, 90, accent), _rounded(200 + shift, 500, 680 + shift, 980, 60, PAPER)]
    elif layout == 2:
        shapes += [_rounded(80, 640 - shift, 1000, 1180 - shift, 120, accent), _circle(540, 910 - shift, 170, PAPER)]
    else:
        shapes += [_circle(400 + shift, 700, 260, accent), _circle(680 - shift, 780, 220, PAPER), _circle(680 - shift, 780, 130, accent)]
    y = 110 if bars_top else 1090
    for width in (820 - shift, 600, 700 - shift // 2):
        shapes.append(_rounded(130, y, 130 + width, y + 44, 22, INK if y in (110, 1090) else GREY))
        y += 74
    cta_y = 1210 if bars_top else 60
    shapes.append(_rounded(130 if layout % 2 else 700, cta_y, 130 + 250 if layout % 2 else 700 + 250, cta_y + 84, 42, accent))
    if "video" in str(fmt) or str(fmt) == "partnership":
        shapes += [_circle(540, 675, 120, INK), _play(540, 675, 62, PAPER)]
    elif str(fmt) == "carousel":
        shapes += [_circle(540 + 60 * k, 1300, 14, INK if k == 1 else GREY) for k in (-1, 0, 1)]
    return background, shapes


def _row(background: RGB, spans: Sequence[Span]) -> bytes:
    row = bytearray(bytes(background) * WIDTH)
    for x0, x1, colour in spans:
        x0, x1 = max(x0, 0), min(x1, WIDTH)
        if x1 > x0:
            row[x0 * 3:x1 * 3] = bytes(colour) * (x1 - x0)
    return bytes(row)


def png_bytes(background: RGB, shapes: Sequence[Shape]) -> bytes:
    """A 1080 x 1350 RGB PNG of the shapes over the background."""
    rows: List[bytes] = []
    cache: Dict[Tuple[Span, ...], bytes] = {}
    for y in range(HEIGHT):
        spans = tuple(span for shape in shapes for span in shape(y))
        if spans not in cache:
            cache[spans] = b"\x00" + _row(background, spans)
        rows.append(cache[spans])

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


def mock_ad(ad_id: str, concept: str, fmt: str) -> bytes:
    return png_bytes(*mock_shapes(ad_id, concept, fmt))


def acme_ads(csv_path: Path) -> List[Tuple[str, str, str]]:
    """(ad id, concept, format) for every ad in the example export."""
    ads = cm.aggregate_by_ad(cm.load_rows(str(csv_path)))
    return [(str(a["ad_id"]), str(a.get("concept") or ""), str(a.get("format") or "")) for a in ads]


def write_all(csv_path: Path, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for ad_id, concept, fmt in acme_ads(csv_path):
        path = out_dir / ("%s.png" % ad_id)
        path.write_bytes(mock_ad(ad_id, concept, fmt))
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", default=str(ROOT / "examples" / "acme" / "ads_daily.csv"))
    parser.add_argument("--out", default=str(ROOT / "examples" / "acme" / "previews"))
    args = parser.parse_args()
    paths = write_all(Path(args.csv), Path(args.out))
    print("wrote %d previews to %s (largest %.1f KB)" % (len(paths), args.out, max(p.stat().st_size for p in paths) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
