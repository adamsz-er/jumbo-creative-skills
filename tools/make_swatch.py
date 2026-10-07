#!/usr/bin/env python3
"""Write examples/acme/swatch.png: flat colour blocks, not a real ad.

Usage: python3 tools/make_swatch.py [--out examples/acme/swatch.png]

Standard library only (zlib + struct). The colours are Acme's two brand
colours plus three invented accents. Block widths are 36, 24, 18, 13 and 9
percent of a 100 pixel wide image, so the shares are known exactly.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

WIDTH, HEIGHT = 100, 50
BLOCKS = (
    ("#2F4A3A", 36),
    ("#E6DCC8", 24),
    ("#B5532A", 18),
    ("#3B4A5A", 13),
    ("#D9A441", 9),
)


def _rgb(hex_colour):
    value = hex_colour.lstrip("#")
    return bytes(int(value[i:i + 2], 16) for i in (0, 2, 4))


def png_bytes():
    row = b"".join(_rgb(colour) * width for colour, width in BLOCKS)
    assert len(row) == WIDTH * 3
    raw = b"".join(b"\x00" + row for _ in range(HEIGHT))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(root / "examples" / "acme" / "swatch.png"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes())
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
