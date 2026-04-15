from __future__ import annotations

import io
import json as jsonlib
from pathlib import Path
import os
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAIError

from api.shared import logger
from core.auth import require_admin, require_user, optional_user
from core.config import SCREEN_HEIGHT, SCREEN_WIDTH, get_default_llm_model_for_provider
from core.config_store import remove_mode_from_all_configs
from core.context import get_date_context, get_weather
from core.mode_registry import (
    CUSTOM_JSON_DIR,
    _validate_mode_def_with_error,
    get_registry,
)
from core.mode_catalog import BUILTIN_CATALOG, builtin_catalog_map
from core.config_store import (
    get_user_custom_modes,
    get_custom_mode,
    save_custom_mode,
    delete_custom_mode,
    get_user_api_quota,
    consume_user_free_quota,
    get_quota_owner_for_mac,
    get_user_role,
)

router = APIRouter(tags=["modes"])


def _billing_enabled() -> bool:
    """translated：INKSIGHT_BILLING_ENABLED=0 translated。"""
    value = os.getenv("INKSIGHT_BILLING_ENABLED", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


@router.get("/modes")
async def list_modes(
    mac: str = Query(None, description="Device MAC address to filter custom modes"),
    user_id: int = Depends(optional_user),
):
    """
    List all modes. If user is authenticated, return builtin modes + that user's custom modes for the specified device.
    Otherwise, return all builtin modes + legacy file-based custom modes (for backward compatibility).
    """
    
    registry = get_registry()
    modes = []
    
    # Add custom modes first (before listing from registry to ensure device isolation)
    if user_id is not None:
        # If mac is provided, validate device ownership
        if mac:
            from core.config_store import has_active_membership
            mac = mac.upper()
            if not await has_active_membership(mac, user_id):
                # Device doesn't belong to user, return only builtin modes
                # Still need to list builtin modes
                for info in registry.list_modes(mac):
                    if info.source != "custom":
                        modes.append({
                            "mode_id": info.mode_id,
                            "display_name": info.display_name,
                            "icon": info.icon,
                            "cacheable": info.cacheable,
                            "description": info.description,
                            "source": info.source,
                            "settings_schema": info.settings_schema,
                        })
                return {"modes": modes}
        
        # IMPORTANT: Before loading modes for this device, we need to ensure clean state
        # The registry is global, so we need to unregister all modes for this device first
        # to prevent seeing modes from other devices that were previously loaded
        if mac:
            # Unregister all modes for this device to ensure clean state
            registry.unregister_device_modes(mac)
        
        # Load user's custom modes into registry (for immediate use in rendering)
        # Only load modes for the specific device if mac is provided, to avoid loading modes from other devices
        await registry.load_user_custom_modes(user_id, mac)

        # Return only this user's custom modes from database (filtered by device if mac provided)
        # translated：translated user_id translated mac translated
        logger.info(
            "[MODES] list_modes DB query get_user_custom_modes(user_id=%s, mac=%s)",
            user_id,
            (mac or "").upper() if mac else None,
        )
        user_custom_modes = await get_user_custom_modes(user_id, mac)
        for mode_data in user_custom_modes:
            definition = mode_data["definition"]
            modes.append({
                "mode_id": mode_data["mode_id"],
                "display_name": definition.get("display_name", mode_data["mode_id"]),
                "icon": definition.get("icon", "star"),
                "cacheable": definition.get("cacheable", True),
                "description": definition.get("description", ""),
                "source": "custom",
                "settings_schema": definition.get("settings_schema", []),
                "mac": mode_data.get("mac"),
            })
    
    # Always include builtin modes (and any custom modes now in registry for this device)
    # After loading user's custom modes, list_modes will only return modes for this device
    for info in registry.list_modes(mac):
        if info.source != "custom":
            modes.append({
                "mode_id": info.mode_id,
                "display_name": info.display_name,
                "icon": info.icon,
                "cacheable": info.cacheable,
                "description": info.description,
                "source": info.source,
                "settings_schema": info.settings_schema,
            })
    # Custom modes are now stored in database only, not loaded from files
    # Removed backward compatibility for file-based custom modes
    
    return {"modes": modes}


@router.get("/modes/catalog")
async def mode_catalog(
    mac: str = Query(None, description="Device MAC address to filter custom modes"),
    user_id: int = Depends(optional_user),
):
    """
    Unified mode catalog for UIs (preview/config).

    - Builtin modes: grouped by a single source of truth in `core.mode_catalog`.
    - Custom modes: dynamic, always category="custom".
    """
    try:
        catalog = builtin_catalog_map()
        registry = get_registry()

        # Normalize mac if provided
        if mac:
            mac = mac.upper()

        def _supported_slot_types_for_mode(mode_id: str) -> list[str] | None:
            jm = registry.get_json_mode(mode_id.upper(), mac, language="zh")
            if not jm or not isinstance(jm.definition, dict):
                return None
            sst = jm.definition.get("supported_slot_types")
            if not isinstance(sst, list):
                return None
            out = [str(x).strip().upper() for x in sst if isinstance(x, str) and str(x).strip()]
            return out or None

        # Reuse list_modes logic (including device isolation) by loading custom modes here.
        if user_id is not None and mac:
            from core.config_store import has_active_membership

            if not await has_active_membership(mac, user_id):
                # Not a member: only builtin modes
                items = []
                for info in registry.list_modes(mac):
                    if info.source == "custom":
                        continue
                    cat = catalog.get(info.mode_id)
                    row = {
                        "mode_id": info.mode_id,
                        "source": info.source,
                        "category": (cat.category if cat else "more"),
                        "topic": (cat.topic if cat else "learning"),
                        "display_name": info.display_name,
                        "description": info.description,
                        "settings_schema": info.settings_schema or [],
                        "i18n": {
                            "zh": {
                                "name": (cat.zh.name if cat else info.display_name),
                                "tip": (cat.zh.tip if cat else info.description),
                            },
                            "en": {
                                "name": (cat.en.name if cat else info.display_name),
                                "tip": (cat.en.tip if cat else info.description),
                            },
                        },
                    }
                    sst = _supported_slot_types_for_mode(info.mode_id)
                    if sst:
                        row["supported_slot_types"] = sst
                    items.append(row)
                return {"items": items}

            # User has access: load their custom modes
            registry.unregister_device_modes(mac)
            await registry.load_user_custom_modes(user_id, mac)

        def _item_from_info(info):
            mid = info.mode_id
            if info.source == "custom":
                row = {
                    "mode_id": mid,
                    "source": info.source,
                    "category": "custom",
                    "topic": "custom",
                    "display_name": info.display_name,
                    "description": info.description,
                    "settings_schema": info.settings_schema or [],
                    "i18n": {
                        "zh": {"name": info.display_name, "tip": info.description},
                        "en": {"name": info.display_name, "tip": info.description},
                    },
                }
            else:
                cat = catalog.get(mid)
                row = {
                    "mode_id": mid,
                    "source": info.source,
                    "category": (cat.category if cat else "more"),
                    "topic": (cat.topic if cat else "learning"),
                    "display_name": info.display_name,
                    "description": info.description,
                    "settings_schema": info.settings_schema or [],
                    "i18n": {
                        "zh": {
                            "name": (cat.zh.name if cat else info.display_name),
                            "tip": (cat.zh.tip if cat else info.description),
                        },
                        "en": {
                            "name": (cat.en.name if cat else info.display_name),
                            "tip": (cat.en.tip if cat else info.description),
                        },
                    },
                }
            sst = _supported_slot_types_for_mode(mid)
            if sst:
                row["supported_slot_types"] = sst
            return row

        items: list[dict] = []

        # 1) Builtin modes in catalog order (stable UX)
        for cat_item in BUILTIN_CATALOG:
            info = registry.get_mode_info(cat_item.mode_id.upper())
            if not info or info.source == "custom":
                continue
            items.append(_item_from_info(info))

        emitted = {x["mode_id"] for x in items}

        # 2) Remaining non-custom modes not in catalog (fallback)
        for info in registry.list_modes(mac):
            if info.source == "custom":
                continue
            if info.mode_id in emitted:
                continue
            items.append(_item_from_info(info))
            emitted.add(info.mode_id)

        # 3) Custom modes (dynamic)
        if mac:
            for info in registry.list_modes(mac):
                if info.source != "custom":
                    continue
                items.append(_item_from_info(info))
        elif user_id is not None:
            # Device-free preview should only show the current user's actual
            # saved/installed custom modes from DB, not whatever custom entries
            # happen to remain in the global registry from other requests.
            user_custom_modes = await get_user_custom_modes(user_id, None)
            latest_by_mode_id: dict[str, dict] = {}
            for mode_data in user_custom_modes:
                mode_id = str(mode_data.get("mode_id") or "").upper().strip()
                definition = mode_data.get("definition") or {}
                if not mode_id or not isinstance(definition, dict):
                    continue
                existing = latest_by_mode_id.get(mode_id)
                updated_at = str(mode_data.get("updated_at") or "")
                if existing is None or updated_at > str(existing.get("updated_at") or ""):
                    latest_by_mode_id[mode_id] = mode_data

            for mode_id, mode_data in sorted(
                latest_by_mode_id.items(),
                key=lambda item: str(item[1].get("updated_at") or item[1].get("created_at") or ""),
                reverse=True,
            ):
                definition = mode_data["definition"]
                display_name = str(definition.get("display_name") or mode_id)
                description = str(definition.get("description") or "")
                settings_schema = definition.get("settings_schema") or []
                sst_raw = definition.get("supported_slot_types")
                sst_list = (
                    [str(x).strip().upper() for x in sst_raw if isinstance(x, str) and str(x).strip()]
                    if isinstance(sst_raw, list)
                    else None
                )
                row = {
                    "mode_id": mode_id,
                    "source": "custom",
                    "category": "custom",
                    "topic": "custom",
                    "display_name": display_name,
                    "description": description,
                    "settings_schema": settings_schema if isinstance(settings_schema, list) else [],
                    "i18n": {
                        "zh": {"name": display_name, "tip": description},
                        "en": {"name": display_name, "tip": description},
                    },
                }
                if sst_list:
                    row["supported_slot_types"] = sst_list
                items.append(row)

        return {"items": items}
    except Exception as e:
        logger.exception("[CATALOG] Error in mode_catalog endpoint")
        return JSONResponse({"error": str(e), "items": []}, status_code=500)


def _preview_payload(content: dict) -> dict:
    for key in ("quote", "text", "body", "summary", "question", "challenge", "interpretation"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return {"preview_text": value.strip()[:200], "content": content}
    return {"preview_text": "", "content": content}


@router.post("/modes/custom/preview")
async def custom_mode_preview(
    body: dict,
    user_id: int = Depends(optional_user),
):
    mode_def = body.get("mode_def", body)
    if not mode_def.get("mode_id"):
        mode_def = dict(mode_def, mode_id="PREVIEW")
    screen_w = body.get("w", SCREEN_WIDTH)
    screen_h = body.get("h", SCREEN_HEIGHT)
    colors = int(body.get("colors", 2))
    response_type = str(body.get("responseType", body.get("response_type", "image"))).strip().lower()

    ok, err = _validate_mode_def_with_error(mode_def, allow_raw_component_tree=False)
    if not ok:
        return JSONResponse({"error": err or "Invalid mode definition"}, status_code=400)

    # translated API key：translated，translated key
    user_api_key = None
    user_image_api_key = None
    user_llm_provider = None
    user_llm_model = None
    user_llm_base_url = None
    if user_id is not None:
        try:
            from core.config_store import get_user_llm_config

            user_cfg = await get_user_llm_config(user_id)
        except Exception:
            user_cfg = None
            logger.warning("[CUSTOM_PREVIEW] Failed to load user_llm_config for user_id=%s", user_id, exc_info=True)
        if user_cfg:
            user_api_key = (user_cfg.get("api_key") or "").strip() or None
            user_image_api_key = (user_cfg.get("image_api_key") or "").strip() or None
            candidate_provider = (user_cfg.get("provider") or "").strip().lower()
            user_llm_provider = candidate_provider if candidate_provider in {"deepseek", "openai"} else "deepseek"
            user_llm_model = (user_cfg.get("model") or "").strip() or None
            user_llm_base_url = None

    # translated：translated API key，translated（user_llm_config translated）
    device_api_key = None
    device_image_api_key = None

    try:
        from core.json_content import generate_json_mode_content
        from core.json_renderer import render_json_mode

        # ── translated（translated BILLING.md，custom preview translated） ──────────────
        # translated“translated”translated：translated user_id，translated mac owner，translated
        quota_user_id: int | None = None
        if user_id is not None:
            quota_user_id = user_id

        # translated API Key（profile / deviceconfig），translated True translated
        # effective_api_key translated None translated“translated Key”，translated
        effective_api_key = user_api_key if user_api_key is not None else device_api_key
        effective_image_api_key = user_image_api_key if user_image_api_key is not None else device_image_api_key
        using_user_key = effective_api_key is not None

        # translatedmodetranslated“translated LLM”（translated shared.build_image translated）
        llm_mode_requires_quota = False
        try:
            content_def = (mode_def.get("content") or {}) if isinstance(mode_def, dict) else {}
            ctype = content_def.get("type")
            if ctype in ("llm", "llm_json", "image_gen"):
                llm_mode_requires_quota = True
            elif ctype == "external_data":
                provider = content_def.get("provider", "")
                if provider == "briefing":
                    summarize = content_def.get("summarize", True)
                    include_insight = content_def.get("include_insight", True)
                    if summarize or include_insight:
                        llm_mode_requires_quota = True
            elif ctype == "composite":
                steps = content_def.get("steps", [])
                if isinstance(steps, list):
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        step_type = step.get("type")
                        if step_type in ("llm", "llm_json", "image_gen"):
                            llm_mode_requires_quota = True
                            break
                        if step_type == "external_data":
                            step_provider = step.get("provider", "")
                            if step_provider == "briefing":
                                step_summarize = step.get("summarize", True)
                                step_include_insight = step.get("include_insight", True)
                                if step_summarize or step_include_insight:
                                    llm_mode_requires_quota = True
                                    break
        except Exception:
            logger.warning("[CUSTOM_PREVIEW] Failed to detect llm requirements for custom mode", exc_info=True)

        # translated：translated Key translated quota_user_id translated
        if (
            _billing_enabled()
            and quota_user_id is not None
            and not using_user_key
            and llm_mode_requires_quota
        ):
            try:
                user_role = await get_user_role(quota_user_id)
            except Exception:
                user_role = None
            if user_role != "root":
                quota = await get_user_api_quota(quota_user_id)
                remaining = int(quota.get("free_quota_remaining") or 0) if quota else 0
                if remaining <= 0:
                    return JSONResponse(
                        {"error": "translated，translatedGet translated"},
                        status_code=402,
                    )

        date_ctx = await get_date_context()
        weather = await get_weather()
        content = await generate_json_mode_content(
            mode_def,
            date_ctx=date_ctx,
            date_str=date_ctx["date_str"],
            weather_str=weather["weather_str"],
            screen_w=screen_w,
            screen_h=screen_h,
            # translatedmodetranslated LLM translated provider + API key
            llm_provider=user_llm_provider,
            llm_model=user_llm_model,
            llm_base_url=user_llm_base_url,
            api_key=effective_api_key,
            image_api_key=effective_image_api_key,
        )

        # translated：translated Key、modetranslated LLM translatedsuccesstranslated LLM translated，root translated
        if (
            _billing_enabled()
            and quota_user_id is not None
            and not using_user_key
            and llm_mode_requires_quota
            and isinstance(content, dict)
            and content.get("_llm_used") is True
            and content.get("_llm_ok") is True
        ):
            try:
                user_role = await get_user_role(quota_user_id)
            except Exception:
                user_role = None
            if user_role != "root":
                await consume_user_free_quota(quota_user_id, amount=1)

        if response_type == "json":
            return {
                "ok": True,
                "mode_id": mode_def.get("mode_id", "PREVIEW"),
                **_preview_payload(content),
            }
        img = render_json_mode(
            mode_def,
            content,
            date_str=date_ctx["date_str"],
            weather_str=weather["weather_str"],
            battery_pct=100.0,
            screen_w=screen_w,
            screen_h=screen_h,
            colors=colors,
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.exception("[CUSTOM_PREVIEW] Preview failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/modes/custom")
async def create_custom_mode(body: dict, user_id: int = Depends(require_user)):
    """Create a custom mode.

    - With `mac`: persist to DB with user+device isolation.
    - Without `mac`: fallback to legacy file-based custom mode (mobile editor compatibility).
    """
    mode_id = body.get("mode_id", "").upper()
    mac = body.get("mac", "").strip().upper()
    if not mode_id:
        return JSONResponse({"error": "mode_id is required"}, status_code=400)
    ok, err = _validate_mode_def_with_error(body, allow_raw_component_tree=False)
    if not ok:
        return JSONResponse({"error": err or "Invalid mode definition"}, status_code=400)

    body["mode_id"] = mode_id
    registry = get_registry()
    if registry.is_builtin(mode_id):
        return JSONResponse(
            {"error": f"Cannot override builtin mode: {mode_id}"},
            status_code=409,
        )

    # Legacy path: no mac means file-based custom mode.
    if not mac:
        file_path = Path(CUSTOM_JSON_DIR) / f"{mode_id.lower()}.json"
        file_path.write_text(jsonlib.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        registry.unregister_custom(mode_id)
        loaded = registry.load_json_mode(str(file_path), source="custom")
        if not loaded:
            file_path.unlink(missing_ok=True)
            return JSONResponse({"error": "Failed to load mode definition"}, status_code=400)
        logger.info("[MODES] Created legacy custom mode %s for user %s", mode_id, user_id)
        return {"ok": True, "mode_id": mode_id}

    # Validate device ownership for DB path
    from core.config_store import has_active_membership
    if not await has_active_membership(mac, user_id):
        return JSONResponse(
            {"error": "device not found or access denied"},
            status_code=403
        )

    # Save to database (with device)
    success = await save_custom_mode(user_id, mode_id, body, mac)
    if not success:
        return JSONResponse({"error": "Failed to save custom mode"}, status_code=500)

    # Load into registry for immediate use
    registry.unregister_custom(mode_id, mac)
    loaded = registry.load_custom_mode_from_dict(mode_id, body, source="custom", mac=mac)
    if not loaded:
        # Rollback database entry
        await delete_custom_mode(user_id, mode_id, mac)
        return JSONResponse({"error": "Failed to load mode definition"}, status_code=400)

    logger.info(f"[MODES] Created custom mode {mode_id} for user {user_id} on device {mac}")
    return {"ok": True, "mode_id": mode_id}


@router.get("/modes/custom/{mode_id}")
async def get_custom_mode_endpoint(
    mode_id: str,
    mac: str = Query(None, description="Device MAC address to filter custom modes"),
    user_id: int = Depends(require_user),
):
    """Get a custom mode for the current user and device.

    translated：
    - musttranslated mac；
    - translated“translatedmode”。
    """
    # Legacy path: no mac -> file-based custom mode.
    if not mac:
        registry = get_registry()
        mode = registry.get_json_mode(mode_id.upper())
        if not mode or mode.info.source != "custom":
            return JSONResponse({"error": "Custom mode not found"}, status_code=404)
        return mode.definition

    mode_data = await get_custom_mode(user_id, mode_id, mac)
    if not mode_data:
        return JSONResponse({"error": "Custom mode not found"}, status_code=404)
    return mode_data["definition"]


@router.delete("/modes/custom/{mode_id}")
async def delete_custom_mode_endpoint(
    mode_id: str,
    mac: str = Query(None, description="Device MAC address to filter custom modes"),
    user_id: int = Depends(require_user),
):
    """Delete a custom mode for the current user, optionally filtered by device."""
    normalized = mode_id.upper()
    
    registry = get_registry()

    # Legacy path: no mac -> file-based custom mode.
    if not mac:
        mode = registry.get_json_mode(normalized)
        if not mode or mode.info.source != "custom":
            return JSONResponse({"error": "Custom mode not found"}, status_code=404)
        registry.unregister_custom(normalized)
        if mode.file_path:
            Path(mode.file_path).unlink(missing_ok=True)
        cleaned_configs = await remove_mode_from_all_configs(normalized, None)
        logger.info(
            "[MODES] Deleted legacy custom mode %s for user %s, cleaned_configs=%s",
            normalized,
            user_id,
            cleaned_configs,
        )
        return {"ok": True, "mode_id": normalized, "cleaned_configs": cleaned_configs}

    # DB path
    deleted = await delete_custom_mode(user_id, normalized, mac)
    if not deleted:
        return JSONResponse({"error": "Custom mode not found"}, status_code=404)

    registry.unregister_custom(normalized, mac)
    cleaned_configs = await remove_mode_from_all_configs(normalized, mac)
    logger.info(
        "[MODES] Deleted custom mode %s for user %s on device %s, cleaned_configs=%s",
        normalized,
        user_id,
        mac,
        cleaned_configs,
    )
    return {"ok": True, "mode_id": normalized, "cleaned_configs": cleaned_configs}


@router.post("/modes/generate")
async def generate_mode(
    body: dict,
    user_id: int = Depends(optional_user),
    admin_auth: None = Depends(require_admin),
):
    description = body.get("description", "").strip()
    if not description:
        return JSONResponse({"error": "description is required"}, status_code=400)
    if len(description) > 2000:
        return JSONResponse({"error": "description too long (max 2000 chars)"}, status_code=400)

    image_base64 = body.get("image_base64")
    if image_base64 and len(image_base64) > 5 * 1024 * 1024:
        return JSONResponse({"error": "image too large (max 4MB)"}, status_code=400)

    # translated API key & provider：translated，translated body translated
    user_api_key = None
    user_llm_provider = None
    user_llm_model = None
    user_llm_base_url = None
    if user_id is not None:
        try:
            from core.config_store import get_user_llm_config

            user_cfg = await get_user_llm_config(user_id)
        except Exception:
            user_cfg = None
            logger.warning("[MODE_GEN] Failed to load user_llm_config for user_id=%s", user_id, exc_info=True)
        if user_cfg:
            user_api_key = (user_cfg.get("api_key") or "").strip() or None
            candidate_provider = (user_cfg.get("provider") or "").strip().lower()
            user_llm_provider = candidate_provider if candidate_provider in {"deepseek", "openai"} else "deepseek"
            # translatedGet by  provider translateddefaulttranslated，translated profile translated model；
            # translated model，translated base_model translateddefault。
            user_llm_model = (user_cfg.get("model") or "").strip() or None
            user_llm_base_url = None

    # translated：translated API key，translated（user_llm_config translated）
    effective_api_key = user_api_key
    using_user_key = effective_api_key is not None

    # ── translated（AI generatemodetranslated BILLING.md translated） ──────────────────────────
    quota_user_id: int | None = None
    if user_id is not None:
        quota_user_id = user_id

    if _billing_enabled() and quota_user_id is not None and not using_user_key:
        try:
            user_role = await get_user_role(quota_user_id)
        except Exception:
            user_role = None
        if user_role != "root":
            quota = await get_user_api_quota(quota_user_id)
            remaining = int(quota.get("free_quota_remaining") or 0) if quota else 0
            if remaining <= 0:
                return JSONResponse(
                    {"error": "translated，translatedGet translated"},
                    status_code=402,
                )

    from core.mode_generator import generate_mode_definition

    try:
        # generatemodetranslated，LLM provider/model **musttranslated**：
        # 1. translated（profile translated provider / model）
        # 2. translated body translated provider / model
        # 3. translatedGet by translated provider translateddefaulttranslated
        provider_from_body = (body.get("provider") or "").strip() or None
        model_from_body = (body.get("model") or "").strip() or None

        # DeepSeek/OpenAI-only backend.
        candidate_provider = (user_llm_provider or provider_from_body or "deepseek").strip().lower()
        effective_provider = candidate_provider if candidate_provider in {"deepseek", "openai"} else "deepseek"

        # model：userconfig > body > Get by translated provider translateddefaulttranslated
        base_model = get_default_llm_model_for_provider(effective_provider)
        effective_model = user_llm_model or model_from_body or base_model
        # translated：translated provider/model translated user_cfg
        logger.info(
            "[GENERATE_MODE_DEBUG] user_id=%s user_cfg=%s body_provider=%s body_model=%s "
            "effective_provider=%s effective_model=%s using_user_key=%s",
            user_id,
            user_cfg,
            provider_from_body,
            model_from_body,
            effective_provider,
            effective_model,
            using_user_key,
        )

        result = await generate_mode_definition(
            description=description,
            image_base64=image_base64,
            provider=effective_provider,
            model=effective_model,
            api_key=effective_api_key,
            base_url=None,
        )
        # successtranslated（translated Key，root translated）
        if _billing_enabled() and quota_user_id is not None and not using_user_key:
            try:
                user_role = await get_user_role(quota_user_id)
            except Exception:
                user_role = None
            if user_role != "root":
                await consume_user_free_quota(quota_user_id, amount=1)
        return result
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except (jsonlib.JSONDecodeError, OSError, OpenAIError, RuntimeError, TypeError) as exc:
        logger.exception("[MODE_GEN] Failed to generate mode")
        return JSONResponse(
            {"error": f"generatefailed: {type(exc).__name__}: {str(exc)[:200]}"},
            status_code=500,
        )
