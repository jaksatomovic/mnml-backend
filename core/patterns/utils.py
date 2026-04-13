"""
translated
translatedmodetranslated
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
from ..config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    EINK_BACKGROUND,
    EINK_FOREGROUND,
    EINK_COLOR_NAME_MAP,
    EINK_COLOR_AVAILABILITY,
    WEATHER_ICON_MAP,
    ICON_SIZES,
    FONTS,
    FONT_SIZES,
)

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")
TRUETYPE_DIR = os.path.join(FONTS_DIR, "truetype")
BITMAP_DIR = os.path.join(FONTS_DIR, "bitmap")
ICONS_DIR = os.path.join(FONTS_DIR, "icons")

SCREEN_W = SCREEN_WIDTH
SCREEN_H = SCREEN_HEIGHT
EINK_BG = EINK_BACKGROUND
EINK_FG = EINK_FOREGROUND


def paste_icon_onto(target: Image.Image, icon: Image.Image, pos: tuple[int, int], fill: int = EINK_FG) -> None:
    """Paste a 1-bit icon handling palette mode transparency."""
    if target.mode == "P":
        mask = icon.convert("L").point(lambda p: 255 - p)
        target.paste(fill, pos, mask)
    elif target.mode == "L":
        mask = icon.convert("L").point(lambda p: 255 - p)
        target.paste(fill, pos, mask)
    else:
        target.paste(icon, pos)

_font_warned: set[str] = set()
_bitmap_warned: set[str] = set()
_font_engine = os.getenv("INKSIGHT_FONT_ENGINE", "bitmap").strip().lower()
_force_bitmap = _font_engine in {"bitmap", "pixel", "pil"}
_fontmode = os.getenv("INKSIGHT_TEXT_FONTMODE", "1").strip()
_bitmap_suffix_to_load_size = {9: 12, 10: 13, 11: 15, 12: 16, 13: 14}
_bitmap_max_request_size = int(os.getenv("INKSIGHT_BITMAP_MAX_REQUEST_SIZE", "16"))


def apply_text_fontmode(draw: ImageDraw.ImageDraw) -> None:
    draw.fontmode = "1" if _fontmode != "L" else "L"


def _ordered_bitmap_suffixes(size: int) -> list[int]:
    return sorted(
        _bitmap_suffix_to_load_size.keys(),
        key=lambda s: abs(_bitmap_suffix_to_load_size[s] - size),
    )


def _bitmap_load_size_from_path(path: str, requested_size: int) -> int:
    m = re.search(r"-(\d+)\.(pcf|otb)$", path.lower())
    if m:
        suffix = int(m.group(1))
        mapped = _bitmap_suffix_to_load_size.get(suffix)
        if mapped is not None:
            return mapped
    return requested_size


def _bitmap_candidates(font_name: str, size: int) -> list[str]:
    name = os.path.basename(font_name)
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext in {".pil", ".pcf", ".otb"}:
        return [name]
    suffixes = _ordered_bitmap_suffixes(size)
    sized_pcf = [f"{stem}-{s}.pcf" for s in suffixes]
    sized_otb = [f"{stem}-{s}.otb" for s in suffixes]
    sized_pil = [f"{stem}-{s}.pil" for s in suffixes]
    return [
        *sized_pcf,
        f"{stem}.pcf",
        *sized_otb,
        f"{stem}.otb",
        *sized_pil,
        f"{stem}.pil",
    ]


def _load_bitmap_font(font_name: str, size: int) -> ImageFont.ImageFont | None:
    if size > _bitmap_max_request_size:
        return None
    for rel in _bitmap_candidates(font_name, size):
        path = os.path.join(BITMAP_DIR, rel)
        if not os.path.exists(path):
            continue
        try:
            lower = path.lower()
            if lower.endswith(".pil"):
                return ImageFont.load(path)
            load_size = _bitmap_load_size_from_path(path, size)
            return ImageFont.truetype(path, load_size)
        except OSError:
            if rel not in _bitmap_warned:
                _bitmap_warned.add(rel)
                logger.warning(f"[FONT] Failed to load bitmap font: {path}", exc_info=True)
    return None


def load_font(font_key: str, size: int) -> ImageFont.ImageFont:
    """translated"""
    font_name = FONTS.get(font_key)
    if not font_name:
        # Fallback to CJK font if default font key not found
        fallback_cjk = "NotoSerifSC-Regular.ttf"
        fallback_path = os.path.join(TRUETYPE_DIR, fallback_cjk)
        if os.path.exists(fallback_path):
            return ImageFont.truetype(fallback_path, size)
        return ImageFont.load_default()
    if _force_bitmap:
        bitmap_font = _load_bitmap_font(font_name, size)
        if bitmap_font is not None:
            return bitmap_font
    path = os.path.join(TRUETYPE_DIR, font_name)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception as e:
            logger.warning(f"[FONT] Failed to load {font_name}: {e}")
            # Fallback to CJK font if loading fails
            fallback_cjk = "NotoSerifSC-Regular.ttf"
            fallback_path = os.path.join(TRUETYPE_DIR, fallback_cjk)
            if os.path.exists(fallback_path):
                return ImageFont.truetype(fallback_path, size)
    if font_key not in _font_warned:
        _font_warned.add(font_key)
        logger.warning(f"[FONT] Missing {font_name}, run: python scripts/setup_fonts.py")
    # Final fallback: try CJK font before default
    fallback_cjk = "NotoSerifSC-Regular.ttf"
    fallback_path = os.path.join(TRUETYPE_DIR, fallback_cjk)
    if os.path.exists(fallback_path):
        return ImageFont.truetype(fallback_path, size)
    return ImageFont.load_default()


def load_font_by_name(name: str, size: int) -> ImageFont.ImageFont:
    """translated（translated）"""
    if _force_bitmap:
        bitmap_font = _load_bitmap_font(name, size)
        if bitmap_font is not None:
            return bitmap_font
    path = os.path.join(TRUETYPE_DIR, name)
    if os.path.exists(path):
        if name.lower().endswith(".pil"):
            return ImageFont.load(path)
        return ImageFont.truetype(path, size)
    if name not in _font_warned:
        _font_warned.add(name)
        logger.warning(f"[FONT] Missing {name}, run: python scripts/setup_fonts.py")
    return ImageFont.load_default()


def rgba_to_mono(
    img: Image.Image, target_size: tuple[int, int] | None = None
) -> Image.Image:
    """Convert an RGBA icon to monochrome (mode '1'), optionally resizing."""
    if target_size:
        img = img.resize(target_size, Image.LANCZOS)
    img = img.convert("RGBA")
    mono = Image.new("1", img.size, 1)
    for x in range(img.width):
        for y in range(img.height):
            _, _, _, a = img.getpixel((x, y))
            if a > 128:
                mono.putpixel((x, y), 0)
    return mono


def load_icon(name: str, size: tuple[int, int] | None = None) -> Image.Image | None:
    """Load a PNG icon from ICONS_DIR, convert to monochrome, optionally resize."""
    path = os.path.join(ICONS_DIR, f"{name}.png")
    if os.path.exists(path):
        img = Image.open(path)
        if img.mode == "1":
            if size:
                img = img.resize(size, Image.LANCZOS)
            return img
        return rgba_to_mono(img, size)
    return None


def get_weather_icon(weather_code: int) -> Image.Image | None:
    """Get weather icon image by WMO weather code."""
    icon_name = WEATHER_ICON_MAP.get(weather_code, "cloud")
    return load_icon(icon_name, size=ICON_SIZES["weather"])


def get_mode_icon(mode: str) -> Image.Image | None:
    """Get footer mode icon (book, electric_bolt, etc.)."""
    icon_name = None
    try:
        from ..mode_registry import get_registry
        info = get_registry().get_mode_info(mode)
        if info:
            icon_name = info.icon
    except (ImportError, AttributeError, RuntimeError):
        logger.warning("[FONT] Falling back to static mode icon mapping for %s", mode, exc_info=True)
        # Registry may be unavailable in some test/bootstrap paths.
        fallback_icons = {
            "DAILY": "sunny",
            "BRIEFING": "global",
            "ARTWALL": "art",
            "RECIPE": "food",
            "COUNTDOWN": "flag",
        }
        icon_name = fallback_icons.get(mode.upper())
    if icon_name:
        return load_icon(icon_name, size=ICON_SIZES["mode"])
    return None


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple,
    end: tuple,
    fill=0,
    width: int = 1,
    dash_len: int = 4,
    gap_len: int = 4,
):
    """Draw a horizontal dashed line (for zen/faded style)."""
    x0, y0 = start
    x1, _ = end
    x = x0
    while x < x1:
        seg_end = min(x + dash_len, x1)
        draw.line([(x, y0), (seg_end, y0)], fill=fill, width=width)
        x += dash_len + gap_len


def draw_dashed_line_vertical(
    draw: ImageDraw.ImageDraw,
    x: int,
    y0: int,
    y1: int,
    *,
    fill=0,
    width: int = 1,
    dash_len: int = 3,
    gap_len: int = 3,
) -> None:
    """Short vertical dashes (internal grid / TRMNL-style dividers)."""
    y = y0
    while y < y1:
        seg_end = min(y + dash_len, y1)
        draw.line([(x, y), (x, seg_end)], fill=fill, width=width)
        y += dash_len + gap_len


def draw_surface_footer_bar(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    mode: str,
    attribution: str,
    *,
    mode_id: str = "",
    weather_code: int | None = None,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
    colors: int = 2,
) -> None:
    """Inset rounded bar, solid black fill; white label + attribution; icon left."""
    scale = screen_w / 400.0
    # Narrower side margins → wider bar (still clear of panel edge)
    margin_x = max(4, int(screen_w * 0.014))
    margin_b = max(6, int(screen_h * 0.026))
    bar_h = max(26, int(screen_h * 0.092))

    x0 = margin_x
    y0 = screen_h - margin_b - bar_h
    x1 = screen_w - margin_x
    y1 = screen_h - margin_b
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    # Modest corner radius (not full pill)
    r = min(max(4, h // 5), w // 2, 10)

    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    # Solid black bar (L=0); surface preview threshold maps L≤135 → black ink.
    patch = Image.new("L", (w, h), 0)
    img.paste(patch, (x0, y0), mask)

    on_dark = 255  # white on black footer (L; survives 1-bit threshold in surface preview)

    label_px = int(FONT_SIZES["footer"]["label"] * scale * 1.12)
    font_label = load_font("inter_medium", label_px)
    attr_font_size = int(FONT_SIZES["footer"]["attribution"] * scale * 1.08)
    if attribution and has_cjk(attribution):
        font_attr = load_font("noto_serif_bold", attr_font_size)
    else:
        font_attr = load_font("lora_bold", attr_font_size)

    pad_in = int(10 * scale)
    icon_x = x0 + pad_in
    _icon_sz = int(14 * scale)
    icon_y = y0 + (bar_h - _icon_sz) // 2
    icon_key = str(mode_id or mode)
    mode_icon = None
    if icon_key.upper() == "WEATHER" and weather_code is not None:
        try:
            mode_icon = get_weather_icon(int(weather_code))
        except (TypeError, ValueError):
            mode_icon = None
    if mode_icon is None:
        mode_icon = get_mode_icon(icon_key)
    label_x = icon_x
    if mode_icon:
        paste_icon_onto(img, mode_icon, (icon_x, icon_y), fill=on_dark)
        label_x = icon_x + int(15 * scale)

    mode_upper = (mode or "").upper()

    def _footer_text_y(font, text: str) -> int:
        bb = draw.textbbox((0, 0), text, font=font)
        th = bb[3] - bb[1]
        return y0 + (bar_h - th) // 2 - bb[1]

    text_y = _footer_text_y(font_label, mode_upper)
    draw.text((label_x, text_y), mode_upper, fill=on_dark, font=font_label)

    if attribution:
        bbox = draw.textbbox((0, 0), attribution, font=font_attr)
        tw = bbox[2] - bbox[0]
        attr_y = _footer_text_y(font_attr, attribution)
        draw.text((x1 - pad_in - tw, attr_y), attribution, fill=on_dark, font=font_attr)


def draw_status_bar(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    date_str: str,
    weather_str: str,
    battery_pct: int,
    weather_code: int = -1,
    line_width: int = 1,
    dashed: bool = False,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
    colors: int = 2,
    language: str = "zh",
    suppress_center_weather: bool = False,
):
    """translated"""
    def _strip_time_tokens(text: str) -> str:
        """Remove any clock fragment like HH:MM / HH:MM:SS."""
        if not text:
            return ""
        cleaned = re.sub(r"\b([01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b", "", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|,")
        return cleaned.strip()

    def _fit_single_line(text: str, font, max_w: int) -> str:
        if not text or max_w <= 0:
            return ""
        if font.getlength(text) <= max_w:
            return text
        ellipsis = "..."
        if font.getlength(ellipsis) > max_w:
            return ""
        trimmed = text
        while trimmed and font.getlength(trimmed + ellipsis) > max_w:
            trimmed = trimmed[:-1]
        return (trimmed.rstrip() + ellipsis) if trimmed else ""

    is_latin = language != "zh"
    scale = screen_w / 400.0
    if is_latin:
        font_date = load_font("lora_regular", int(FONT_SIZES["status_bar"]["cn"] * scale))
    else:
        font_date = load_font("noto_serif_extralight", int(FONT_SIZES["status_bar"]["cn"] * scale))
    font_en = load_font("inter_medium", int(FONT_SIZES["status_bar"]["en"] * scale))

    pad_pct = 0.02 if screen_h < 200 else 0.03
    pad_y = int(screen_h * pad_pct)
    pad_x = int(screen_w * pad_pct)
    y = pad_y

    wx = screen_w // 2 - int(28 * scale)
    left_max_w = max(40, wx - pad_x - int(10 * scale))
    safe_date_text = _strip_time_tokens((date_str or "").strip())
    fitted_date = _fit_single_line(safe_date_text, font_date, left_max_w)
    date_bbox = draw.textbbox((0, 0), fitted_date or "", font=font_date)
    date_h = date_bbox[3] - date_bbox[1]
    text_mid_y = y + int(5 * scale)
    date_y = int(text_mid_y - date_h / 2)
    if fitted_date:
        draw.text((pad_x, date_y), fitted_date, fill=EINK_FG, font=font_date)

    # Weather icon only in the bar center — omit temperature text (e.g. "22°C"), which on
    # 1-bit panels is often misread as a clock; full detail stays in WEATHER mode body, etc.
    if not suppress_center_weather:
        weather_icon = get_weather_icon(weather_code) if weather_code >= 0 else None
        if weather_icon:
            icon_fill = EINK_COLOR_NAME_MAP.get("red", EINK_FG) if colors >= 3 else EINK_FG
            paste_icon_onto(img, weather_icon, (wx, y - 1), fill=icon_fill)
        elif (weather_str or "").strip():
            draw.text((wx, y), weather_str, fill=EINK_FG, font=font_date)

    batt_text = f"{battery_pct}%"
    bbox = draw.textbbox((0, 0), batt_text, font=font_en)
    batt_text_w = bbox[2] - bbox[0]

    batt_fill = EINK_FG
    available = EINK_COLOR_AVAILABILITY.get(colors, frozenset())
    if battery_pct < 20 and "red" in available:
        batt_fill = EINK_COLOR_NAME_MAP["red"]
    elif battery_pct < 50 and "yellow" in available:
        batt_fill = EINK_COLOR_NAME_MAP["yellow"]

    batt_box_w = int(22 * scale)
    batt_box_h = int(11 * scale)
    bx = screen_w - pad_x - batt_text_w - int(6 * scale) - batt_box_w
    by = y + 1
    draw.rectangle([bx, by, bx + batt_box_w, by + batt_box_h], outline=batt_fill, width=1)
    draw.rectangle([bx + batt_box_w, by + int(3 * scale), bx + batt_box_w + int(2 * scale), by + int(8 * scale)], fill=batt_fill)
    fill_w = int((batt_box_w - 4) * battery_pct / 100)
    if fill_w > 0:
        draw.rectangle([bx + 2, by + 2, bx + 2 + fill_w, by + batt_box_h - 2], fill=batt_fill)

    draw.text((bx + batt_box_w + int(6 * scale), y), batt_text, fill=batt_fill, font=font_en)

    # Intentionally omit the full-width bottom divider line for the top bar.


def has_cjk(text: str) -> bool:
    """Check if text contains CJK (Chinese/Japanese/Korean) characters."""
    return any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in text)


def draw_footer(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    mode: str,
    attribution: str,
    mode_id: str = "",
    weather_code: int | None = None,
    line_width: int = 1,
    dashed: bool = False,
    attr_font: str | None = None,
    attr_font_size: int | None = None,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
    colors: int = 2,
):
    """translated"""
    scale = screen_w / 400.0
    if attr_font_size is None:
        attr_font_size = int(FONT_SIZES["footer"]["attribution"] * scale)

    # Smaller footer on short screens
    footer_pct = 0.08 if screen_h < 200 else 0.10
    y_line = screen_h - int(screen_h * footer_pct)
    if dashed:
        draw_dashed_line(
            draw, (0, y_line), (screen_w, y_line), fill=EINK_FG, width=line_width
        )
    else:
        draw.line([(0, y_line), (screen_w, y_line)], fill=EINK_FG, width=line_width)

    font_label = load_font("inter_medium", int(FONT_SIZES["footer"]["label"] * scale))
    if attr_font:
        font_attr = load_font_by_name(attr_font, attr_font_size)
    elif attribution and has_cjk(attribution):
        font_attr = load_font("noto_serif_light", attr_font_size)
    else:
        font_attr = load_font("lora_regular", attr_font_size)

    icon_x = int(12 * scale)
    icon_y = y_line + int(9 * scale)
    icon_key = str(mode_id or mode)
    mode_icon = None
    if icon_key.upper() == "WEATHER" and weather_code is not None:
        try:
            mode_icon = get_weather_icon(int(weather_code))
        except (TypeError, ValueError):
            mode_icon = None
    if mode_icon is None:
        mode_icon = get_mode_icon(icon_key)
    if mode_icon:
        icon_fill = EINK_COLOR_NAME_MAP.get("red", EINK_FG) if colors >= 3 else EINK_FG
        paste_icon_onto(img, mode_icon, (icon_x, icon_y), fill=icon_fill)
        label_x = icon_x + int(15 * scale)
    else:
        label_x = icon_x
    draw.text((label_x, y_line + int(9 * scale)), mode.upper(), fill=EINK_FG, font=font_label)

    if attribution:
        bbox = draw.textbbox((0, 0), attribution, font=font_attr)
        draw.text(
            (screen_w - int(12 * scale) - (bbox[2] - bbox[0]), y_line + int(9 * scale)),
            attribution,
            fill=EINK_FG,
            font=font_attr,
        )


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Wrap text to pixel width. Latin uses word boundaries; CJK uses per-character fitting."""

    def _line_width(s: str) -> float:
        try:
            return float(font.getlength(s))
        except Exception:
            bbox = font.getbbox(s)
            return float(bbox[2] - bbox[0])

    def _wrap_latin_words(paragraph: str) -> list[str]:
        out: list[str] = []
        parts = paragraph.split()
        if not parts:
            return [""] if paragraph.strip() == "" else []
        current = parts[0]
        for word in parts[1:]:
            trial = current + " " + word
            if _line_width(trial) <= max_width:
                current = trial
                continue
            out.append(current)
            if _line_width(word) <= max_width:
                current = word
                continue
            chunk = ""
            for ch in word:
                t2 = chunk + ch
                if _line_width(t2) > max_width and chunk:
                    out.append(chunk)
                    chunk = ch
                else:
                    chunk = t2
            current = chunk
        out.append(current)
        return out

    def _wrap_cjk_chars(paragraph: str) -> list[str]:
        out: list[str] = []
        current = ""
        for ch in paragraph:
            test = current + ch
            if _line_width(test) > max_width and current:
                out.append(current)
                current = ch
            else:
                current = test
        if current:
            out.append(current)
        return out

    lines: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        if has_cjk(paragraph):
            lines.extend(_wrap_cjk_chars(paragraph))
        else:
            lines.extend(_wrap_latin_words(paragraph))
    return lines


def render_quote_body(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_name: str,
    font_size: int,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
):
    """translated"""
    if has_cjk(text) and "Noto" not in font_name:
        font_name = "NotoSerifSC-Light.ttf"
    font = load_font_by_name(font_name, font_size)
    lines = wrap_text(text, font, screen_w - 48)
    line_h = font_size + 8
    total_h = len(lines) * line_h
    y_start = 32 + (screen_h - 32 - 30 - total_h) // 2

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        x = (screen_w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y_start + i * line_h), line, fill=EINK_FG, font=font)
