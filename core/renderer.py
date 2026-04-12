"""
translated
translated，translatedmodetranslated

STOIC, ROAST, ZEN, FITNESS, POETRY translated JSON translated (json_renderer.py)。
translated Python translatedmode。
"""

from __future__ import annotations

import io
from PIL import Image

from .config import SCREEN_WIDTH, SCREEN_HEIGHT
from .patterns import render_error

__all__ = [
    "render_error",
    "render_mode",
    "image_to_bmp_bytes",
    "image_to_png_bytes",
    "image_to_raw_2bpp",
]


def render_mode(
    persona: str,
    content: dict,
    *,
    date_str: str,
    weather_str: str,
    battery_pct: float,
    weather_code: int = -1,
    date_ctx: dict | None = None,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
) -> Image.Image:
    """Legacy dispatcher retained for backward compatibility.

    All production modes are JSON-defined and rendered by json_renderer.
    """
    raise ValueError(
        f"Unknown builtin persona '{persona}'. "
        "JSON-defined modes should be routed through json_renderer."
    )


def image_to_bmp_bytes(img: Image.Image) -> bytes:
    """translated BMP translated"""
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def image_to_raw_2bpp(img: Image.Image) -> bytes:
    """Convert image to raw 2bpp packed bytes for 4-color e-ink.

    Pixel mapping: 0=black, 1=white, 2=yellow, 3=red.
    4 pixels packed per byte, MSB first (bits 7-6 = first pixel).
    Row-major, top to bottom.
    """
    if img.mode == "1":
        pixels = img.load()
        w, h = img.size
        out = bytearray(w * h // 4)
        idx = 0
        for y in range(h):
            for x in range(0, w, 4):
                packed = 0
                for bit in range(4):
                    px = x + bit
                    is_white = pixels[px, y] if px < w else 1
                    color = 0x01 if is_white else 0x00
                    packed |= color << (6 - bit * 2)
                out[idx] = packed
                idx += 1
        return bytes(out)

    if img.mode != "P":
        img = img.convert("P")
    pixels = img.load()
    w, h = img.size
    out = bytearray(w * h // 4)
    idx = 0
    for y in range(h):
        for x in range(0, w, 4):
            packed = 0
            for bit in range(4):
                px = x + bit
                color = (pixels[px, y] & 0x03) if px < w else 0x01
                packed |= color << (6 - bit * 2)
            out[idx] = packed
            idx += 1
    return bytes(out)


def image_to_png_bytes(img: Image.Image) -> bytes:
    """translated PNG translated"""
    if img.mode == "1":
        img = img.convert("L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
