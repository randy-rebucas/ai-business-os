"""Untrusted logo uploads: sniff the real format, refuse oversized or decompression-bomb images, re-encode to a clean
PNG (no metadata, no trailing bytes, no polyglot) and extract the visible palette. SVG is refused: it is a document
that can carry script, and rasterising it safely needs another dependency."""

import io
from collections import Counter

from PIL import Image, UnidentifiedImageError

from abos.branding.colors import rgb_to_hex
from abos.core.errors import AppError

MAX_BYTES = 1024 * 1024
MAX_SIDE = 4096
STORED_SIDE = 512
ALLOWED = {"PNG", "JPEG", "WEBP"}
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")


def _bad(message: str) -> AppError:
    return AppError(422, "invalid_logo", message)


def process(data: bytes) -> tuple[bytes, int, int, list[dict]]:
    """Returns (png_bytes, width, height, palette) where palette = [{"hex", "share"}] over opaque pixels."""
    if len(data) > MAX_BYTES:
        raise _bad("The logo must be 1 MB or smaller.")
    if not data.startswith(_MAGIC) or (data.startswith(b"RIFF") and data[8:12] != b"WEBP"):
        raise _bad("Upload a PNG, JPEG or WebP image (SVG isn't accepted).")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED:
                raise _bad("Upload a PNG, JPEG or WebP image (SVG isn't accepted).")
            if max(probe.size) > MAX_SIDE:
                raise _bad(f"The logo must be at most {MAX_SIDE} pixels on its longest side.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            rgba = img.convert("RGBA")
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise _bad("The image could not be read.") from exc
    bbox = rgba.getbbox()  # trim fully transparent margins
    if bbox:
        rgba = rgba.crop(bbox)
    rgba.thumbnail((STORED_SIDE, STORED_SIDE))
    out = io.BytesIO()
    rgba.save(out, format="PNG", optimize=True)  # fresh encode: only pixels survive
    return out.getvalue(), rgba.width, rgba.height, palette(rgba)


def palette(rgba: Image.Image, colors: int = 8) -> list[dict]:
    small = rgba.copy()
    small.thumbnail((96, 96))
    pixels = [p[:3] for p in small.get_flattened_data() if p[3] >= 128]
    if not pixels:
        return []
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quant = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    lut = quant.getpalette() or []
    counts = Counter(quant.get_flattened_data())
    total = sum(counts.values())
    return [{"hex": rgb_to_hex(tuple(lut[i * 3:i * 3 + 3])), "share": round(n / total, 4)}
            for i, n in counts.most_common()]
