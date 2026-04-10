"""
translated + translated
translated Python modetranslated JSON translatedmodetranslated
"""
from __future__ import annotations

import logging
from PIL import Image

from datetime import datetime

from .config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_MODEL,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_LANGUAGE,
    DEFAULT_CONTENT_TONE,
)

WEEKDAY_EN_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_EN_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_date_str(date_ctx: dict, language: str) -> str:
    if language == "en":
        weekday = int(date_ctx.get("weekday", datetime.now().weekday()))
        day = int(date_ctx.get("day", datetime.now().day))
        month = int(date_ctx.get("month", datetime.now().month))
        return f"{MONTH_EN_SHORT[month - 1]} {day} {WEEKDAY_EN_SHORT[weekday]}"
    return date_ctx["date_str"]

logger = logging.getLogger(__name__)


def get_effective_mode_config(cfg: dict | None, persona: str) -> dict:
    base = dict(cfg or {})
    mode_overrides = base.get("mode_overrides", {})
    if not isinstance(mode_overrides, dict):
        return base
    override = mode_overrides.get((persona or "").upper(), {})
    if not isinstance(override, dict):
        return base
    for key in (
        "city",
        "latitude",
        "longitude",
        "timezone",
        "admin1",
        "country",
        "llm_provider",
        "llm_model",
    ):
        value = override.get(key)
        if isinstance(value, str) and value.strip():
            base[key] = value.strip()
        elif isinstance(value, (int, float)) and key in {"latitude", "longitude"}:
            base[key] = value
    reserved = {
        "city",
        "latitude",
        "longitude",
        "timezone",
        "admin1",
        "country",
        "llm_provider",
        "llm_model",
        "llmProvider",
        "llmModel",
    }
    mode_settings = {k: v for k, v in override.items() if k not in reserved}
    if mode_settings:
        base["mode_settings"] = mode_settings
    return base


async def generate_and_render(
    persona: str,
    config: dict | None,
    date_ctx: dict,
    weather: dict,
    battery_pct: float,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
    mac: str = "",
    colors: int = 2,
    omit_chrome: bool = False,
) -> tuple[Image.Image, dict | None]:
    """Generate content for a persona and render to an e-ink image.

    Dispatches to either a builtin Python mode or a JSON-defined mode
    via the mode registry.

    ``omit_chrome`` skips per-mode status/footer in JSON renders (for surface tile compositing).

    Returns:
        Tuple of (rendered image, content dict).
    """
    time_str = date_ctx.get("time_str", "")
    weather_str = weather["weather_str"]
    weather_code = weather.get("weather_code", -1)
    cfg = get_effective_mode_config(config, persona)

    content = await _generate_content_for_persona(
        persona,
        cfg,
        date_ctx,
        weather_str,
        mac=mac,
        screen_w=screen_w,
        screen_h=screen_h,
    )

    eff_cfg = get_effective_mode_config(config, persona)
    _eff_lang = eff_cfg.get("mode_language", "") or DEFAULT_LANGUAGE
    date_str = _format_date_str(date_ctx, _eff_lang)

    img = _render_for_persona(
        persona,
        content,
        date_str=date_str,
        weather_str=weather_str,
        battery_pct=battery_pct,
        weather_code=weather_code,
        time_str=time_str,
        date_ctx=date_ctx,
        screen_w=screen_w,
        screen_h=screen_h,
        mac=mac or "",
        colors=colors,
        language=_eff_lang,
        omit_chrome=omit_chrome,
    )
    return img, content


async def generate_content_only(
    persona: str,
    config: dict | None,
    date_ctx: dict,
    weather: dict,
    *,
    mac: str = "",
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
) -> dict:
    cfg = get_effective_mode_config(config, persona)
    return await _generate_content_for_persona(
        persona,
        cfg,
        date_ctx,
        weather.get("weather_str", ""),
        mac=mac,
        screen_w=screen_w,
        screen_h=screen_h,
    )


