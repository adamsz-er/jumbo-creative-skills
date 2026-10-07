#!/usr/bin/env python3
"""Extract the palette of ad images and describe it for colour direction.

Usage: python3 palette.py image-or-folder [--k 6] [--json]

Uses Pillow (median cut) when it is installed. Without it, PNG files (8-bit
RGB or RGBA, not interlaced) are decoded with the standard library and colours
are bucketed to 4 bits per channel. Any other format without Pillow exits 2.
Set CREATIVE_SKILLS_NO_PILLOW=1 to force the standard-library path. Numbers
describe the image; none of them is a benchmark.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
NO_PILLOW = "install Pillow (pip install pillow) or let your agent describe the colours from the image"
SAMPLE_SIDE = 160  # long side, in pixels, an image is shrunk to before Pillow counts it
# Arbitrary default: a set "shares a look" when more than this share of its images have the
# same dominant colour family. Set your own from how varied your feed should be.
FAMILY_SHARE = 55.0
Pixels = List[Tuple[int, int, int]]


class Unsupported(Exception):
    """The image cannot be read on this machine."""


def _pillow():
    if os.environ.get("CREATIVE_SKILLS_NO_PILLOW"):
        return None
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_png(path: str) -> Tuple[int, int, Pixels]:
    """Decode an 8-bit RGB or RGBA, non-interlaced PNG into (width, height, RGB pixels)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise Unsupported("not a PNG file")
    pos, idat, header = 8, [], None
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 8 + length + 4
    if header is None:
        raise Unsupported("PNG has no header")
    width, height, depth, colour_type, _, _, interlace = header
    if depth != 8 or colour_type not in (2, 6) or interlace:
        raise Unsupported("this PNG is not 8-bit RGB or RGBA without interlacing; " + NO_PILLOW)
    bpp = 3 if colour_type == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = width * bpp
    previous = bytearray(stride)
    pixels: Pixels = []
    for row in range(height):
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                line[i] = (line[i] + _paeth(left, up, corner)) & 255
        previous = line
        for x in range(width):
            if bpp == 4 and line[x * bpp + 3] == 0:
                continue
            pixels.append((line[x * bpp], line[x * bpp + 1], line[x * bpp + 2]))
    return width, height, pixels


def _stdlib_colours(pixels: Pixels, k: int) -> List[Tuple[Tuple[int, int, int], int]]:
    """Bucket to 4 bits per channel; report each bucket by its most common exact colour."""
    buckets: Dict[Tuple[int, int, int], Counter] = {}
    for rgb in pixels:
        buckets.setdefault((rgb[0] >> 4, rgb[1] >> 4, rgb[2] >> 4), Counter())[rgb] += 1
    ranked = sorted(((sum(c.values()), c.most_common(1)[0][0]) for c in buckets.values()),
                    key=lambda item: (-item[0], item[1]))
    return [(rgb, count) for count, rgb in ranked[:k]]


def _pillow_colours(Image, path: str, k: int):
    image = Image.open(path).convert("RGB")
    image.thumbnail((SAMPLE_SIDE, SAMPLE_SIDE))
    pixels = list(getattr(image, "get_flattened_data", image.getdata)())
    quantised = image.quantize(colors=k, method=Image.MEDIANCUT)
    palette = quantised.getpalette()
    counts = sorted(quantised.getcolors(), reverse=True)
    return [(tuple(palette[i * 3:i * 3 + 3]), n) for n, i in counts[:k]], pixels


