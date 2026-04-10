from __future__ import annotations

import re
from core import db_adapter as aiosqlite
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import JSONResponse

from api.shared import require_membership_access
from core.auth import require_user, validate_mac_param
from core.content import _call_llm
from core.config_store import (
    approve_access_request,
    bind_device,
    delete_user_llm_config,
    get_device_members,
    get_device_owner,
    get_pending_requests_for_owner,
    get_user_api_quota,
    init_user_api_quota,
    get_user_by_username,
    get_user_devices,
    get_user_llm_config,
    reject_access_request,
    revoke_device_member,
    save_user_llm_config,
    share_device_with_user,
    unbind_device,
)
from core.db import get_main_db
from core.email import send_verification_code, verify_code

router = APIRouter(tags=["user"])

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@router.get("/user/devices")
async def list_user_devices(user_id: int = Depends(require_user)):
    return {"devices": await get_user_devices(user_id)}


@router.post("/user/devices")
async def bind_user_device(body: dict, user_id: int = Depends(require_user)):
    mac = validate_mac_param((body.get("mac") or "").strip().upper())
    nickname = (body.get("nickname") or "").strip()
    if not mac:
        return JSONResponse({"error": "MAC address is required"}, status_code=400)
    return {"ok": True, **await bind_device(user_id, mac, nickname)}


@router.delete("/user/devices/{mac}")
async def unbind_user_device(mac: str, user_id: int = Depends(require_user)):
    result = await unbind_device(user_id, mac.upper())
    if result == "not_found":
        return JSONResponse({"error": "Device is not bound"}, status_code=404)
    if result == "owner_has_members":
        return JSONResponse({"error": "Owner still has shared members and cannot unbind"}, status_code=409)
    return {"ok": True}


@router.get("/user/devices/requests")
async def list_device_requests(user_id: int = Depends(require_user)):
    return {"requests": await get_pending_requests_for_owner(user_id)}


@router.post("/user/devices/requests/{request_id}/approve")
async def approve_device_request(request_id: int, user_id: int = Depends(require_user)):
    membership = await approve_access_request(request_id, user_id)
    if not membership:
        return JSONResponse({"error": "Request does not exist or cannot be approved"}, status_code=404)
    return {"ok": True, "membership": membership}


@router.post("/user/devices/requests/{request_id}/reject")
async def reject_device_request(request_id: int, user_id: int = Depends(require_user)):
    ok = await reject_access_request(request_id, user_id)
    if not ok:
        return JSONResponse({"error": "Request does not exist or cannot be rejected"}, status_code=404)
    return {"ok": True}


@router.get("/user/devices/{mac}/members")
async def list_device_members_route(
    mac: str,
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
):
    await require_membership_access(request, mac.upper(), ink_session)
    members = await get_device_members(mac.upper())
    owner = await get_device_owner(mac.upper())
    return {"mac": mac.upper(), "members": members, "owner_user_id": owner["user_id"] if owner else None}


@router.post("/user/devices/{mac}/share")
async def share_device_access(
    mac: str,
    body: dict,
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
):
    owner = await require_membership_access(request, mac.upper(), ink_session, owner_only=True)
    username = str(body.get("username") or "").strip()
    if not username:
        return JSONResponse({"error": "Username is required"}, status_code=400)
    target_user = await get_user_by_username(username)
    if not target_user:
        return JSONResponse({"error": "Target user not found"}, status_code=404)
    return {"ok": True, **await share_device_with_user(owner["user_id"], mac.upper(), target_user["id"])}


@router.delete("/user/devices/{mac}/members/{target_user_id}")
async def remove_device_member(
    mac: str,
    target_user_id: int,
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
):
    owner = await require_membership_access(request, mac.upper(), ink_session, owner_only=True)
    ok = await revoke_device_member(owner["user_id"], mac.upper(), target_user_id)
    if not ok:
        return JSONResponse({"error": "Member does not exist or cannot be removed"}, status_code=404)
    return {"ok": True}


def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "****" if key else ""
    return key[:4] + "****" + key[-4:]


@router.get("/user/profile")
async def get_user_profile(user_id: int = Depends(require_user)):
    db = await get_main_db()

    cursor = await db.execute(
        "SELECT id, username, phone, email, role FROM users WHERE id = ?",
        (user_id,),
    )
    user_row = await cursor.fetchone()
    if not user_row:
        return JSONResponse({"error": "User not found"}, status_code=404)

    quota = await get_user_api_quota(user_id)
    if quota is None:
        # Backfill legacy users that don't yet have an api_quotas row.
        await init_user_api_quota(user_id, free_quota=50)
        quota = await get_user_api_quota(user_id)

    llm_config = await get_user_llm_config(user_id)
    llm_config_updated_at = ""
    if llm_config:
        for k in ("api_key", "image_api_key"):
            if llm_config.get(k):
                llm_config[k] = _mask_key(llm_config[k])
        try:
            cursor2 = await db.execute("SELECT updated_at FROM user_llm_config WHERE user_id = ?", (user_id,))
            row2 = await cursor2.fetchone()
            llm_config_updated_at = row2[0] if row2 and row2[0] else ""
        except Exception:
            llm_config_updated_at = ""

    return {
        "user_id": user_row[0],
        "username": user_row[1],
        "phone": user_row[2] or "",
        "email": user_row[3] or "",
        "role": user_row[4] or "user",
        "free_quota_remaining": quota.get("free_quota_remaining", 0) if quota else 0,
        "llm_config": llm_config,
        "llm_config_updated_at": llm_config_updated_at,
    }


