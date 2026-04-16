from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, Request
from fastapi.responses import JSONResponse

from api.shared import ensure_web_or_device_access, logger
from core.auth import is_admin_authorized, require_admin, validate_mac_param
from core.content import _call_llm
from core.config_store import (
    activate_config,
    get_active_config,
    get_or_create_alert_token,
    get_config_history,
    save_config,
    set_pending_refresh,
    update_focus_listening,
)
from core.schemas import ConfigRequest, ConfigSaveResponse

router = APIRouter(tags=["config"])


@router.post("/config", response_model=ConfigSaveResponse)
async def post_config(
    request: Request,
    body: ConfigRequest,
    x_inksight_client: Optional[str] = Header(default=None),
    x_device_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    data = body.model_dump()
    mac = data["mac"]
    if not is_admin_authorized(authorization):
        await ensure_web_or_device_access(
            request,
            mac,
            x_device_token,
            ink_session,
            allow_device_token=True,
        )
    modes = data.get("modes", [])
    logger.info(
        "[CONFIG SAVE REQUEST] source=%s mac=%s modes=%s refresh_strategy=%s",
        x_inksight_client or "unknown",
        mac,
        len(modes) if isinstance(modes, list) else 0,
        data.get("refresh_strategy"),
    )
    config_id = await save_config(mac, data)
    await set_pending_refresh(mac, True)

    saved_config = await get_active_config(mac)
    if saved_config:
        logger.info(
            "[CONFIG VERIFY] Saved config id=%s refresh_strategy=%s",
            saved_config.get("id"),
            saved_config.get("refresh_strategy"),
        )

    return ConfigSaveResponse(ok=True, config_id=config_id)


@router.get("/config/{mac}")
async def get_config(
    mac: str,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    # FastAPI translated URL translated，translated MAC translated
    logger.debug(f"[CONFIG GET] Received MAC: {mac} (raw)")
    try:
        mac = validate_mac_param(mac)
        logger.debug(f"[CONFIG GET] Validated MAC: {mac}")
    except Exception as e:
        logger.warning(f"[CONFIG GET] Invalid MAC format: {mac}, error: {e}")
        raise
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    config = await get_active_config(mac)
    if not config:
        return JSONResponse({"error": "no config found"}, status_code=404)
    config.pop("llm_api_key", None)
    config.pop("image_api_key", None)
    return config


@router.get("/config/{mac}/history")
async def get_config_history_route(
    mac: str,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    mac = validate_mac_param(mac)
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    history = await get_config_history(mac)
    for cfg in history:
        cfg.pop("llm_api_key", None)
        cfg.pop("image_api_key", None)
    return {"mac": mac, "configs": history}


@router.put("/config/{mac}/activate/{config_id}")
async def activate_config_route(
    mac: str,
    config_id: int,
    admin_auth: None = Depends(require_admin),
):
    mac = validate_mac_param(mac)
    ok = await activate_config(mac, config_id)
    if not ok:
        return JSONResponse({"error": "config not found"}, status_code=404)
    return {"ok": True}


@router.patch("/config/{mac}/focus-listening")
async def patch_focus_listening(
    mac: str,
    request: Request,
    enabled: bool = True,
    x_device_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    """translated：translated focus_listening；translated alert_token translated。"""
    mac = validate_mac_param(mac)
    if not is_admin_authorized(authorization):
        await ensure_web_or_device_access(
            request,
            mac,
            x_device_token,
            ink_session,
            allow_device_token=True,
        )

    ok = await update_focus_listening(mac, bool(enabled))
    if not ok:
        return JSONResponse({"error": "no_active_config"}, status_code=404)

    token = None
    if enabled:
        token = await get_or_create_alert_token(mac, regenerate=False)

    return {"ok": True, "is_focus_listening": bool(enabled), "alert_token": token}


def _mask_key(raw: str) -> str:
    v = (raw or "").strip()
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}...{v[-4:]}"


def _llm_key_payload_from_active(cfg: dict, mac: str) -> dict:
    return {
        "mac": mac,
        "llm_access_mode": str(cfg.get("llm_access_mode", "preset") or "preset"),
        "provider": str(cfg.get("llm_provider", "deepseek") or "deepseek"),
        "model": str(cfg.get("llm_model", "deepseek-chat") or "deepseek-chat"),
        "api_key": str(cfg.get("llm_api_key", "") or ""),
        "base_url": str(cfg.get("llm_base_url", "") or ""),
        "has_api_key": bool(str(cfg.get("llm_api_key", "") or "").strip()),
        "api_key_masked": _mask_key(str(cfg.get("llm_api_key", "") or "")),
    }


@router.get("/config/{mac}/llm-key")
async def get_config_llm_key(
    mac: str,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    mac = validate_mac_param(mac)
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    cfg = await get_active_config(mac)
    if not cfg:
        return JSONResponse({"error": "no config found"}, status_code=404)
    return _llm_key_payload_from_active(cfg, mac)


@router.put("/config/{mac}/llm-key")
async def put_config_llm_key(
    mac: str,
    body: dict,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    mac = validate_mac_param(mac)
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    cfg = await get_active_config(mac)
    if not cfg:
        return JSONResponse({"error": "no config found"}, status_code=404)

    cfg_payload = dict(cfg)
    cfg_payload["mac"] = mac
    cfg_payload["llmAccessMode"] = str(body.get("llm_access_mode") or "preset").strip().lower() or "preset"
    cfg_payload["llmProvider"] = str(body.get("provider") or cfg.get("llm_provider") or "deepseek").strip().lower() or "deepseek"
    cfg_payload["llmModel"] = str(body.get("model") or cfg.get("llm_model") or "deepseek-chat").strip() or "deepseek-chat"
    incoming_key = str(body.get("api_key") or "").strip()
    cfg_payload["llmApiKey"] = incoming_key if incoming_key else str(cfg.get("llm_api_key") or "")
    cfg_payload["llmBaseUrl"] = str(body.get("base_url") or "").strip()
    await save_config(mac, cfg_payload)
    latest = await get_active_config(mac)
    if not latest:
        return JSONResponse({"error": "failed to save llm key"}, status_code=500)
    return {"ok": True, **_llm_key_payload_from_active(latest, mac)}


@router.delete("/config/{mac}/llm-key")
async def delete_config_llm_key(
    mac: str,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    mac = validate_mac_param(mac)
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    cfg = await get_active_config(mac)
    if not cfg:
        return JSONResponse({"error": "no config found"}, status_code=404)
    cfg_payload = dict(cfg)
    cfg_payload["mac"] = mac
    cfg_payload["llmApiKey"] = ""
    cfg_payload["llmBaseUrl"] = ""
    await save_config(mac, cfg_payload)
    return {"ok": True}


@router.post("/config/{mac}/llm-key/test")
async def test_config_llm_key(
    mac: str,
    body: dict,
    request: Request,
    x_device_token: Optional[str] = Header(default=None),
    ink_session: Optional[str] = Cookie(default=None),
):
    mac = validate_mac_param(mac)
    await ensure_web_or_device_access(request, mac, x_device_token, ink_session)
    llm_access_mode = (body.get("llm_access_mode") or "preset").strip().lower()
    provider = (body.get("provider") or "deepseek").strip().lower()
    if llm_access_mode == "custom_openai":
        provider = "openai_compat"
    model = (body.get("model") or "").strip() or ("gpt-4o-mini" if llm_access_mode == "custom_openai" else "deepseek-chat")
    api_key = (body.get("api_key") or "").strip()
    base_url = (body.get("base_url") or "").strip() if llm_access_mode == "custom_openai" else ""
    if not api_key:
        return JSONResponse({"error": "api_key is required"}, status_code=400)
    if llm_access_mode == "custom_openai" and not base_url:
        return JSONResponse({"error": "base_url is required for custom_openai"}, status_code=400)
    try:
        await _call_llm(
            provider=provider,
            model=model,
            prompt="Return exactly: pong",
            temperature=0.0,
            max_tokens=16,
            api_key=api_key,
            base_url=(base_url or None),
        )
        return {"ok": True, "message": "API key test passed"}
    except Exception as exc:
        return JSONResponse({"error": f"API key test failed: {exc}"}, status_code=400)
