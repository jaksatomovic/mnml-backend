import base64
import io
import json
import time
from datetime import datetime
from json import JSONDecodeError
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image, UnidentifiedImageError

from api.shared import (
    _preview_push_queue,
    _preview_push_queue_lock,
    _render_device_unbound_image,
    build_image,
    content_cache,
    ensure_web_or_device_access,
    limiter,
    log_render_stats,
    logger,
    reconnect_threshold_seconds,
    resolve_preview_voltage,
    resolve_refresh_minutes_for_device_state,
)
from core.auth import require_device_token, validate_mac_param
from core.config import DEFAULT_REFRESH_INTERVAL, SCREEN_HEIGHT, SCREEN_WIDTH
from core.config_store import (
    append_surface_event,
    consume_pending_refresh,
    get_active_config,
    get_device_owner,
    get_device_state,
    get_recent_surface_events,
    get_or_create_claim_token,
    list_active_surface_device_configs,
    set_pending_refresh,
    update_device_state,
)
from core.context import extract_location_settings, get_date_context, get_weather
from core.pipeline import generate_and_render
from core.renderer import image_to_bmp_bytes, image_to_png_bytes, image_to_raw_2bpp, render_error
from core.schemas import RenderQuery
from core.surface_engine import (
    build_surface_render_payload,
    evaluate_event_for_device,
    resolve_device_surface,
)
from core.surface_preview_render import render_surface_preview_image
from core.stats_store import get_latest_heartbeat

router = APIRouter(tags=["render"])


