from __future__ import annotations

import re
from datetime import datetime

from core import db_adapter as aiosqlite
import phonenumbers
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from phonenumbers.phonenumberutil import NumberParseException

from core.auth import clear_session_cookie, create_session_token, require_user, set_session_cookie
from core.config_store import authenticate_user, _hash_password, get_user_api_quota
from core.db import execute_insert_returning_id, get_main_db
from core.email import send_verification_code, verify_code

router = APIRouter(tags=["auth"])


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

_COMMON_PHONE_REGIONS = {
    "CN", "US", "CA", "GB", "JP", "KR", "SG", "HK", "TW", "DE", "FR", "AU", "IN",
}


def _normalize_phone(phone: str, phone_region: str = "") -> str:
    raw = (phone or "").strip()
    if not raw:
        return ""
    region = (phone_region or "").strip().upper()
    if region and region not in _COMMON_PHONE_REGIONS:
        raise ValueError("unsupported_region")
    default_region = region or "CN"
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)
    except NumberParseException as exc:
        raise ValueError("invalid_phone") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("invalid_phone")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _phone_lookup_candidates(normalized_phone: str) -> tuple[str, ...]:
    if not normalized_phone:
        return ()
    candidates = {normalized_phone}
    if normalized_phone.startswith("+86"):
        candidates.add(normalized_phone[3:])
    return tuple(candidates)


async def _phone_exists(db, normalized_phone: str) -> bool:
    if not normalized_phone:
        return False
    candidates = _phone_lookup_candidates(normalized_phone)
    cursor = await db.execute(
        f"SELECT 1 FROM users WHERE phone IN ({','.join('?' for _ in candidates)}) LIMIT 1",
        tuple(candidates),
    )
    return await cursor.fetchone() is not None


@router.post("/auth/register")
async def auth_register(body: dict, response: Response):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    phone = (body.get("phone") or "").strip()
    phone_region = (body.get("phone_region") or "").strip()
    email = (body.get("email") or "").strip()

    if not username or len(username) < 2 or len(username) > 30:
        return JSONResponse({"error": "translated 2-30 translated"}, status_code=400)
    if len(password) < 4:
        return JSONResponse({"error": "translated 4 translated"}, status_code=400)

    if not email:
        return JSONResponse({"error": "translated"}, status_code=400)
    if not _EMAIL_RE.match(email):
        return JSONResponse({"error": "translated"}, status_code=400)
    normalized_phone = ""
    if phone:
        try:
            normalized_phone = _normalize_phone(phone, phone_region)
        except ValueError:
            return JSONResponse({"error": "translated"}, status_code=400)

    db = await get_main_db()
    now = datetime.now().isoformat()
    pw_hash, _ = _hash_password(password)

    try:
        # translated，translated「translated -> translated」translated
        await db.execute("BEGIN")
        if normalized_phone and await _phone_exists(db, normalized_phone):
            await db.rollback()
            return JSONResponse({"error": "translated/translatedalready exists"}, status_code=409)

        # 1) translated（translated + translated/translated）
        user_id = await execute_insert_returning_id(
            db,
            """
            INSERT INTO users (username, password_hash, phone, email, role, created_at)
            VALUES (?, ?, ?, ?, 'user', ?)
            """,
            (
                username,
                pw_hash,
                normalized_phone or None,
                email or None,
                now,
            ),
        )

        # 2) translated API translated（translated 50 translated）
        initial_quota = 50
        await db.execute(
            """
            INSERT OR IGNORE INTO api_quotas (user_id, total_calls_made, free_quota_remaining)
            VALUES (?, 0, ?)
            """,
            (user_id, initial_quota),
        )

        await db.commit()
    except aiosqlite.IntegrityError:
        # translated / translated / translatedconflict
        await db.rollback()
        return JSONResponse({"error": "translated/translatedalready exists"}, status_code=409)
    except Exception:
        await db.rollback()
        raise

    token = create_session_token(user_id, username)
    set_session_cookie(response, token)
    return {"ok": True, "user_id": user_id, "username": username, "token": token}


@router.post("/auth/login")
async def auth_login(body: dict, response: Response):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = await authenticate_user(username, password)
    if not user:
        return JSONResponse({"error": "translated"}, status_code=401)
    token = create_session_token(user["id"], user["username"])
    set_session_cookie(response, token)
    return {"ok": True, "user_id": user["id"], "username": user["username"], "token": token}


