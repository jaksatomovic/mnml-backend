"""Metadata for device firmware: status bar + footer strings (not drawn in the bitmap)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from .config import (
    DEFAULT_CITY,
    DEVICE_FOOTER_HEIGHT_PX,
    DEVICE_STATUS_BAR_HEIGHT_PX,
)
from .context import (
    calc_battery_pct,
    extract_location_settings,
    get_date_context,
    get_weather,
)
from .render_tiers import merge_layout_for_screen

logger = logging.getLogger(__name__)


def _resolve_template(content: dict, template: str) -> str:
    def _replace(m: re.Match) -> str:
        key = m.group(1)
        val = content.get(key, "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val)

    return re.sub(r"\{(\w+)\}", _replace, template)


def build_render_chrome(
    mode_def: dict[str, Any],
    content: dict[str, Any] | None,
    *,
    mode_id: str,
    date_str: str,
    time_str: str,
    weather_str: str,
    battery_pct: float,
    weather_code: int,
    language: str,
    screen_w: int,
    screen_h: int,
) -> dict[str, Any]:
    """Build header/footer payloads for firmware. Safe when content is empty (cache hit)."""
    from .json_renderer import _localized_footer_attribution, _localized_footer_label

    c = content if isinstance(content, dict) else {}
    base_layout = mode_def.get("layout", {})
    overrides = mode_def.get("layout_overrides", {})
    layout = merge_layout_for_screen(
        base_layout if isinstance(base_layout, dict) else {},
        overrides if isinstance(overrides, dict) else None,
        screen_w=screen_w,
        screen_h=screen_h,
    )
    ft = layout.get("footer", {}) if isinstance(layout.get("footer"), dict) else {}
    status_bar_cfg = (
        layout.get("status_bar", {}) if isinstance(layout.get("status_bar"), dict) else {}
    )

    label = _localized_footer_label(mode_id, str(ft.get("label", mode_id) or mode_id), language)
    attr_t = str(ft.get("attribution_template", "") or "")
    attribution = _resolve_template(c, attr_t) if attr_t else ""
    attribution = _localized_footer_attribution(mode_id, attribution, language)

    mid = (mode_id or "").upper()
    footer_icon_code = c.get("today_code", c.get("code"))

    # Contract: screen_w × screen_h is the delivered bitmap (body). Full panel on device
    # is body plus fixed chrome strips (same numbers as firmware).
    sb_px = int(DEVICE_STATUS_BAR_HEIGHT_PX)
    fb_px = int(DEVICE_FOOTER_HEIGHT_PX)
    panel_h = int(screen_h) + sb_px + fb_px

    return {
        "mode_id": mid,
        "layout": {
            "status_bar_px": sb_px,
            "footer_px": fb_px,
            "body_w": int(screen_w),
            "body_h": int(screen_h),
            "panel_w": int(screen_w),
            "panel_h": panel_h,
        },
        "header": {
            "date_str": date_str,
            "time_str": time_str or "",
            "weather_str": weather_str,
            "weather_code": int(weather_code) if weather_code is not None else -1,
            "battery_pct": float(battery_pct),
            "status_bar": {
                "line_width": status_bar_cfg.get("line_width", 1),
                "dashed": bool(status_bar_cfg.get("dashed", False)),
            },
        },
        "footer": {
            "label": label,
            "attribution": attribution,
            "line_width": ft.get("line_width", 1),
            "dashed": bool(ft.get("dashed", False)),
            "weather_code": footer_icon_code,
        },
    }


async def assemble_render_chrome(
    *,
    mac: str | None,
    persona: str,
    config: dict[str, Any] | None,
    content_data: dict[str, Any] | None,
    v: float,
    screen_w: int,
    screen_h: int,
) -> dict[str, Any] | None:
    """Rebuild chrome metadata (e.g. cache hit) using fresh date/weather/battery."""
    from .mode_registry import get_registry
    from .pipeline import _format_date_str, get_effective_mode_config
    from .stats_store import get_latest_render_content_for_mode

    registry = get_registry()
    if not registry.is_json_mode(persona):
        return None
    jm = registry.get_json_mode(persona, mac)
    if not jm or not isinstance(jm.definition, dict):
        return None
    eff = get_effective_mode_config(config, persona)
    lang = str(eff.get("mode_language") or eff.get("modeLanguage") or "").strip() or "zh"
    loc = extract_location_settings(eff, fallback_city=DEFAULT_CITY)
    tz = str(eff.get("timezone", "") or "").strip()
    date_ctx, weather = await asyncio.gather(
        get_date_context(timezone_name=tz),
        get_weather(**loc),
    )
    time_str = str(date_ctx.get("time_str", "") or "")
    weather_str = str(weather.get("weather_str", "") or "")
    weather_code = int(weather.get("weather_code", -1) or -1)
    date_str = _format_date_str(date_ctx, lang)
    battery_pct = float(calc_battery_pct(v))
    merged_content: dict[str, Any] = dict(content_data) if isinstance(content_data, dict) else {}
    if mac and not merged_content:
        latest = await get_latest_render_content_for_mode(mac, persona)
        if isinstance(latest, dict):
            merged_content = latest
    mode_id = str(jm.definition.get("mode_id", "") or persona).upper()
    return build_render_chrome(
        jm.definition,
        merged_content,
        mode_id=mode_id,
        date_str=date_str,
        time_str=time_str,
        weather_str=weather_str,
        battery_pct=battery_pct,
        weather_code=weather_code,
        language=lang,
        screen_w=screen_w,
        screen_h=screen_h,
    )
