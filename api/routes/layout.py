"""Layout builder API (grid editor contract: validate, available modes, save stub)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from api.shared import logger
from core.auth import optional_user
from core.mode_registry import get_registry
from core.surface_grid import validate_layout

router = APIRouter(tags=["layout"])


async def _load_registry_for_mac(mac: Optional[str], user_id: Optional[int]) -> None:
    if user_id is None or not mac:
        return
    from core.config_store import has_active_membership

    registry = get_registry()
    mac_u = mac.upper()
    if await has_active_membership(mac_u, user_id):
        registry.unregister_device_modes(mac_u)
        await registry.load_user_custom_modes(user_id, mac_u)


def _normalize_validate_body(body: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, dict[str, Any] | None]:
    """Accept ``{ grid, slots, modes? }`` or ``{ layout: { grid, slots }, modes? }``."""
    if not isinstance(body, dict):
        return None, None, None
    modes_in = body.get("modes")
    modes_list: list[dict[str, Any]] | None = None
    if isinstance(modes_in, list):
        modes_list = [m for m in modes_in if isinstance(m, dict)]
    elif modes_in is None:
        modes_list = None
    else:
        modes_list = []

    grid = body.get("grid")
    slots = body.get("slots")
    lg = body.get("layout")
    if isinstance(lg, dict):
        grid = grid or lg.get("grid")
        slots = slots or lg.get("slots")
    if not isinstance(grid, dict) or not isinstance(slots, list):
        return None, modes_list, None
    return grid, modes_list, {"grid": grid, "slots": slots}


@router.get("/layouts/modes")
async def get_layout_editor_modes(
    mac: Optional[str] = Query(None, description="Device MAC for custom modes"),
    user_id: Optional[int] = Depends(optional_user),
):
    """Simplified mode list for the grid editor: id, name, supported_slot_types."""
    await _load_registry_for_mac(mac, user_id)
    registry = get_registry()
    mac_norm = mac.upper() if mac else None
    catalog = []
    seen: set[str] = set()
    for info in registry.list_modes(mac_norm):
        mid = info.mode_id.upper()
        if mid in seen:
            continue
        seen.add(mid)
        jm = registry.get_json_mode(mid, mac_norm, language="zh")
        sst: list[str] | None = None
        if jm and isinstance(jm.definition, dict):
            raw = jm.definition.get("supported_slot_types")
            if isinstance(raw, list):
                sst = [str(x).strip().upper() for x in raw if isinstance(x, str) and str(x).strip()]
        catalog.append(
            {
                "id": mid,
                "name": info.display_name or mid,
                "supported_slot_types": sst or [],
            }
        )
    return catalog


@router.post("/layouts/validate")
async def post_layouts_validate(
    body: dict,
    mac: Optional[str] = Query(None, description="Device MAC for custom mode definitions"),
    user_id: Optional[int] = Depends(optional_user),
):
    """Validate ``{ grid, slots, modes? }`` (or wrapped ``layout``)."""
    await _load_registry_for_mac(mac, user_id)
    grid, modes_list, layout = _normalize_validate_body(body)
    if layout is None:
        return {"valid": False, "errors": [{"code": "INVALID_LAYOUT", "message": "expected grid and slots"}]}
    registry = get_registry()
    mac_norm = mac.upper() if mac else None

    def get_mode_definition(mid: str):
        jm = registry.get_json_mode(mid.upper(), mac_norm, language="zh")
        return jm.definition if jm else None

    try:
        if modes_list is not None:
            return validate_layout(layout, modes=modes_list)
        return validate_layout(layout, modes=None, get_mode_definition=get_mode_definition)
    except Exception as e:
        logger.exception("[layouts/validate] failed")
        return {"valid": False, "errors": [{"code": "INVALID_LAYOUT", "message": str(e)}]}


@router.post("/layout/validate")
async def post_validate_layout_legacy(
    body: dict,
    mac: Optional[str] = Query(None),
    user_id: Optional[int] = Depends(optional_user),
):
    """Legacy: body may use ``layout`` key. Delegates to :func:`post_layouts_validate`."""
    if isinstance(body, dict) and "grid" not in body and isinstance(body.get("layout"), dict):
        body = {**body["layout"], "modes": body.get("modes")}
    return await post_layouts_validate(body, mac=mac, user_id=user_id)


@router.post("/layouts")
async def post_layout_save(
    body: dict,
    mac: Optional[str] = Query(None),
    user_id: Optional[int] = Depends(optional_user),
):
    """Validate layout; MVP returns an id without server-side persistence (caller saves via device config)."""
    result = await post_layouts_validate(body, mac=mac, user_id=user_id)
    if not result.get("valid"):
        from fastapi.responses import JSONResponse

        return JSONResponse(result, status_code=422)
    lid = f"layout_{uuid.uuid4().hex[:12]}"
    return {"id": lid, "saved": True, "layout": _normalize_validate_body(body)[2]}


@router.put("/layouts/{layout_id}")
async def put_layout_update(
    layout_id: str,
    body: dict,
    mac: Optional[str] = Query(None),
    user_id: Optional[int] = Depends(optional_user),
):
    result = await post_layouts_validate(body, mac=mac, user_id=user_id)
    if not result.get("valid"):
        from fastapi.responses import JSONResponse

        return JSONResponse(result, status_code=422)
    return {"id": layout_id, "saved": True, "layout": _normalize_validate_body(body)[2]}


@router.get("/layouts/{layout_id}")
async def get_layout_by_id(layout_id: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {"error": "not_implemented", "message": "Server-side layout storage is not enabled; use device surface config."},
        status_code=501,
    )