@router.post("/auth/reset-password/send-code")
async def auth_reset_send_code(body: dict):
    """Step 1: send a verification code to the user's registered email."""
    email = (body.get("email") or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "translated"}, status_code=400)

    db = await get_main_db()
    cursor = await db.execute("SELECT id FROM users WHERE email = ? LIMIT 1", (email,))
    if not await cursor.fetchone():
        return JSONResponse({"error": "translated"}, status_code=404)

    ok, message = await send_verification_code(email)
    if not ok:
        return JSONResponse({"error": message}, status_code=429)
    return {"ok": True, "message": message}


@router.post("/auth/reset-password")
async def auth_reset_password(body: dict):
    """Step 2: verify code and set new password."""
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()
    password = body.get("password") or ""

    if not email or not _EMAIL_RE.match(email):
        return JSONResponse({"error": "translated"}, status_code=400)
    if not code:
        return JSONResponse({"error": "translatedcannot be empty"}, status_code=400)
    if len(password) < 4:
        return JSONResponse({"error": "translated 4 translated"}, status_code=400)

    if not verify_code(email, code):
        return JSONResponse({"error": "translatedinvalidtranslated"}, status_code=400)

    db = await get_main_db()
    cursor = await db.execute("SELECT id FROM users WHERE email = ? LIMIT 1", (email,))
    row = await cursor.fetchone()
    if not row:
        return JSONResponse({"error": "translated"}, status_code=404)

    pw_hash, _ = _hash_password(password)
    await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, row[0]))
    await db.commit()
    return {"ok": True, "message": "translated，translated"}


@router.get("/auth/me")
async def auth_me(user_id: int = Depends(require_user)):
    from core.db import get_main_db

    db = await get_main_db()
    cursor = await db.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row:
        return JSONResponse({"error": "userdoes not exist"}, status_code=404)
    return {"user_id": row[0], "username": row[1], "created_at": row[2]}


@router.post("/auth/logout")
async def auth_logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/auth/redeem-invite-code")
async def auth_redeem_invite_code(body: dict, user_id: int = Depends(require_user)):
    """translated，translated 50 translated LLM translated"""
    invite_code = (body.get("invite_code") or "").strip()
    
    if not invite_code:
        return JSONResponse({"error": "translatedcannot be empty"}, status_code=400)
    
    db = await get_main_db()
    
    try:
        # translated，translated「translated -> translated -> translated」translated
        await db.execute("BEGIN")
        
        # 1) translated
        cursor = await db.execute(
            "SELECT id, code, is_used FROM invitation_codes WHERE code = ? LIMIT 1",
            (invite_code,),
        )
        row = await cursor.fetchone()
        if not row:
            await db.rollback()
            return JSONResponse({"error": "translatedinvalid"}, status_code=400)
        if row[2]:  # is_used
            await db.rollback()
            return JSONResponse({"error": "translated"}, status_code=409)
        
        # 2) translated
        await db.execute(
            """
            UPDATE invitation_codes
            SET is_used = 1, used_by_user_id = ?
            WHERE code = ?
            """,
            (user_id, invite_code),
        )
        
        # 3) translated（+50 translated）
        # translated api_quotas translated
        await db.execute(
            """
            INSERT OR IGNORE INTO api_quotas (user_id, total_calls_made, free_quota_remaining)
            VALUES (?, 0, 0)
            """,
            (user_id,),
        )
        # translated（translated，translated）
        await db.execute(
            """
            UPDATE api_quotas
            SET free_quota_remaining = free_quota_remaining + 50
            WHERE user_id = ?
            """,
            (user_id,),
        )
        
        await db.commit()
        
        # Get translated
        quota = await get_user_api_quota(user_id)
        return {
            "ok": True,
            "message": "translatedsuccess，translated 50 translated LLM translated",
            "free_quota_remaining": quota.get("free_quota_remaining", 0) if quota else 0,
        }
    except aiosqlite.IntegrityError:
        await db.rollback()
        return JSONResponse({"error": "translated"}, status_code=409)
    except Exception as e:
        await db.rollback()
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"[REDEEM_INVITE] Failed to redeem invite code: {e}", exc_info=True)
        return JSONResponse({"error": "translatedfailed，please try again later"}, status_code=500)
