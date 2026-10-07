"""Ad preview embedding for the dashboard. Standard library only.

`--previews DIR` holds rendered previews and `--thumbs DIR` small thumbnails or
video stills, both named `<ad_id>.<ext>`. Each image is sniffed from its first
bytes, size-capped, charged against a page budget and embedded as a data URI, so
the page never depends on a URL that expires. Nothing here reads a URL.
"""
from __future__ import annotations

import base64
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_MAX_KB = 240  # arbitrary default: a rendered mobile preview is usually well under this
DEFAULT_BUDGET_KB = 3600  # arbitrary default: keeps the file easy to email or open
NO_PREVIEW = "no preview fetched"
UNRECOGNISED = "unrecognised image type"
TOO_LARGE = "too large"
BUDGET = "size budget reached"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
FALLBACK_SIZE = (300, 300)


def sniff(data: bytes) -> Optional[str]:
    """The image's MIME type from its magic bytes, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def dimensions(data: bytes, mime: str) -> Tuple[int, int]:
    """Pixel width and height read from the file header; FALLBACK_SIZE when the header is not readable."""
    try:
        if mime == "image/png":
            return struct.unpack(">II", data[16:24])
        if mime == "image/gif":
            return struct.unpack("<HH", data[6:10])
        if mime == "image/jpeg":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height, width = struct.unpack(">HH", data[i + 5:i + 9])
                    return width, height
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        if mime == "image/webp":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b"VP8 ":
                width, height = struct.unpack("<HH", data[26:30])
                return width & 0x3FFF, height & 0x3FFF
    except (struct.error, IndexError):
        pass
    return FALLBACK_SIZE


class Previews:
    """Resolves each ad to a preview, a thumbnail or a labelled placeholder, within a size budget.

    Each ad is resolved once and its image embedded once, as a symbol every card of that ad points at, so an ad
    that appears in three panels costs its bytes one time and counts one time in the footer.
    """

    HEAD = 32

    def __init__(self, preview_dir: Optional[str] = None, thumb_dir: Optional[str] = None,
                 max_kb: int = DEFAULT_MAX_KB, budget_kb: int = DEFAULT_BUDGET_KB) -> None:
        self.preview_dir = Path(preview_dir) if preview_dir else None
        self.thumb_dir = Path(thumb_dir) if thumb_dir else None
        self.max_kb, self.budget_kb = max_kb, budget_kb
        self.total_bytes = 0
        self.kinds: Counter = Counter()
        self.reasons: Counter = Counter()
        self.symbols: Dict[str, Dict[str, object]] = {}
        self._resolved: Dict[str, Dict[str, object]] = {}

    def _find(self, directory: Optional[Path], ad_id: str) -> Optional[Path]:
        if directory is None or not directory.is_dir() or not _SAFE_ID.match(ad_id):
            return None
        return next((p for p in sorted(directory.glob(ad_id + ".*")) if p.is_file()), None)

    def _load(self, path: Path) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
        size = path.stat().st_size
        if size > self.max_kb * 1024:
            return None, TOO_LARGE
        with open(path, "rb") as handle:
            mime = sniff(handle.read(self.HEAD))
            if mime is None:
                return None, UNRECOGNISED
            if self.total_bytes + size > self.budget_kb * 1024:
                return None, BUDGET
            handle.seek(0)
            data = handle.read()
        self.total_bytes += len(data)
        width, height = dimensions(data, mime)
        return {"uri": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii")), "width": width, "height": height}, None

    def resolve(self, ad_id: Optional[str]) -> Dict[str, object]:
        """{"kind": "preview"|"thumbnail"|"placeholder", "symbol", "width", "height", "reason"} for one ad, cached."""
        key = str(ad_id or "")
        if key in self._resolved:
            return self._resolved[key]
        reason = None
        found_image: Dict[str, object] = {}
        for kind, directory in (("preview", self.preview_dir), ("thumbnail", self.thumb_dir)):
            found = self._find(directory, key)
            if found is None:
                continue
            image, why = self._load(found)
            if image:
                self.kinds[kind] += 1
                self.symbols[key] = image
                found_image = dict(image, kind=kind, symbol="pv-" + key, reason=None)
                break
            reason = reason or why
        if not found_image:
            reason = reason or NO_PREVIEW
            self.kinds["placeholder"] += 1
            self.reasons[reason] += 1
            found_image = {"kind": "placeholder", "symbol": None, "width": FALLBACK_SIZE[0], "height": FALLBACK_SIZE[1], "reason": reason}
        self._resolved[key] = found_image
        return found_image

    def embed(self, ad_id: Optional[str]) -> Optional[str]:
        """The ad's image as a data URI, or None when it falls back to the placeholder."""
        self.resolve(ad_id)
        image = self.symbols.get(str(ad_id or ""))
        return image["uri"] if image else None

    def sprite(self) -> str:
        """One zero-size inline SVG holding every embedded image once; cards reference it with <use>."""
        if not self.symbols:
            return ""
        items = "".join('<symbol id="pv-%s" viewBox="0 0 %d %d"><image href="%s" width="%d" height="%d"/></symbol>'
                        % (key, img["width"], img["height"], img["uri"], img["width"], img["height"]) for key, img in sorted(self.symbols.items()))
        return '<svg class="sprite" aria-hidden="true" width="0" height="0" focusable="false">%s</svg>' % items

    def summary(self) -> str:
        """The footer sentence: counts by kind (one per ad), each placeholder reason, and the embedded size."""
        reasons = ", ".join("%s: %d" % (name, n) for name, n in sorted(self.reasons.items())) or "none"
        return ("Ad images: previews embedded %d, thumbnails used %d, placeholders %d (reasons: %s), %.1f KB embedded in total, each image once."
                % (self.kinds["preview"], self.kinds["thumbnail"], self.kinds["placeholder"], reasons, self.total_bytes / 1024))
