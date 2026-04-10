"""
FastAPI translated。

translated：
1. Device Token — translated X-Device-Token translated，translated
2. Admin Token — translated Authorization Bearer token，translated
"""
from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, Header, HTTPException, Request, Response

from .config_store import validate_device_token, get_device_state
from .i18n import detect_lang_from_request, msg, normalize_lang

logger = logging.getLogger(__name__)

def _load_jwt_secret() -> str:
    # Prefer explicit environment configuration in all deployments.
    env = (
        os.environ.get("INKSIGHT_JWT_SECRET")
        or os.environ.get("JWT_SECRET")
        or ""
    ).strip()
    if env:
        return env

    # Local-dev compatibility: reuse existing file if present.
    secret_file = os.path.join(os.path.dirname(__file__), "..", ".jwt_secret")
    try:
        with open(secret_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    except OSError:
        # Read errors should not crash module import in serverless runtime.
        pass

    # Serverless filesystems are read-only (`/var/task` on Vercel), so do not
    # attempt to create `.jwt_secret` here. Use a process-local fallback secret
    # to keep the app bootable; production should always set INKSIGHT_JWT_SECRET.
    logger.warning(
        "[AUTH] JWT secret not configured via INKSIGHT_JWT_SECRET/JWT_SECRET "
        "and no .jwt_secret file available; using ephemeral in-memory secret."
    )
    return secrets.token_urlsafe(48)

_JWT_SECRET = _load_jwt_secret()
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_DAYS = 30
_COOKIE_NAME = "ink_session"

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def validate_mac_param(mac: str, lang: str = "zh") -> str:
    """translated MAC translated。

    translated MAC，translatedinvalidtranslated 400。
    """
    if not mac or not _MAC_RE.match(mac):
        raise HTTPException(status_code=400, detail=msg("auth.invalid_mac_format", normalize_lang(lang)))
    return mac.upper()


def is_admin_authorized(authorization: Optional[str]) -> bool:
    admin_token = os.environ.get("ADMIN_TOKEN")
    if not admin_token:
        return False
    if not authorization:
        return False

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        return False
    return hmac.compare_digest(parts[1], admin_token)


def require_admin(
    authorization: Optional[str] = Header(default=None),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
) -> None:
    """FastAPI translated：translated。"""
    if not is_admin_authorized(authorization):
        raise HTTPException(status_code=403, detail=msg("auth.admin_required", normalize_lang(accept_language)))


async def require_device_token(
    mac: str,
    x_device_token: Optional[str] = Header(default=None),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
) -> bool:
    lang = normalize_lang(accept_language)
    if x_device_token:
        valid = await validate_device_token(mac, x_device_token)
        if valid:
            return True

    state = await get_device_state(mac)
    if state and state.get("auth_token"):
        logger.warning(f"[AUTH] device Token translatedfailed: {mac}")
        raise HTTPException(status_code=401, detail=msg("auth.device_token_invalid", lang))
    raise HTTPException(status_code=401, detail=msg("auth.device_token_required", lang))


def create_session_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_session_token(token: str) -> Optional[dict]:
    """Decode JWT session token.
    
    Returns:
        dict | None: Decoded payload if valid, None if invalid/expired.
    """
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning(f"[AUTH] decode_session_token: Token expired")
        return None
    except jwt.InvalidSignatureError:
        logger.warning(f"[AUTH] decode_session_token: Invalid signature (secret mismatch?)")
        return None
    except jwt.DecodeError as e:
        logger.warning(f"[AUTH] decode_session_token: Decode error: {e}")
        return None
    except jwt.PyJWTError as e:
        logger.warning(f"[AUTH] decode_session_token: JWT error: {type(e).__name__}: {e}")
        return None


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_JWT_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(key=_COOKIE_NAME, path="/")


def _extract_user(
    ink_session: Optional[str],
    request: Request,
) -> Optional[dict]:
    """Extract user payload from cookie or authorization header."""
    sources = []
    if ink_session:
        sources.append(("cookie", ink_session))
    
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        sources.append(("header", auth_header[7:]))
    
    for source_type, token in sources:
        if not token:
            continue
        try:
            payload = decode_session_token(token)
            if payload and "sub" in payload:
                logger.info(f"[AUTH] _extract_user: Successfully extracted from {source_type}, user_id={payload.get('sub')}")
                return payload
            else:
                logger.warning(f"[AUTH] _extract_user: Token from {source_type} decoded but missing 'sub' field, payload={payload}")
        except Exception as e:
            logger.warning(f"[AUTH] _extract_user: Failed to decode token from {source_type}: {type(e).__name__}: {e}")
            continue
    
    logger.warning(f"[AUTH] _extract_user: No valid token found (cookie={'present' if ink_session else 'None'}, header={'present' if auth_header else 'None'})")
    return None


async def require_user(
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
) -> int:
    payload = _extract_user(ink_session, request)
    if not payload:
        raise HTTPException(status_code=401, detail=msg("auth.login_required", detect_lang_from_request(request)))
    return int(payload["sub"])


async def optional_user(
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
) -> Optional[int]:
    payload = _extract_user(ink_session, request)
    return int(payload["sub"]) if payload else None


async def get_current_user_optional(
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
) -> Optional[dict]:
    """FastAPI translated：translatedGet translated（translated user_id translated role）。
    
    translated Token（Cookie translated Header），translatedinvalidtranslated None，translated。
    translated，translated。
    
    Returns:
        dict | None: translated，translated {"user_id": int, "role": str}，translated None
    """
    from .db import get_main_db
    
    # Debug: log what we received
    logger.info(f"[AUTH] get_current_user_optional: ink_session cookie={'present' if ink_session else 'None'}, auth header={'present' if request.headers.get('authorization') else 'None'}")
    
    payload = _extract_user(ink_session, request)
    if not payload:
        logger.warning(f"[AUTH] get_current_user_optional: No payload extracted")
        return None
    
    try:
        user_id = int(payload["sub"])
        logger.info(f"[AUTH] get_current_user_optional: Extracted user_id={user_id}")
    except (ValueError, KeyError) as e:
        logger.warning(f"[AUTH] get_current_user_optional: Failed to extract user_id: {e}, payload={payload}")
        return None
    
    # translatedGet  role
    try:
        db = await get_main_db()
        cursor = await db.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if not row:
            logger.warning(f"[AUTH] get_current_user_optional: User {user_id} not found in database")
            return None
        
        user_role = row[0] or "user"  # default role translated 'user'
        logger.info(f"[AUTH] get_current_user_optional: User {user_id} has role={user_role}")
        return {"user_id": user_id, "role": user_role}
    except Exception as e:
        # translatedfailedtranslated None，translated
        logger.warning(f"[AUTH] Failed to query user role for user_id={user_id}: {e}")
        return None


async def get_current_root_user(
    request: Request,
    ink_session: Optional[str] = Cookie(default=None),
) -> int:
    """FastAPI translated：translatedmusttranslated root translated（translated API translated）。
    
    translatedfailedtranslated role != "root"，translated HTTPException(403)。
    
    Returns:
        int: translated root translated user_id
        
    Raises:
        HTTPException: 401 translated，403 translated root translated
    """
    from .db import get_main_db
    
    # translated
    payload = _extract_user(ink_session, request)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail=msg("auth.login_required", detect_lang_from_request(request))
        )
    
    user_id = int(payload["sub"])
    
    # translated role
    db = await get_main_db()
    cursor = await db.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    
    if not row:
        raise HTTPException(
            status_code=404,
            detail=msg("auth.user_not_found", detect_lang_from_request(request))
        )
    
    user_role = row[0] or "user"  # default role translated 'user'
    
    if user_role != "root":
        raise HTTPException(
            status_code=403,
            detail=msg("auth.root_required", detect_lang_from_request(request))
        )
    
    return user_id