async def _generate_content_for_persona(
    persona: str,
    cfg: dict,
    date_ctx: dict,
    weather_str: str,
    mac: str = "",
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
) -> dict:
    """Dispatch content generation to the appropriate handler."""
    from .mode_registry import ContentContext, get_registry

    registry = get_registry()

    effective_language = cfg.get("mode_language", "") or DEFAULT_LANGUAGE
    date_str = _format_date_str(date_ctx, effective_language)

    device_api_key: str | None = None
    device_image_api_key: str | None = None

    user_api_key = cfg.get("user_api_key")
    if isinstance(user_api_key, str):
        device_api_key = user_api_key
        logger.info(
            "[Pipeline] Using user_api_key for persona=%s (mac=%s), length=%s",
            persona,
            mac,
            len(user_api_key) if user_api_key else 0,
        )
    else:
        logger.info("[Pipeline] No user_api_key in config, will use env var")
    
    user_image_api_key = cfg.get("user_image_api_key")
    if isinstance(user_image_api_key, str):
        device_image_api_key = user_image_api_key
        logger.info(
            "[Pipeline] Using user_image_api_key for persona=%s (mac=%s), length=%s",
            persona,
            mac,
            len(user_image_api_key) if user_image_api_key else 0,
        )

    ctx = ContentContext(
        config=cfg,
        date_ctx=date_ctx,
        weather_str=weather_str,
        date_str=date_str,
        festival=date_ctx.get("festival", ""),
        daily_word=date_ctx.get("daily_word", ""),
        upcoming_holiday=date_ctx.get("upcoming_holiday", ""),
        days_until_holiday=date_ctx.get("days_until_holiday", 0),
        character_tones=cfg.get("character_tones", []),
        language=effective_language,
        content_tone=cfg.get("content_tone", DEFAULT_CONTENT_TONE),
        llm_provider=cfg.get("llm_provider", DEFAULT_LLM_PROVIDER),
        llm_model=cfg.get("llm_model", DEFAULT_LLM_MODEL),
        api_key=device_api_key,
        image_api_key=device_image_api_key,
        llm_base_url=cfg.get("llm_base_url"),
    )

    # JSON-defined mode
    if registry.is_json_mode(persona):
        from .json_content import generate_json_mode_content
        jm = registry.get_json_mode(persona, mac, language=effective_language)
        if not jm:
            # Try to load from database if mode not in registry
            # This can happen for user-specific custom modes
            if mac:
                from .config_store import get_device_owner, get_custom_mode as get_user_custom_mode_from_db
                owner = await get_device_owner(mac)
                if owner:
                    user_id = owner.get("user_id")
                    if user_id:
                        mode_data = await get_user_custom_mode_from_db(user_id, persona, mac)
                        if mode_data:
                            mode_mac = mode_data.get("mac")
                            registry.load_custom_mode_from_dict(persona, mode_data["definition"], source="custom", mac=mode_mac)
                            jm = registry.get_json_mode(persona, mac, language=effective_language)
        if not jm:
            raise ValueError(f"JSON mode {persona} not found in registry")
        return await generate_json_mode_content(
            jm.definition,
            config=cfg,
            date_ctx=date_ctx,
            date_str=date_str,
            weather_str=weather_str,
            festival=date_ctx.get("festival", ""),
            daily_word=date_ctx.get("daily_word", ""),
            upcoming_holiday=date_ctx.get("upcoming_holiday", ""),
            days_until_holiday=date_ctx.get("days_until_holiday", 0),
            character_tones=cfg.get("character_tones", []),
            language=effective_language,
            content_tone=cfg.get("content_tone", DEFAULT_CONTENT_TONE),
            llm_provider=cfg.get("llm_provider", DEFAULT_LLM_PROVIDER),
            llm_model=cfg.get("llm_model", DEFAULT_LLM_MODEL),
            llm_base_url=cfg.get("llm_base_url"),
            image_provider=cfg.get("image_provider", DEFAULT_IMAGE_PROVIDER),
            image_model=cfg.get("image_model", DEFAULT_IMAGE_MODEL),
            mac=mac,
            screen_w=screen_w,
            screen_h=screen_h,
            api_key=device_api_key,
            image_api_key=device_image_api_key,
        )

    # Builtin Python mode - use specialized content functions
    bm = registry.get_builtin(persona)
    if bm:
        return await bm.content_fn(ctx)

    raise ValueError(f"Unknown persona: {persona}")


def _render_for_persona(
    persona: str,
    content: dict,
    *,
    date_str: str,
    weather_str: str,
    battery_pct: float,
    weather_code: int = -1,
    time_str: str = "",
    date_ctx: dict | None = None,
    screen_w: int = SCREEN_WIDTH,
    screen_h: int = SCREEN_HEIGHT,
    mac: str = "",
    colors: int = 2,
    language: str = "zh",
    omit_chrome: bool = False,
) -> Image.Image:
    """Dispatch rendering to the appropriate handler."""
    from .mode_registry import get_registry
    from .renderer import render_mode
    from .json_renderer import render_json_mode

    registry = get_registry()

    # JSON-defined mode
    if registry.is_json_mode(persona):
        jm = registry.get_json_mode(persona, mac or None, language=language)
        # Weather modetranslated（translated、translated）
        if persona.upper() == "WEATHER":
            weather_str_for_bar = ""
            weather_code_for_bar = -1
        else:
            weather_str_for_bar = weather_str
            weather_code_for_bar = weather_code
        return render_json_mode(
            jm.definition, content,
            date_str=date_str, weather_str=weather_str_for_bar, battery_pct=battery_pct,
            weather_code=weather_code_for_bar, time_str=time_str,
            screen_w=screen_w, screen_h=screen_h, colors=colors,
            language=language,
            omit_chrome=omit_chrome,
        )

    # Builtin Python mode — always raises; kept for stack traces
    return render_mode(
        persona, content,
        date_str=date_str, weather_str=weather_str, battery_pct=battery_pct,
        weather_code=weather_code, time_str=time_str, date_ctx=date_ctx,
        screen_w=screen_w, screen_h=screen_h,
    )
