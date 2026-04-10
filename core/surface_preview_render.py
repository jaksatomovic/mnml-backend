"""Surface preview: mosaic tiles at 400×300, each tile renders a real mode via generate_and_render."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PIL import Image, ImageDraw

from core.context import extract_location_settings, get_date_context, get_weather
from core.patterns.utils import apply_text_fontmode, draw_footer, draw_status_bar, load_font
from core.pipeline import generate_and_render
from core.surface_engine import build_surface_render_payload

logger = logging.getLogger(__name__)

_POSITION_ORDER = ("top", "middle", "bottom")

_MOSAIC_PRESETS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "morning": (
        (0.0, 0.0, 0.48, 0.52),
        (0.52, 0.0, 0.48, 0.52),
        (0.0, 0.56, 1.0, 0.44),
    ),
    "work": (
        (0.0, 0.0, 0.58, 0.62),
        (0.62, 0.0, 0.38, 0.30),
        (0.0, 0.66, 1.0, 0.34),
    ),
    "home": (
        (0.0, 0.0, 0.36, 0.34),
        (0.40, 0.0, 0.60, 0.58),
        (0.0, 0.62, 1.0, 0.38),
    ),
}

_GENERIC_THREE: tuple[tuple[float, float, float, float], ...] = (
    (0.0, 0.0, 0.48, 0.52),
    (0.52, 0.0, 0.48, 0.52),
    (0.0, 0.56, 1.0, 0.44),
)


def _preset_for_surface(surface_id: str) -> tuple[tuple[float, float, float, float], ...]:
    sid = (surface_id or "").strip().lower()
    return _MOSAIC_PRESETS.get(sid, _GENERIC_THREE)


def _body_box(screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
    """Mosaic area inside padded margins; per-tile renders omit mode chrome."""
    pad = max(5, min(10, screen_w // 48))
    return (pad, pad, screen_w - pad, screen_h - pad)


def _frac_to_rect(
    body: tuple[int, int, int, int],
    frac: tuple[float, float, float, float],
    gutter: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = body
    bw, bh = x1 - x0, y1 - y0
    l, t, w, h = frac
    gx = int(gutter * 0.4)
    px0 = x0 + int(l * bw) + (gx if l > 0.01 else 0)
    py0 = y0 + int(t * bh) + (gx if t > 0.01 else 0)
    px1 = x0 + int((l + w) * bw) - (gx if l + w < 0.99 else 0)
    py1 = y0 + int((t + h) * bh) - (gx if t + h < 0.99 else 0)
    px0 = max(x0, min(px0, x1 - 2))
    py0 = max(y0, min(py0, y1 - 2))
    px1 = max(px0 + 8, min(px1, x1))
    py1 = max(py0 + 8, min(py1, y1))
    return (px0, py0, px1, py1)


def _legacy_type_to_mode(wtype: str) -> str:
    m = {
        "weather": "WEATHER",
        "calendar": "CALENDAR",
        "text": "DAILY",
        "tasks": "BRIEFING",
        "github": "BRIEFING",
        "custom_api": "DAILY",
    }
    return m.get(wtype.strip().lower(), "STOIC")


def _resolve_mode_for_block(block: dict[str, Any] | None) -> str:
    if not block:
        return "STOIC"
    raw = block.get("mode") or block.get("mode_id") or block.get("persona")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return _legacy_type_to_mode(str(block.get("type") or "text"))


def _to_grayscale(img: Image.Image) -> Image.Image:
    if img.mode == "L":
        return img
    if img.mode == "1":
        return img.convert("L")
    if img.mode == "P":
        return img.convert("L")
    return img.convert("L")


def _fit_tile(tile: Image.Image, tw: int, th: int) -> Image.Image:
    tile = _to_grayscale(tile)
    if tile.size == (tw, th):
        return tile
    return tile.resize((tw, th), Image.Resampling.LANCZOS)


def _draw_surface_chrome(
    img: Image.Image,
    *,
    date_ctx: dict,
    weather: dict,
    battery_pct: float,
    screen_w: int,
    screen_h: int,
    language: str,
    surface_label: str,
) -> None:
    """One status bar + footer for the full surface (tiles are body-only)."""
    from core.pipeline import _format_date_str

    date_str = _format_date_str(date_ctx, language)
    time_str = str(date_ctx.get("time_str", "") or "")
    wstr = str(weather.get("weather_str", "") or "")
    wcode = int(weather.get("weather_code", -1) or -1)
    draw = ImageDraw.Draw(img)
    apply_text_fontmode(draw)
    draw_status_bar(
        draw,
        img,
        date_str,
        wstr,
        int(battery_pct),
        wcode,
        1,
        False,
        time_str,
        screen_w,
        screen_h,
        2,
        language,
    )
    label = (surface_label or "SURFACE").strip().upper() or "SURFACE"
    draw_footer(
        draw,
        img,
        label,
        "InkSight",
        mode_id="SURFACE",
        weather_code=None,
        screen_w=screen_w,
        screen_h=screen_h,
        colors=2,
        time_str=time_str,
    )


def _draw_error_tile(tw: int, th: int, msg: str) -> Image.Image:
    im = Image.new("L", (max(1, tw), max(1, th)), 255)
    d = ImageDraw.Draw(im)
    apply_text_fontmode(d)
    f = load_font("noto_serif_light", max(9, min(12, tw // 12)))
    d.text((4, 4), msg[:80], fill=0, font=f)
    return im


async def render_surface_preview_image(
    surface: dict[str, Any],
    *,
    screen_w: int,
    screen_h: int,
    device_config: dict[str, Any] | None = None,
    mac: str = "",
) -> Image.Image:
    """Composite each slot with a real mode render at slot pixel size (matches mosaic layout)."""
    normalized = dict(surface)
    normalized["type"] = "surface"
    payload = build_surface_render_payload(normalized, {"type": "preview"})
    layout = payload.get("layout") if isinstance(payload.get("layout"), list) else []
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    loc = extract_location_settings(device_config if isinstance(device_config, dict) else None)
    tz = ""
    if isinstance(device_config, dict):
        tz = str(device_config.get("timezone") or device_config.get("timeZone") or "").strip()

    date_ctx = await get_date_context(timezone_name=tz)
    weather = await get_weather(lat=loc.get("lat"), lon=loc.get("lon"), city=loc.get("city"))
    battery_pct = 100.0

    cfg = device_config if isinstance(device_config, dict) else None
    surface_id = str(meta.get("surface") or normalized.get("id") or "").strip()

    img = Image.new("L", (screen_w, screen_h), 255)

    body = _body_box(screen_w, screen_h)
    gutter = max(4, screen_w // 90)

    preset = _preset_for_surface(surface_id.lower())
    items: list[dict[str, Any] | None] = []
    for pos in _POSITION_ORDER:
        raw = next((x for x in layout if isinstance(x, dict) and str(x.get("position") or "") == pos), None)
        items.append(raw if isinstance(raw, dict) else None)

    async def _one_tile(persona: str, rect: tuple[int, int, int, int]) -> Image.Image:
        rx0, ry0, rx1, ry1 = rect
        tw = max(96, rx1 - rx0)
        th = max(72, ry1 - ry0)
        try:
            tile, _c = await generate_and_render(
                persona,
                cfg,
                date_ctx,
                weather,
                battery_pct,
                screen_w=tw,
                screen_h=th,
                mac=mac or "",
                colors=2,
                omit_chrome=True,
            )
            return _fit_tile(tile, tw, th)
        except Exception:
            logger.warning("[surface_preview] tile render failed persona=%s", persona, exc_info=True)
            return _draw_error_tile(tw, th, persona[:10])

    rects: list[tuple[int, int, int, int]] = []
    personas: list[str] = []
    for i in range(min(len(items), len(preset))):
        personas.append(_resolve_mode_for_block(items[i]))
        rects.append(_frac_to_rect(body, preset[i], gutter))

    tiles = await asyncio.gather(*[_one_tile(personas[i], rects[i]) for i in range(len(personas))])

    for i, rect in enumerate(rects):
        rx0, ry0, rx1, ry1 = rect
        tw, th = rx1 - rx0, ry1 - ry0
        tile = tiles[i]
        tile = _fit_tile(tile, tw, th)
        img.paste(tile, (rx0, ry0))

    lang = "zh"
    if isinstance(cfg, dict):
        lang = str(cfg.get("mode_language") or cfg.get("modeLanguage") or "zh").strip() or "zh"
    title = (
        str(meta.get("title") or normalized.get("name") or surface_id or "Surface").strip()
        or "Surface"
    )
    _draw_surface_chrome(
        img,
        date_ctx=date_ctx,
        weather=weather,
        battery_pct=battery_pct,
        screen_w=screen_w,
        screen_h=screen_h,
        language=lang,
        surface_label=title,
    )

    return img.point(lambda p: 255 if p > 135 else 0).convert("1")