def hex_of(rgb: Sequence[int]) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def _linear(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: Sequence[int]) -> float:
    r, g, b = (_linear(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rgb(colour) -> Tuple[int, int, int]:
    if isinstance(colour, str):
        value = colour.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(colour)


def contrast_ratio(first, second) -> float:
    """WCAG contrast ratio between two colours (hex strings or RGB tuples), 1.0 to 21.0."""
    a, b = luminance(_rgb(first)), luminance(_rgb(second))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def colour_family(rgb: Sequence[int]) -> str:
    """A coarse family name used to spot a set that shares one look."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    degrees = h * 360
    if v < 0.2:
        return "near-black"
    if s < 0.12:
        return "white" if v > 0.85 else "grey"
    if s < 0.35 and v > 0.7 and 16 <= degrees < 68:
        return "neutral-warm (cream, sand, beige)"
    names = ((16, "red"), (42, "orange"), (68, "yellow"), (160, "green"), (250, "blue"),
             (330, "purple"), (361, "red"))
    return next(name for limit, name in names if degrees < limit)


def _stats(pixels: Pixels) -> Dict[str, Optional[float]]:
    if not pixels:
        return {"brightness": None, "saturation": None, "warm_share": None, "cool_share": None,
                "contrast_spread": None}
    n = len(pixels)
    lum = sorted(luminance(p) for p in pixels)
    hsv = [colorsys.rgb_to_hsv(*(c / 255 for c in p)) for p in pixels]
    coloured = [h * 360 for h, s, v in hsv if s >= 0.12 and v >= 0.2]
    warm = sum(1 for d in coloured if d < 68 or d >= 330)
    judged = len(coloured) or None
    return {"brightness": sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in pixels) / n / 255 * 100,
            "saturation": sum(s for _, s, _ in hsv) / n * 100,
            "warm_share": warm / judged * 100 if judged else None,
            "cool_share": (len(coloured) - warm) / judged * 100 if judged else None,
            "contrast_spread": (lum[int(0.95 * (n - 1))] - lum[int(0.05 * (n - 1))]) * 100}


def analyse_image(path: str, k: int = 6) -> Dict[str, Any]:
    """Top colours with shares, plus brightness, saturation, warm/cool balance and contrast."""
    Image = _pillow()
    if Image is not None:
        counted, pixels = _pillow_colours(Image, path, k)
        total = sum(n for _, n in counted)
        engine = "Pillow median cut"
    else:
        if Path(path).suffix.lower() != ".png":
            raise Unsupported(NO_PILLOW)
        _, _, pixels = read_png(path)
        counted = _stdlib_colours(pixels, k)
        total = len(pixels)
        engine = "standard-library PNG decoder, 4-bit buckets"
    if not total:
        raise Unsupported("the image has no visible pixels")
    colours = [{"hex": hex_of(rgb), "share": n / total * 100, "family": colour_family(rgb)}
               for rgb, n in counted]
    result: Dict[str, Any] = {"path": str(path), "engine": engine, "colours": colours}
    result.update(_stats(pixels))
    result["text_contrast_ratio"] = (contrast_ratio(colours[0]["hex"], colours[1]["hex"])
                                     if len(colours) > 1 else None)
    return result


def find_images(target: str) -> List[str]:
    path = Path(target)
    if path.is_dir():
        return sorted(str(p) for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    return [str(path)]


def shared_family(results: Sequence[Dict[str, Any]]) -> Optional[Tuple[str, int]]:
    """The dominant-colour family shared by most images in a set, if one is."""
    if len(results) < 2:
        return None
    count = Counter(r["colours"][0]["family"] for r in results if r["colours"])
    family, hits = count.most_common(1)[0]
    return (family, hits) if hits / len(results) * 100 > FAMILY_SHARE else None


def _n(value: Optional[float], digits: int = 0) -> str:
    return "n/a" if value is None else "%.*f" % (digits, value)


def render(results: Sequence[Dict[str, Any]]) -> str:
    out = ["Basis: colours counted from each image's own pixels (%s). Shares are of counted pixels; "
           "brightness, saturation and contrast spread are 0-100 scales on that image; warm and cool are "
           "shares of its coloured pixels (greys excluded)." % ", ".join(sorted({r["engine"] for r in results})),
           ""]
    for r in results:
        out.append(r["path"])
        out.append("  colours: " + ", ".join("%s %.0f%%" % (c["hex"], c["share"]) for c in r["colours"]))
        out.append("  brightness %s, saturation %s, warm %s%% / cool %s%%, contrast spread %s" % (
            _n(r["brightness"]), _n(r["saturation"]), _n(r["warm_share"]), _n(r["cool_share"]),
            _n(r["contrast_spread"])))
        ratio = r["text_contrast_ratio"]
        out.append("  text legibility: the two most common colours have a WCAG contrast ratio of %s:1" %
                   ("n/a (only one colour found)" if ratio is None else "%.1f" % ratio))
    shared = shared_family(results)
    if shared:
        out += ["", "Set check: %d of %d images share a dominant colour family (%s). In the feed they will read "
                "as one look: vary the background family across the set." % (shared[1], len(results), shared[0])]
    elif len(results) > 1:
        out += ["", "Set check: no single dominant colour family covers most of the %d images." % len(results)]
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract the palette of ad images.")
    parser.add_argument("path", help="an image, or a folder of images")
    parser.add_argument("--k", type=int, default=6, help="how many colours to report (default 6)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    results = []
    try:
        for image in find_images(args.path):
            results.append(analyse_image(image, args.k))
    except (Unsupported, OSError, ValueError, zlib.error, struct.error) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not results:
        print("error: no images found at %s" % args.path, file=sys.stderr)
        return 2
    if args.json:
        shared = shared_family(results)
        print(json.dumps({"images": results, "shared_family": shared[0] if shared else None}, indent=2))
    else:
        print(render(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