def _chrome_header_value(chrome: Optional[dict]) -> Optional[str]:
    """Compact JSON (UTF-8) as URL-safe base64 without padding, for X-InkSight-Chrome."""
    if not chrome:
        return None
    try:
        raw = json.dumps(chrome, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    except (TypeError, ValueError):
        return None


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _configured_refresh_minutes(config: Optional[dict]) -> int:
    refresh_minutes_raw = config.get("refresh_interval") if config else DEFAULT_REFRESH_INTERVAL
    try:
        refresh_minutes = int(refresh_minutes_raw)
    except (TypeError, ValueError):
        refresh_minutes = DEFAULT_REFRESH_INTERVAL
    if refresh_minutes < 10:
        return 10
    if refresh_minutes > 1440:
        return 1440
    return refresh_minutes


@router.get("/render-json")
async def render_json(
    mac: str = Query(..., description="Device MAC"),
):
    mac = validate_mac_param(mac)
    cfg = await get_active_config(mac, log_load=False)
    if not cfg:
        return {"layout": [{"type": "text", "content": "No config", "size": "medium"}], "meta": {"mode": "mode"}}

    device_mode = str(cfg.get("device_mode") or cfg.get("deviceMode") or "mode").strip().lower()
    if device_mode == "surface":
        surface, reason = resolve_device_surface(mac, cfg)
        payload = build_surface_render_payload(surface, reason)
        payload["meta"]["mode"] = "surface"
        payload["meta"]["assigned"] = str(cfg.get("assigned_surface") or cfg.get("assignedSurface") or "")
        return payload

    assigned_mode = str(cfg.get("assigned_mode") or cfg.get("assignedMode") or "").strip().upper()
    mode_fallback = assigned_mode or (cfg.get("modes", ["STOIC"])[0] if cfg.get("modes") else "STOIC")
    return {
        "layout": [{"type": "text", "content": f"Mode: {mode_fallback}", "size": "large"}],
        "meta": {"mode": "mode", "assigned": mode_fallback, "refresh": {"mode": "polling", "interval": _configured_refresh_minutes(cfg) * 60}},
    }


@router.post("/render-json/preview")
async def render_json_preview(payload: dict):
    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    surface = payload.get("surface")
    if not isinstance(surface, dict):
        return JSONResponse({"error": "surface_required"}, status_code=400)
    normalized = dict(surface)
    normalized["type"] = "surface"
    reason = {"type": "preview"}
    response = build_surface_render_payload(normalized, reason)
    response["meta"]["mode"] = "surface"
    return response


@router.post("/preview/surface")
@limiter.limit("20/minute")
async def preview_surface(
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    """PNG preview for Surface layouts (same resolution pipeline as /preview for modes)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    surface = body.get("surface")
    if not isinstance(surface, dict):
        return JSONResponse({"error": "surface_required"}, status_code=400)
    try:
        w = int(body.get("w", SCREEN_WIDTH))
        h = int(body.get("h", SCREEN_HEIGHT))
    except (TypeError, ValueError):
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
    w = max(100, min(1600, w))
    h = max(100, min(1200, h))

    mac_raw = body.get("mac")
    mac = None
    if mac_raw not in (None, ""):
        mac = validate_mac_param(str(mac_raw).strip())
        await ensure_web_or_device_access(request, mac, x_device_token, ink_session)

    device_config = await get_active_config(mac, log_load=False) if mac else None

    try:
        img = await render_surface_preview_image(
            surface,
            screen_w=w,
            screen_h=h,
            device_config=device_config if isinstance(device_config, dict) else None,
            mac=mac or "",
        )
        png_bytes = image_to_png_bytes(img)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Preview-Surface": "1",
                "Cache-Control": "no-store",
            },
        )
    except (OSError, RuntimeError, TypeError, ValueError, UnidentifiedImageError):
        logger.exception("[PREVIEW_SURFACE] render failed")
        err_img = render_error(mac=mac or "preview", screen_w=w, screen_h=h)
        return Response(content=image_to_png_bytes(err_img), media_type="image/png", status_code=500)


@router.post("/events")
async def post_event(payload: dict):
    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    event_type = str(payload.get("type") or "").strip()
    if not event_type:
        return JSONResponse({"error": "event_type_required"}, status_code=400)
    priority = str(payload.get("priority") or "normal").strip().lower()
    event_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event = {
        "type": event_type,
        "priority": priority,
        "timestamp": payload.get("timestamp") or datetime.now().isoformat(),
        "data": event_data,
    }
    event_id = await append_surface_event(event_type, priority, event)
    impacted: list[dict] = []
    for cfg in await list_active_surface_device_configs():
        mac = str(cfg.get("mac") or "").strip().upper()
        if not mac:
            continue
        matched = evaluate_event_for_device(mac, cfg, event)
        if matched:
            impacted.append({"mac": mac, "action": matched.get("action"), "target": matched.get("target")})
            await set_pending_refresh(mac, True)
            await update_device_state(mac, pending_mode=str(matched.get("target") or ""))
    return {"ok": True, "event_id": event_id, "impacted_devices": impacted}


@router.get("/events/recent")
async def recent_events(limit: int = Query(default=20, ge=1, le=200)):
    return {"events": await get_recent_surface_events(limit)}


@router.get("/render")
@limiter.limit("10/minute")
async def render(
    request: Request,
    params: Annotated[RenderQuery, Depends()],
    x_device_token: Optional[str] = Header(default=None),
):
    mac = params.mac
    cfg: Optional[dict] = None
    configured_refresh_minutes: Optional[int] = None
    owner = None
    if mac:
        mac = validate_mac_param(mac)
        await require_device_token(mac, x_device_token)
        cfg = await get_active_config(mac, log_load=False)
        configured_refresh_minutes = _configured_refresh_minutes(cfg)
        owner = await get_device_owner(mac)

    start_time = time.time()
    force_next = params.next_mode == 1

    try:
        if mac and owner is None:
            claim = await get_or_create_claim_token(mac, source="render")
            img = _render_device_unbound_image(params.w, params.h, claim.get("pair_code", ""))
            bmp_bytes = image_to_bmp_bytes(img)
            headers: dict[str, str] = {}
            if configured_refresh_minutes is not None:
                headers["X-Refresh-Minutes"] = str(configured_refresh_minutes)
            if await consume_pending_refresh(mac):
                headers["X-Pending-Refresh"] = "1"
            return Response(content=bmp_bytes, media_type="image/bmp", headers=headers)

        if mac:
            async with _preview_push_queue_lock:
                pushed_payload = _preview_push_queue.pop(mac, None)
            logger.info("[RENDER] Checked queue for mac=%s: found=%s, mode=%s", mac, pushed_payload is not None, pushed_payload.get("mode") if pushed_payload else None)
            if pushed_payload and pushed_payload.get("image"):
                try:
                    with Image.open(io.BytesIO(pushed_payload["image"])) as pushed_img:
                        if params.colors >= 3 and pushed_img.mode == "P":
                            img = pushed_img.copy()
                        else:
                            img = pushed_img.convert("1")
                        if img.size != (params.w, params.h):
                            img = img.resize((params.w, params.h), Image.NEAREST)
                    if params.colors >= 3 and img.mode == "P":
                        out_bytes = image_to_raw_2bpp(img)
                        out_media = "application/octet-stream"
                    else:
                        out_bytes = image_to_bmp_bytes(img)
                        out_media = "image/bmp"
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    resolved_persona = pushed_payload.get("mode") or params.persona or "PUSH_PREVIEW"
                    await log_render_stats(
                        mac,
                        resolved_persona,
                        False,
                        elapsed_ms,
                        voltage=params.v,
                        rssi=params.rssi,
                    )
                    if params.refresh_min is not None:
                        await update_device_state(mac, expected_refresh_min=params.refresh_min)
                    # Clear pending_mode after delivering the pushed preview, so the device
                    # returns to normal polling instead of re-requesting the same mode every cycle.
                    await update_device_state(mac, pending_mode=None)
                    headers = {"X-Preview-Push": "1"}
                    if configured_refresh_minutes is not None:
                        headers["X-Refresh-Minutes"] = str(configured_refresh_minutes)
                    if await consume_pending_refresh(mac):
                        headers["X-Pending-Refresh"] = "1"
                    return Response(content=out_bytes, media_type=out_media, headers=headers)
                except (OSError, TypeError, UnidentifiedImageError, ValueError) as exc:
                    logger.warning("[RENDER] Failed to deliver pushed preview for %s: %s", mac, exc)

        skip_cache_for_this_render = False
        if mac:
            if cfg:
                state = await get_device_state(mac)
                refresh_minutes = resolve_refresh_minutes_for_device_state(cfg, state)
                latest_heartbeat = await get_latest_heartbeat(mac)
                if latest_heartbeat and latest_heartbeat.get("created_at"):
                    try:
                        now_dt = datetime.now()
                        delta_seconds = (
                            now_dt - datetime.fromisoformat(latest_heartbeat["created_at"])
                        ).total_seconds()
                        threshold_seconds = reconnect_threshold_seconds(refresh_minutes)
                        last_regen_raw = state.get("last_reconnect_regen_at", "") if state else ""
                        regen_cooldown_ok = True
                        if isinstance(last_regen_raw, str) and last_regen_raw:
                            since_last_regen = (
                                now_dt - datetime.fromisoformat(last_regen_raw)
                            ).total_seconds()
                            regen_cooldown_ok = since_last_regen > threshold_seconds
                        if delta_seconds > threshold_seconds and regen_cooldown_ok:
                            skip_cache_for_this_render = True
                            await update_device_state(
                                mac, last_reconnect_regen_at=now_dt.isoformat()
                            )
                            await content_cache.force_regenerate_all(
                                mac, cfg, params.v, params.w, params.h,
                                colors=params.colors,
                            )
                    except (TypeError, ValueError, OSError):
                        logger.warning("[RECONNECT] Failed to evaluate reconnect policy for %s", mac, exc_info=True)

        (
            img,
            resolved_persona,
            cache_hit,
            content_fallback,
            quota_exhausted,
            api_key_invalid,
            llm_mode_requires_quota,
            _usage_source,
            chrome_meta,
        ) = await build_image(
            params.v,
            mac,
            params.persona,
            screen_w=params.w,
            screen_h=params.h,
            force_next=force_next,
            skip_cache=skip_cache_for_this_render,
            colors=params.colors,
        )

        if img.size != (params.w, params.h):
            logger.warning(
                "[RENDER] Image size mismatch for %s:%s: got %sx%s, expected %sx%s. Resizing.",
                mac,
                resolved_persona,
                img.size[0],
                img.size[1],
                params.w,
                params.h,
            )
            img = img.resize((params.w, params.h), Image.NEAREST)

        if params.colors >= 3:
            out_bytes = image_to_raw_2bpp(img)
            out_media = "application/octet-stream"
        else:
            out_bytes = image_to_bmp_bytes(img)
            out_media = "image/bmp"
        elapsed_ms = int((time.time() - start_time) * 1000)
        if mac:
            await log_render_stats(
                mac,
                resolved_persona,
                cache_hit,
                elapsed_ms,
                voltage=params.v,
                rssi=params.rssi,
                is_fallback=content_fallback,
            )
            if params.refresh_min is not None:
                await update_device_state(mac, expected_refresh_min=params.refresh_min)

        headers: dict[str, str] = {
            "X-Render-Time-Ms": str(elapsed_ms),
            "X-Cache-Hit": "1" if cache_hit else "0",
        }
        if configured_refresh_minutes is not None:
            headers["X-Refresh-Minutes"] = str(configured_refresh_minutes)
        if mac and await consume_pending_refresh(mac):
            headers["X-Pending-Refresh"] = "1"
        if content_fallback:
            headers["X-Content-Fallback"] = "1"
        ch = _chrome_header_value(chrome_meta)
        if ch:
            headers["X-InkSight-Chrome"] = ch

        return Response(content=out_bytes, media_type=out_media, headers=headers)
    except (OSError, RuntimeError, TypeError, UnidentifiedImageError, ValueError) as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error("[RENDER] Failed: %s", exc, exc_info=True)
        if mac:
            await log_render_stats(
                mac,
                params.persona or "unknown",
                False,
                elapsed_ms,
                voltage=params.v,
                rssi=params.rssi,
                status="error",
            )
        err_img = render_error(mac=mac or "unknown", screen_w=params.w, screen_h=params.h)
        return Response(
            content=image_to_bmp_bytes(err_img),
            media_type="image/bmp",
            status_code=500,
        )


@router.get("/widget/{mac}")
async def get_widget(
    mac: str,
    mode: str = "",
    w: int = 400,
    h: int = 300,
    size: str = "",
    x_device_token: Optional[str] = Header(default=None),
):
    await require_device_token(mac, x_device_token)
    if size == "small":
        w, h = 200, 150
    elif size == "medium":
        w, h = 400, 300
    elif size == "large":
        w, h = 800, 480

    config = await get_active_config(mac) or {}
    persona = mode.upper() if mode else config.get("modes", ["STOIC"])[0] if config.get("modes") else "STOIC"
    location_args = extract_location_settings(config)
    timezone_name = str(config.get("timezone", "") or "").strip()
    date_ctx = await get_date_context(timezone_name=timezone_name)
    weather = await get_weather(**location_args)
    img, _, _ = await generate_and_render(
        persona,
        config,
        date_ctx,
        weather,
        100.0,
        screen_w=w,
        screen_h=h,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300", "X-InkSight-Mode": persona},
    )


@router.get("/preview")
@limiter.limit("20/minute")
async def preview(
    request: Request,
    v: Optional[float] = Query(default=None),
    mac: Optional[str] = Query(default=None),
    persona: Optional[str] = Query(default=None),
    city_override: Optional[str] = Query(default=None),
    mode_override: Optional[str] = Query(default=None),
    memo_text: Optional[str] = Query(default=None),
    w: int = Query(default=SCREEN_WIDTH, ge=100, le=1600),
    h: int = Query(default=SCREEN_HEIGHT, ge=100, le=1200),
    no_cache: Optional[int] = Query(default=None),
    intent: Optional[int] = Query(default=None),
    colors: int = Query(default=2, ge=2, le=4),
    ui_language: Optional[str] = Query(default=None, description="Preview only: zh|en, overrides device mode_language"),
    x_device_token: Optional[str] = Header(default=None),
    x_inksight_llm_api_key: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    if mac:
        mac = validate_mac_param(mac)
        await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    
    # Get translated ID：
    # - translated Web translated user_llm_config（translated API Key）
    # - translated BILLING.md：translated owner translated，Web translated
    current_user_id = None
    try:
        from core.auth import get_current_user_optional

        current_user = await get_current_user_optional(request, ink_session)
        if current_user:
            current_user_id = current_user.get("user_id")
            logger.debug("[PREVIEW] Current user_id=%s for preview (mac=%s)", current_user_id, mac)
    except Exception:
        logger.warning("[PREVIEW] Failed to resolve current user for preview", exc_info=True)
    
    try:
        effective_v = await resolve_preview_voltage(v, mac)
        parsed_mode_override = None
        if mode_override:
            try:
                candidate = json.loads(mode_override)
                if isinstance(candidate, dict):
                    parsed_mode_override = candidate
            except JSONDecodeError:
                logger.warning("[PREVIEW] Failed to parse mode_override JSON", exc_info=True)
        _ui_lang = (ui_language or "").strip().lower()
        _preview_ui_lang = _ui_lang if _ui_lang in ("zh", "en") else None
        (
            img,
            resolved_persona,
            cache_hit,
            _content_fallback,
            quota_exhausted,
            api_key_invalid,
            llm_mode_requires_quota,
            usage_source,
            chrome_meta,
        ) = await build_image(
            effective_v,
            mac,
            persona,
            screen_w=w,
            screen_h=h,
            skip_cache=(no_cache == 1),
            preview_city_override=(city_override.strip() if city_override else None),
            preview_mode_override=parsed_mode_override,
            preview_memo_text=(memo_text if isinstance(memo_text, str) else None),
            preview_ui_language=_preview_ui_lang,
            current_user_id=current_user_id,
            user_api_key=x_inksight_llm_api_key,
            intent_only=(intent == 1),
            colors=colors,
        )
        if intent == 1:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=200,
                content={
                    "cache_hit": cache_hit,
                    "usage_source": usage_source,
                    "persona": resolved_persona,
                    "requires_invite_code": quota_exhausted,
                    "llm_mode_requires_quota": llm_mode_requires_quota,
                },
            )
        # translated API key invalid，translated JSON translated，translated
        if api_key_invalid:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,  # Bad Request
                content={
                    "error": "api_key_invalid",
                    "message": "translated API key invalidtranslated，translated API key config",
                },
            )
        # translated，translated JSON translated，translated
        if quota_exhausted:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=402,  # Payment Required
                content={
                    "error": "quota_exhausted",
                    "message": "translated，translatedGet translated",
                    "requires_invite_code": True,
                },
            )
        # translated img translated None（translated，translated）
        if img is None:
            logger.error("[PREVIEW] img is None but quota_exhausted is False")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={"error": "image_generation_failed", "message": "imagegeneratefailed"},
            )
        png_bytes = image_to_png_bytes(img)
        logger.info("[PREVIEW] Generated PNG persona=%s size=%sx%s", resolved_persona, w, h)
        
        # translated（translated）
        status_msg = "no_llm_required" if not llm_mode_requires_quota else ("model_generated" if not _content_fallback else "fallback_used")
        
        prev_headers = {
            "X-Cache-Hit": "1" if cache_hit else "0",
            "X-Preview-Bypass": "1" if no_cache == 1 else "0",
            "X-Preview-Status": status_msg,
            "X-Llm-Required": "1" if llm_mode_requires_quota else "0",
        }
        ch = _chrome_header_value(chrome_meta)
        if ch:
            prev_headers["X-InkSight-Chrome"] = ch
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers=prev_headers,
        )
    except (OSError, RuntimeError, TypeError, ValueError, UnidentifiedImageError):
        logger.exception("Exception occurred during preview")
        err_img = render_error(mac=mac or "unknown", screen_w=w, screen_h=h)
        return Response(
            content=image_to_png_bytes(err_img),
            media_type="image/png",
            status_code=500,
        )


@router.get("/preview/stream")
@limiter.limit("20/minute")
async def preview_stream(
    request: Request,
    v: Optional[float] = Query(default=None),
    mac: Optional[str] = Query(default=None),
    persona: Optional[str] = Query(default=None),
    city_override: Optional[str] = Query(default=None),
    mode_override: Optional[str] = Query(default=None),
    memo_text: Optional[str] = Query(default=None),
    w: int = Query(default=SCREEN_WIDTH, ge=100, le=1600),
    h: int = Query(default=SCREEN_HEIGHT, ge=100, le=1200),
    no_cache: Optional[int] = Query(default=None),
    colors: int = Query(default=2, ge=2, le=4),
    ui_language: Optional[str] = Query(default=None, description="Preview only: zh|en, overrides device mode_language"),
    x_device_token: Optional[str] = Header(default=None),
    x_inksight_llm_api_key: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    if mac:
        mac = validate_mac_param(mac)
        await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    
    # Get translated ID：translated，translated user_llm_config，translated owner / translated
    current_user_id = None
    try:
        from core.auth import get_current_user_optional

        current_user = await get_current_user_optional(request, ink_session)
        if current_user:
            current_user_id = current_user.get("user_id")
            logger.debug("[PREVIEW_STREAM] Current user_id=%s for preview (mac=%s)", current_user_id, mac)
    except Exception:
        logger.warning("[PREVIEW_STREAM] Failed to resolve current user for preview", exc_info=True)

    async def stream():
        try:
            yield _sse_event("status", {"stage": "generating", "message": "translated..."})
            effective_v = await resolve_preview_voltage(v, mac)
            parsed_mode_override = None
            if mode_override:
                try:
                    candidate = json.loads(mode_override)
                    if isinstance(candidate, dict):
                        parsed_mode_override = candidate
                except JSONDecodeError:
                    logger.warning("[PREVIEW_STREAM] Failed to parse mode_override JSON", exc_info=True)

            _ui_lang = (ui_language or "").strip().lower()
            _preview_ui_lang = _ui_lang if _ui_lang in ("zh", "en") else None
            (
                img,
                resolved_persona,
                cache_hit,
                _content_fallback,
                quota_exhausted,
                api_key_invalid,
                llm_mode_requires_quota,
                usage_source,
                chrome_meta,
            ) = await build_image(
                effective_v,
                mac,
                persona,
                screen_w=w,
                screen_h=h,
                skip_cache=(no_cache == 1),
                preview_city_override=(city_override.strip() if city_override else None),
                preview_mode_override=parsed_mode_override,
                preview_memo_text=(memo_text if isinstance(memo_text, str) else None),
                preview_ui_language=_preview_ui_lang,
                current_user_id=current_user_id,
                user_api_key=x_inksight_llm_api_key,
                colors=colors,
            )
            # translated API key invalid，translated
            if api_key_invalid:
                yield _sse_event("error", {
                    "error": "api_key_invalid",
                    "message": "translated API key invalidtranslated，translated API key config",
                })
                return
            # translated，translated
            if quota_exhausted:
                yield _sse_event("error", {
                    "error": "quota_exhausted",
                    "message": "translated，translatedGet translated",
                    "requires_invite_code": True,
                    "usage_source": usage_source,
                })
                return
            yield _sse_event("status", {"stage": "rendering", "message": "translated..."})
            png_bytes = image_to_png_bytes(img)
            data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
            # Keep SSE result payload aligned with /preview headers for UI.
            status_msg = (
                "no_llm_required"
                if not llm_mode_requires_quota
                else ("model_generated" if not _content_fallback else "fallback_used")
            )
            result_payload = {
                "stage": "done",
                "message": "translated",
                "persona": resolved_persona,
                "cache_hit": cache_hit,
                "usage_source": usage_source,
                "image_url": data_url,
                "preview_status": status_msg,
                "llm_required": bool(llm_mode_requires_quota),
            }
            if chrome_meta is not None:
                result_payload["chrome"] = chrome_meta
            yield _sse_event("result", result_payload)
        except (OSError, RuntimeError, TypeError, ValueError, UnidentifiedImageError) as exc:
            logger.exception("[PREVIEW_STREAM] Streaming preview failed")
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