@router.put("/user/profile/llm")
async def save_user_llm_config_route(body: dict, user_id: int = Depends(require_user)):
    """Save user-level LLM configuration."""
    llm_access_mode = (body.get("llm_access_mode") or "preset").strip().lower()
    if llm_access_mode not in {"preset", "custom_openai"}:
        return JSONResponse({"error": "llm_access_mode supports only preset or custom_openai"}, status_code=400)
    provider = (body.get("provider") or "deepseek").strip().lower()
    if llm_access_mode == "custom_openai":
        provider = "openai_compat"
    if provider not in {"deepseek", "openai_compat"}:
        return JSONResponse({"error": "provider supports only deepseek or openai_compat"}, status_code=400)
    model = (body.get("model") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    base_url = (body.get("base_url") or "").strip() if llm_access_mode == "custom_openai" else ""
    image_provider = "deepseek"
    image_model = (body.get("image_model") or "").strip()
    image_api_key = ""
    image_base_url = ""
    
    ok = await save_user_llm_config(
        user_id,
        llm_access_mode,
        provider,
        model,
        api_key,
        base_url,
        image_provider,
        image_model,
        image_api_key,
        image_base_url=image_base_url,
    )
    if not ok:
        return JSONResponse({"error": "Failed to save configuration"}, status_code=500)
    
    return {"ok": True, "message": "Configuration saved"}


@router.post("/user/profile/llm/test")
async def test_user_llm_config_route(body: dict, user_id: int = Depends(require_user)):
    llm_access_mode = (body.get("llm_access_mode") or "preset").strip().lower()
    if llm_access_mode not in {"preset", "custom_openai"}:
        return JSONResponse({"error": "Invalid llm_access_mode"}, status_code=400)

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


@router.delete("/user/profile/llm")
async def delete_user_llm_config_route(user_id: int = Depends(require_user)):
    """Delete user-level LLM configuration (BYOK)."""
    deleted = await delete_user_llm_config(user_id)
    # Idempotent: return ok even if there was no existing config.
    return {"ok": True, "deleted": bool(deleted), "message": "Configuration deleted"}


@router.post("/user/redeem")
async def redeem_invite_code(body: dict, user_id: int = Depends(require_user)):
    """Redeem an invite code to add 50 free LLM calls for the current user."""
    invite_code = (body.get("invite_code") or "").strip()
    
    if not invite_code:
        return JSONResponse({"error": "Invite code is required"}, status_code=400)
    
    db = await get_main_db()
    
    try:
        # Start an explicit transaction for atomic redeem flow.
        await db.execute("BEGIN")
        
        # 1) Validate invite code exists and is unused.
        cursor = await db.execute(
            "SELECT id, code, is_used FROM invitation_codes WHERE code = ? LIMIT 1",
            (invite_code,),
        )
        row = await cursor.fetchone()
        if not row:
            await db.rollback()
            return JSONResponse({"error": "Invalid invite code"}, status_code=400)
        if row[2]:  # is_used
            await db.rollback()
            return JSONResponse({"error": "Invite code has already been used"}, status_code=409)
        
        # 2) Mark invite code as used by current user.
        await db.execute(
            """
            UPDATE invitation_codes
            SET is_used = 1, used_by_user_id = ?
            WHERE code = ?
            """,
            (user_id, invite_code),
        )
        
        # 3) Add free quota (+50 calls).
        # Ensure api_quotas row exists first.
        await db.execute(
            """
            INSERT OR IGNORE INTO api_quotas (user_id, total_calls_made, free_quota_remaining)
            VALUES (?, 0, 0)
            """,
            (user_id,),
        )
        # Atomic increment to avoid race conditions.
        await db.execute(
            """
            UPDATE api_quotas
            SET free_quota_remaining = free_quota_remaining + 50
            WHERE user_id = ?
            """,
            (user_id,),
        )
        
        await db.commit()
        
        # Fetch updated quota.
        quota = await get_user_api_quota(user_id)
        return {
            "ok": True,
            "message": "Invite code redeemed successfully. You have received 50 free LLM calls.",
            "free_quota_remaining": quota.get("free_quota_remaining", 0) if quota else 0,
        }
    except aiosqlite.IntegrityError:
        await db.rollback()
        return JSONResponse({"error": "Invite code has already been used"}, status_code=409)
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[REDEEM_INVITE] Failed to redeem invite code: {e}", exc_info=True)
        return JSONResponse({"error": "Redemption failed, please try again later"}, status_code=500)


@router.post("/user/bind-email/send-code")
async def bind_email_send_code(body: dict, user_id: int = Depends(require_user)):
    """Send a verification code to the new email address."""
    email = (body.get("email") or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "Invalid email format"}, status_code=400)

    db = await get_main_db()
    cursor = await db.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id))
    if await cursor.fetchone():
        return JSONResponse({"error": "This email is already used by another account"}, status_code=409)

    ok, message = await send_verification_code(email)
    if not ok:
        return JSONResponse({"error": message}, status_code=429)
    return {"ok": True, "message": message}


@router.post("/user/bind-email")
async def bind_email(body: dict, user_id: int = Depends(require_user)):
    """Verify code and bind email to the current user."""
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()

    if not email or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "Invalid email format"}, status_code=400)
    if not code:
        return JSONResponse({"error": "Verification code is required"}, status_code=400)
    if not verify_code(email, code):
        return JSONResponse({"error": "Verification code is invalid or expired"}, status_code=400)

    db = await get_main_db()
    cursor = await db.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id))
    if await cursor.fetchone():
        return JSONResponse({"error": "This email is already used by another account"}, status_code=409)

    await db.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
    await db.commit()
    return {"ok": True, "message": "Email bound successfully"}
