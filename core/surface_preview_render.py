"""Surface preview: mosaic tiles at 400×300, each tile renders a real mode via generate_and_render."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PIL import Image, ImageDraw

from core.context import extract_location_settings, get_date_context, get_weather
from core.patterns.utils import (
    apply_text_fontmode,
    draw_status_bar,
    load_font,
    get_mode_icon,
    get_weather_icon,
    paste_icon_onto,
)
from core.pipeline import generate_and_render
from core.render_tiers import surface_mosaic_inner_rect
from core.surface_engine import build_surface_render_payload
from core.surface_grid import (
    body_slot_rects_px,
    cell_rect_px,
    cell_slot_occupy_ids,
    grid_dimensions,
    parse_surface_grid,
    resolve_slot_widget_block,
    sort_slots_reading_order,
    validate_slots_for_grid,
)

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


def _cell_slot_id_equal(a: str | None, b: str | None) -> bool:
    return (a or "") == (b or "")


def _draw_slot_boundary_dashed(
    draw: ImageDraw.ImageDraw,
    body: tuple[int, int, int, int],
    grid: dict,
    slots_sorted: list[dict[str, Any]],
    *,
    outline: int = 0,
    dash_len: int = 3,
    gap_len: int = 3,
) -> None:
    """Dashed lines only where two adjacent cells belong to different slots (follows real layout)."""
    cols, rows, _, _ = grid_dimensions(grid)
    if cols < 2 and rows < 2:
        return
    occ = cell_slot_occupy_ids(slots_sorted, columns=cols, rows=rows)

    # Vertical: boundary between columns c-1 and c
    for c in range(1, cols):
        ry = 0
        while ry < rows:
            if _cell_slot_id_equal(occ[ry][c - 1], occ[ry][c]):
                ry += 1
                continue
            r0 = ry
            while ry < rows and not _cell_slot_id_equal(occ[ry][c - 1], occ[ry][c]):
                ry += 1
            r1 = ry - 1
            top = cell_rect_px(body, grid, c - 1, r0)[1]
            bot = cell_rect_px(body, grid, c - 1, r1)[3]
            lc = cell_rect_px(body, grid, c - 1, r0)
            rc = cell_rect_px(body, grid, c, r0)
            xv = (lc[2] + rc[0]) // 2
            draw_dashed_line_vertical(
                draw, xv, top, bot, fill=outline, width=1, dash_len=dash_len, gap_len=gap_len
            )

    # Horizontal: boundary between rows r-1 and r
    for r in range(1, rows):
        rx = 0
        while rx < cols:
            if _cell_slot_id_equal(occ[r - 1][rx], occ[r][rx]):
                rx += 1
                continue
            c0 = rx
            while rx < cols and not _cell_slot_id_equal(occ[r - 1][rx], occ[r][rx]):
                rx += 1
            c1 = rx - 1
            top_cell = cell_rect_px(body, grid, c0, r - 1)
            bot_cell = cell_rect_px(body, grid, c0, r)
            yh = (top_cell[3] + bot_cell[1]) // 2
            x_left = cell_rect_px(body, grid, c0, r - 1)[0]
            x_right = cell_rect_px(body, grid, c1, r - 1)[2]
            draw_dashed_line(
                draw,
                (x_left, yh),
                (x_right, yh),
                fill=outline,
                width=1,
                dash_len=dash_len,
                gap_len=gap_len,
            )


def _draw_surface_chrome(
    img: Image.Image,
    *,
    date_ctx: dict,
    weather: dict,
    battery_pct: float,
    screen_w: int,
    screen_h: int,
    language: str,
    suppress_center_weather: bool,
) -> None:
    """One status bar for the full surface (tiles have local chrome)."""
    from core.pipeline import _format_date_str

    date_str = _format_date_str(date_ctx, language)
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
        screen_w,
        screen_h,
        2,
        language,
        suppress_center_weather=suppress_center_weather,
    )


def _draw_error_tile(tw: int, th: int, msg: str) -> Image.Image:
    im = Image.new("L", (max(1, tw), max(1, th)), 255)
    d = ImageDraw.Draw(im)
    apply_text_fontmode(d)
    f = load_font("noto_serif_light", max(9, min(12, tw // 12)))
    d.text((4, 4), msg[:80], fill=0, font=f)
    return im


def _draw_dotted_line_h(
    draw: ImageDraw.ImageDraw,
    x0: int,
    x1: int,
    y: int,
    *,
    step: int = 4,
    fill: int = 0,
) -> None:
    for x in range(x0, x1 + 1, step):
        draw.point((x, y), fill=fill)


def _draw_dotted_line_v(
    draw: ImageDraw.ImageDraw,
    x: int,
    y0: int,
    y1: int,
    *,
    step: int = 4,
    fill: int = 0,
) -> None:
    for y in range(y0, y1 + 1, step):
        draw.point((x, y), fill=fill)


def _draw_dotted_top_arc(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    start_deg: int,
    end_deg: int,
    *,
    step_deg: int = 12,
    fill: int = 0,
) -> None:
    import math

    x0, y0, x1, y1 = bbox
    rx = (x1 - x0) / 2.0
    ry = (y1 - y0) / 2.0
    cx = x0 + rx
    cy = y0 + ry
    for deg in range(start_deg, end_deg + 1, step_deg):
        rad = math.radians(deg)
        x = int(round(cx + rx * math.cos(rad)))
        y = int(round(cy + ry * math.sin(rad)))
        draw.point((x, y), fill=fill)


def _draw_slot_chrome(
    img: Image.Image,
    rect: tuple[int, int, int, int],
    mode_label: str,
) -> None:
    x0, y0, x1, y1 = rect
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    if w < 32 or h < 28:
        return

    draw = ImageDraw.Draw(img)
    apply_text_fontmode(draw)

    r = 3
    left = x0
    right = x1 - 1
    top = y0
    bottom = y1 - 1

    footer_h = min(22, max(14, int(h * 0.14)))
    footer_top = max(top + 8, bottom - footer_h + 1)
    body_bottom = max(top + r + 2, footer_top - 1)

    # Dotted border belongs to content area only (stops before footer).
    _draw_dotted_line_h(draw, left + r, right - r, top, step=4, fill=0)
    _draw_dotted_line_v(draw, left, top + r, body_bottom, step=4, fill=0)
    _draw_dotted_line_v(draw, right, top + r, body_bottom, step=4, fill=0)
    _draw_dotted_top_arc(draw, (left, top, left + 2 * r, top + 2 * r), 180, 270, fill=0)
    _draw_dotted_top_arc(draw, (right - 2 * r, top, right, top + 2 * r), 270, 360, fill=0)

    # Footer: black bar with rounded bottom corners only.
    fr = 3
    draw.rounded_rectangle([left, footer_top + 1, right, bottom], radius=fr, fill=0)
    # Square the top edge back so only bottom corners remain rounded.
    draw.rectangle([left, footer_top + 1, right, footer_top + fr], fill=0)
    _draw_dotted_line_h(draw, left + 3, right - 3, footer_top, step=3, fill=255)

    font = load_font("inter_medium", max(9, min(12, int(w / 16))))
    raw_label = (mode_label or "WIDGET").strip()
    label = raw_label.replace("_", " ").lower().title()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    icon = get_mode_icon(raw_label.upper())
    if icon is None and raw_label.upper() == "WEATHER":
        # Surface footer has no per-tile weather code; use a generic weather glyph.
        icon = get_weather_icon(1)
    icon_size = 12
    icon_x = left + 8
    text_left_padding = 8
    if icon:
        if icon.size != (icon_size, icon_size):
            icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        text_left_padding = icon_size + 6
    tx = left + 8 + text_left_padding
    if tw > w - (tx - left) - 8:
        while label and tw > w - (tx - left) - 10:
            label = label[:-1]
            bbox = draw.textbbox((0, 0), f"{label}...", font=font)
            tw = bbox[2] - bbox[0]
        label = f"{label}..." if label else "..."
    text_h = bbox[3] - bbox[1]
    footer_inner_top = footer_top + 1
    footer_inner_bottom = bottom
    footer_inner_h = max(1, footer_inner_bottom - footer_inner_top + 1)
    ty = footer_inner_top + max(0, (footer_inner_h - text_h) // 2)
    if icon:
        icon_y = footer_inner_top + max(0, (footer_inner_h - icon_size) // 2)
        paste_icon_onto(img, icon, (icon_x, icon_y), fill=255)
    draw.text((tx, ty), label, fill=255, font=font)


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

    # Tiles only in the band between where surface status bar & footer will draw
    body = surface_mosaic_inner_rect(screen_w, screen_h)
    gutter = max(4, screen_w // 90)

    grid, slot_defs = parse_surface_grid(normalized)
    use_grid = False
    sorted_slots: list[dict[str, Any]] = []
    if grid and slot_defs:
        cols, rows, _, _ = grid_dimensions(grid)
        ok, _err = validate_slots_for_grid(slot_defs, columns=cols, rows=rows)
        if ok:
            use_grid = True
            sorted_slots = sort_slots_reading_order(slot_defs)

    preset = _preset_for_surface(surface_id.lower())
    items: list[dict[str, Any] | None] = []
    if use_grid:
        blocks = [x for x in layout if isinstance(x, dict)]
        for i, _slot in enumerate(sorted_slots):
            blk = resolve_slot_widget_block(_slot, blocks, i)
            items.append(blk if isinstance(blk, dict) else None)
    else:
        for pos in _POSITION_ORDER:
            raw = next(
                (x for x in layout if isinstance(x, dict) and str(x.get("position") or "") == pos),
                None,
            )
            items.append(raw if isinstance(raw, dict) else None)

    async def _one_tile(
        persona: str,
        rect: tuple[int, int, int, int],
        slot_type: str | None,
    ) -> Image.Image:
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
                slot_type=slot_type,
            )
            return _fit_tile(tile, tw, th)
        except Exception:
            logger.warning("[surface_preview] tile render failed persona=%s", persona, exc_info=True)
            return _draw_error_tile(tw, th, persona[:10])

    rects: list[tuple[int, int, int, int]] = []
    personas: list[str] = []
    slot_types: list[str | None] = []
    if use_grid:
        rects = body_slot_rects_px(body, grid, slot_defs)
        for i in range(len(rects)):
            personas.append(_resolve_mode_for_block(items[i] if i < len(items) else None))
            st = str(sorted_slots[i].get("slot_type") or "").strip().upper() or None
            slot_types.append(st)
    else:
        for i in range(min(len(items), len(preset))):
            personas.append(_resolve_mode_for_block(items[i]))
            rects.append(_frac_to_rect(body, preset[i], gutter))
            slot_types.append(None)

    tiles = await asyncio.gather(
        *[_one_tile(personas[i], rects[i], slot_types[i]) for i in range(len(personas))]
    )

    for i, rect in enumerate(rects):
        rx0, ry0, rx1, ry1 = rect
        tw, th = rx1 - rx0, ry1 - ry0
        tile = tiles[i]
        tile = _fit_tile(tile, tw, th)
        img.paste(tile, (rx0, ry0))
        _draw_slot_chrome(img, rect, personas[i])

    # Grid separators between cells are intentionally omitted.
    # Each tile now draws its own border chrome.

    lang = "zh"
    if isinstance(cfg, dict):
        lang = str(cfg.get("mode_language") or cfg.get("modeLanguage") or "zh").strip() or "zh"
    has_weather_tile = any((p or "").upper() == "WEATHER" for p in personas)
    _draw_surface_chrome(
        img,
        date_ctx=date_ctx,
        weather=weather,
        battery_pct=battery_pct,
        screen_w=screen_w,
        screen_h=screen_h,
        language=lang,
        suppress_center_weather=has_weather_tile,
    )

    # 1-bit threshold: L≤135 → black. Footer uses L=0 (bar) and L>135 (white text/icons).
    return img.point(lambda p: 255 if p > 135 else 0).convert("1")
