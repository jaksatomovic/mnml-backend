from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from api.shared import logger
from core.auth import require_user
from core.config import SCREEN_HEIGHT, SCREEN_WIDTH
from core.config_store import get_main_db
from core.context import get_date_context, get_weather
from core.db import execute_insert_returning_id
from core.mode_registry import (
    _validate_mode_def_with_error,
    get_registry,
)
from core.config_store import save_custom_mode, get_custom_mode as get_user_custom_mode_from_db

router = APIRouter(tags=["discover"])

_PLUGIN_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_PLUGIN_ZIP_MAX_ENTRIES = 64
_PLUGIN_REQUIRE_SIGNATURE = os.getenv("INKSIGHT_PLUGIN_REQUIRE_SIGNATURE", "0").strip() in {"1", "true", "yes"}
_PLUGIN_SIGNING_SECRET = os.getenv("INKSIGHT_PLUGIN_SIGNING_SECRET", "").strip()


async def _ensure_discover_install_table() -> None:
    db = await get_main_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS installed_shared_modes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mac TEXT NOT NULL,
            shared_mode_id INTEGER NOT NULL,
            custom_mode_id TEXT NOT NULL,
            installed_at TEXT NOT NULL,
            UNIQUE(user_id, mac, shared_mode_id)
        )
        """
    )
    await db.commit()


async def _ensure_plugin_install_table() -> None:
    db = await get_main_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS installed_plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mac TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            version TEXT NOT NULL,
            custom_mode_id TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            installed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, mac, plugin_id)
        )
        """
    )
    await db.commit()


async def _ensure_plugin_events_table() -> None:
    db = await get_main_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mac TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            version TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    await db.commit()


async def _log_plugin_event(
    *,
    user_id: int,
    mac: str,
    plugin_id: str,
    event_type: str,
    version: str,
    details: dict,
) -> None:
    await _ensure_plugin_events_table()
    db = await get_main_db()
    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO plugin_events (user_id, mac, plugin_id, event_type, version, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, mac, plugin_id, event_type, version, json.dumps(details, ensure_ascii=False), now),
    )
    await db.commit()


def _extract_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            urls.extend(_extract_urls(v))
    elif isinstance(value, list):
        for v in value:
            urls.extend(_extract_urls(v))
    elif isinstance(value, str):
        s = value.strip()
        if s.startswith("http://") or s.startswith("https://"):
            urls.append(s)
    return urls


def _validate_plugin_permissions(manifest: dict[str, object], mode_def: dict) -> tuple[bool, str]:
    permissions = manifest.get("permissions_obj")
    if not isinstance(permissions, dict):
        return True, ""
    allowed_domains = permissions.get("allowed_domains")
    if allowed_domains is None:
        return True, ""
    if not isinstance(allowed_domains, list) or not all(isinstance(d, str) and d.strip() for d in allowed_domains):
        return False, "manifest.permissions.allowed_domains musttranslated"
    normalized = [d.strip().lower() for d in allowed_domains]
    urls = _extract_urls(mode_def)
    for raw_url in urls:
        try:
            host = (urlparse(raw_url).hostname or "").lower().strip()
        except ValueError:
            return False, f"modetranslated URL: {raw_url}"
        if not host:
            return False, f"modetranslated URL: {raw_url}"
        if host in {"localhost", "127.0.0.1"} or host.endswith(".local"):
            return False, f"translated URL: {raw_url}"
        if not any(host == d or host.endswith(f".{d}") for d in normalized):
            return False, f"URL translated manifest permissions translated: {host}"
    return True, ""


def _verify_plugin_signature(
    *,
    plugin_id: str,
    version: str,
    mode_def: dict,
    signature: str,
) -> bool:
    if not _PLUGIN_SIGNING_SECRET:
        return False
    canonical_mode = json.dumps(mode_def, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload = f"{plugin_id}|{version}|{canonical_mode}".encode("utf-8")
    expected = hmac.new(_PLUGIN_SIGNING_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip().lower())


def _parse_semver(version: str) -> tuple[int, int, int]:
    v = (version or "").strip()
    core = v.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    if len(parts) == 1:
        parts = [parts[0], "0", "0"]
    elif len(parts) == 2:
        parts = [parts[0], parts[1], "0"]
    elif len(parts) > 3:
        parts = parts[:3]
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except (TypeError, ValueError, IndexError):
        raise ValueError("invalid semver")
    return major, minor, patch


@router.get("/discover/modes")
async def list_shared_modes(
    category: Optional[str] = Query(None, description="category filter"),
    page: int = Query(1, ge=1, description="page"),
    limit: int = Query(20, ge=1, le=100, description="items per page"),
):
    """Get translatedmodelist（translated，translated）"""
    db = await get_main_db()
    offset = (page - 1) * limit

    # translated
    query = """
        SELECT 
            sm.id,
            sm.mode_id,
            sm.name,
            sm.description,
            sm.category,
            sm.thumbnail_url,
            sm.created_at,
            u.username as author_username
        FROM shared_modes sm
        INNER JOIN users u ON sm.author_id = u.id
        WHERE sm.is_active IS TRUE
    """
    params = []

    if category:
        query += " AND sm.category = ?"
        params.append(category)

    query += " ORDER BY sm.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()

    # Get translated
    count_query = "SELECT COUNT(*) FROM shared_modes sm WHERE sm.is_active IS TRUE"
    count_params = []
    if category:
        count_query += " AND sm.category = ?"
        count_params.append(category)

    cursor = await db.execute(count_query, count_params)
    total_row = await cursor.fetchone()
    total = total_row[0] if total_row else 0

    modes = [
        {
            "id": row[0],
            "mode_id": row[1],
            "name": row[2],
            "description": row[3],
            "category": row[4],
            "thumbnail_url": row[5],
            "created_at": row[6],
            "author": f"@{row[7]}" if row[7] else "@unknown",
        }
        for row in rows
    ]

    return {
        "modes": modes,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if total > 0 else 0,
        },
    }


@router.get("/discover/modes/installed")
async def list_installed_shared_modes(
    mac: str = Query(..., description="device MAC"),
    user_id: int = Depends(require_user),
):
    mac_u = (mac or "").strip().upper()
    if not mac_u:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)

    from core.config_store import has_active_membership
    if not await has_active_membership(mac_u, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)

    await _ensure_discover_install_table()
    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT shared_mode_id, custom_mode_id, installed_at
        FROM installed_shared_modes
        WHERE user_id = ? AND mac = ?
        ORDER BY installed_at DESC
        """,
        (user_id, mac_u),
    )
    rows = await cursor.fetchall()
    return {
        "installed": [
            {
                "shared_mode_id": row[0],
                "custom_mode_id": row[1],
                "installed_at": row[2],
            }
            for row in rows
        ]
    }


@router.post("/discover/modes/publish")
async def publish_mode(
    body: dict,
    user_id: int = Depends(require_user),
):
    """publishmodetranslated（translated）"""
    source_custom_mode_id = body.get("source_custom_mode_id", "").strip().upper()
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    category = body.get("category", "").strip()
    mac = body.get("mac", "").strip().upper()
    thumbnail_base64 = body.get("thumbnail_base64")
    colors = int(body.get("colors", 2))

    # translated
    if not source_custom_mode_id:
        return JSONResponse({"error": "source_custom_mode_id cannot be empty"}, status_code=400)
    if not name:
        return JSONResponse({"error": "name cannot be empty"}, status_code=400)
    if not category:
        return JSONResponse({"error": "category cannot be empty"}, status_code=400)
    if not mac:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)

    # translated
    db = await get_main_db()
    cursor = await db.execute(
        "SELECT id FROM shared_modes WHERE name = ? AND is_active IS TRUE",
        (name,),
    )
    existing = await cursor.fetchone()
    if existing:
        return JSONResponse(
            {"error": f"modetranslated '{name}' already exists，translated"},
            status_code=409  # Conflict
        )

    # translated
    from core.config_store import has_active_membership
    if not await has_active_membership(mac, user_id):
        return JSONResponse(
            {"error": "device not found or access denied"},
            status_code=403
        )

    # translatedmodetranslated（translated，translated）
    mode_def = None
    
    # translatedGet translatedmode（translated）
    user_mode_data = await get_user_custom_mode_from_db(user_id, source_custom_mode_id, mac)
    if user_mode_data:
        mode_def = user_mode_data["definition"]
    else:
        # translated（translatedmode）
        registry = get_registry()
        mode = registry.get_json_mode(source_custom_mode_id, mac)
        if not mode:
            return JSONResponse(
                {"error": f"translatedmode {source_custom_mode_id} does not exist"},
                status_code=404,
            )
        if mode.info.source != "custom":
            return JSONResponse(
                {"error": f"mode {source_custom_mode_id} translatedmode"},
                status_code=400,
            )
        mode_def = mode.definition

    # Get translatedmodetranslated JSON
    config_json = json.dumps(mode_def, ensure_ascii=False)

    # translated（mustsuccess）
    try:
        from core.json_content import generate_json_mode_content
        from core.json_renderer import render_json_mode
        from core.config_store import get_user_llm_config

        # Get translated LLM config（translated）
        user_llm_cfg = await get_user_llm_config(user_id)
        llm_provider = ""
        llm_model = ""
        api_key = ""
        llm_base_url = ""
        image_provider = ""
        image_model = ""
        image_api_key = ""
        
        if user_llm_cfg:
            llm_access_mode = (user_llm_cfg.get("llm_access_mode") or "preset").strip().lower()
            llm_provider = (user_llm_cfg.get("provider") or "").strip()
            llm_model = (user_llm_cfg.get("model") or "").strip()
            api_key_plain = (user_llm_cfg.get("api_key") or "").strip()
            if api_key_plain:
                api_key = api_key_plain
            if llm_access_mode == "custom_openai":
                llm_base_url = (user_llm_cfg.get("base_url") or "").strip()
            image_provider = (user_llm_cfg.get("image_provider") or "").strip()
            image_model = (user_llm_cfg.get("image_model") or "").strip()
            image_api_key_plain = (user_llm_cfg.get("image_api_key") or "").strip()
            if image_api_key_plain:
                image_api_key = image_api_key_plain

        # Get translated
        date_ctx = await get_date_context()
        weather = await get_weather()

        # translated（translated image_gen translated，translatedimagetranslated）
        content_type = mode_def.get("content", {}).get("type", "static")
        max_retries = 10  # translated 10 translated
        retry_interval = 2  # translated 2 translated
        
        content = None
        if content_type == "image_gen":
            # translatedimagetranslated，translated
            for attempt in range(max_retries):
                content = await generate_json_mode_content(
                    mode_def,
                    date_ctx=date_ctx,
                    date_str=date_ctx["date_str"],
                    weather_str=weather["weather_str"],
                    screen_w=SCREEN_WIDTH,
                    screen_h=SCREEN_HEIGHT,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    llm_base_url=(llm_base_url or None),
                    api_key=api_key,
                    image_provider=image_provider,
                    image_model=image_model,
                    image_api_key=image_api_key,
                )
                
                image_url = content.get("image_url", "")
                description = content.get("description", "")
                
                # translatedgenerating
                is_generating = (
                    description == "translatedgenerating" or 
                    description == "Image generating..." or
                    not image_url or 
                    not image_url.strip() or
                    not (image_url.startswith("http://") or image_url.startswith("https://"))
                )
                
                if not is_generating:
                    # imagetranslated
                    logger.info(f"[DISCOVER] Image generated successfully after {attempt + 1} attempt(s)")
                    break
                
                # translatedgenerating，translated
                if attempt < max_retries - 1:
                    logger.info(f"[DISCOVER] Image still generating, retrying in {retry_interval}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_interval)
                else:
                    # translatedfailed
                    return JSONResponse(
                        {"error": "imagegeneratetimeout，translatedpublish。translatedimagegenerate API translated，translated。"},
                        status_code=408  # Request Timeout
                    )
        else:
            # translatedimagetranslated，translated
            content = await generate_json_mode_content(
                mode_def,
                date_ctx=date_ctx,
                date_str=date_ctx["date_str"],
                weather_str=weather["weather_str"],
                screen_w=SCREEN_WIDTH,
                screen_h=SCREEN_HEIGHT,
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_base_url=(llm_base_url or None),
                api_key=api_key,
                image_provider=image_provider,
                image_model=image_model,
                image_api_key=image_api_key,
            )

        # translatedimage
        img = render_json_mode(
            mode_def,
            content,
            date_str=date_ctx["date_str"],
            weather_str=weather["weather_str"],
            battery_pct=100.0,
            screen_w=SCREEN_WIDTH,
            screen_h=SCREEN_HEIGHT,
            colors=colors,
        )

        # translated base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        png_bytes = buf.getvalue()
        thumbnail_base64_str = base64.b64encode(png_bytes).decode("ascii")
        thumbnail_url = f"data:image/png;base64,{thumbnail_base64_str}"

        logger.info(f"[DISCOVER] Generated thumbnail for mode {source_custom_mode_id}")
    except Exception as e:
        logger.error(f"[DISCOVER] Failed to generate thumbnail for {source_custom_mode_id}: {e}", exc_info=True)
        return JSONResponse(
            {"error": f"translatedimagegeneratefailed: {str(e)}"},
            status_code=500
        )

    # translated（translated，translated）
    db = await get_main_db()
    now = datetime.now().isoformat()
    try:
        shared_mode_id = await execute_insert_returning_id(
            db,
            """
            INSERT INTO shared_modes 
            (mode_id, name, description, category, author_id, config_json, thumbnail_url, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_custom_mode_id, name, description, category, user_id, config_json, thumbnail_url, True, now),
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        error_msg = str(e).lower()
        if "unique" in error_msg or "constraint" in error_msg:
            return JSONResponse(
                {"error": f"modetranslated '{name}' already exists，translated"},
                status_code=409  # Conflict
            )
        logger.error(f"[DISCOVER] Failed to insert shared mode: {e}", exc_info=True)
        return JSONResponse(
            {"error": "publishfailed，please try again later"},
            status_code=500
        )

    logger.info(f"[DISCOVER] User {user_id} published mode {source_custom_mode_id} as shared mode {shared_mode_id}")
    return {"ok": True, "id": shared_mode_id}


@router.post("/discover/modes/{mode_id}/install")
async def install_shared_mode(
    mode_id: int,
    body: dict,
    user_id: int = Depends(require_user),
):
    """installtranslatedmodetranslated（translated）"""
    mac = body.get("mac", "").strip().upper()
    if not mac:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)

    # translated
    from core.config_store import has_active_membership
    if not await has_active_membership(mac, user_id):
        return JSONResponse(
            {"error": "device not found or access denied"},
            status_code=403
        )

    db = await get_main_db()

    await _ensure_discover_install_table()

    # translatedmode
    cursor = await db.execute(
        """
        SELECT config_json, mode_id, name
        FROM shared_modes
        WHERE id = ? AND is_active IS TRUE
        """,
        (mode_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return JSONResponse({"error": "translatedmodedoes not existtranslated"}, status_code=404)

    config_json_str, original_mode_id, original_name = row

    # translated JSON
    try:
        mode_def = json.loads(config_json_str)
    except json.JSONDecodeError:
        return JSONResponse({"error": "modeconfigformat error"}, status_code=500)

    # translatedmode ID（translatedconflict）
    new_mode_id = f"CUSTOM_{uuid.uuid4().hex[:8].upper()}"
    mode_def["mode_id"] = new_mode_id

    # translated：translated，translated
    if "display_name" in mode_def:
        mode_def["display_name"] = f"{original_name} (from marketplace)"

    # translatedmodetranslated
    ok, err = _validate_mode_def_with_error(mode_def, allow_raw_component_tree=False)
    if not ok:
        return JSONResponse({"error": err or "modetranslatedfailed"}, status_code=400)

    # translatedmodeconflict
    registry = get_registry()
    if registry.is_builtin(new_mode_id):
        return JSONResponse({"error": "mode ID conflict"}, status_code=409)

    dl = str(mode_def.get("definition_language") or "zh").strip().lower()
    if dl not in ("zh", "en", "hr"):
        dl = "zh"
    success = await save_custom_mode(
        user_id, new_mode_id, mode_def, mac, definition_language=dl
    )
    if not success:
        return JSONResponse({"error": "translatedmodefailed"}, status_code=500)

    # translated
    registry.unregister_custom(new_mode_id, mac)
    loaded = registry.load_custom_mode_from_dict(
        new_mode_id, mode_def, source="custom", mac=mac, definition_language=dl
    )
    if not loaded:
        # Rollback database entry
        from core.config_store import delete_custom_mode
        await delete_custom_mode(user_id, new_mode_id, mac)
        return JSONResponse({"error": "modetranslatedfailed"}, status_code=500)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO installed_shared_modes (user_id, mac, shared_mode_id, custom_mode_id, installed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, mac, shared_mode_id) DO UPDATE SET
            custom_mode_id = excluded.custom_mode_id,
            installed_at = excluded.installed_at
        """,
        (user_id, mac, mode_id, new_mode_id, now),
    )
    await db.commit()

    logger.info(f"[DISCOVER] User {user_id} installed shared mode {mode_id} as {new_mode_id} on device {mac}")
    return {"ok": True, "custom_mode_id": new_mode_id}


@router.post("/discover/plugins/install")
async def install_plugin_package(
    body: dict,
    user_id: int = Depends(require_user),
):
    """Install a local plugin package (JSON) to a device."""
    mac = str(body.get("mac", "")).strip().upper()
    if not mac:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)

    from core.config_store import has_active_membership
    if not await has_active_membership(mac, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)

    await _ensure_plugin_install_table()

    mode_def: dict | None = None
    manifest: dict[str, object] = {}
    plugin_obj = body.get("plugin")
    plugin_base64 = str(body.get("plugin_base64") or "").strip()
    plugin_filename = str(body.get("plugin_filename") or "").strip().lower()

    if plugin_base64:
        if plugin_filename and not (plugin_filename.endswith(".json") or plugin_filename.endswith(".zip")):
            return JSONResponse({"error": "plugintranslatedmusttranslated .json translated .zip"}, status_code=400)
        try:
            plugin_bytes = base64.b64decode(plugin_base64, validate=True)
        except Exception:
            return JSONResponse({"error": "plugin_base64 translated"}, status_code=400)
        if len(plugin_bytes) > _PLUGIN_MAX_BYTES:
            return JSONResponse({"error": "plugintranslated（translated 2MB）"}, status_code=413)

        if plugin_filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(plugin_bytes)) as zf:
                    names = zf.namelist()
                    if len(names) > _PLUGIN_ZIP_MAX_ENTRIES:
                        return JSONResponse({"error": "plugin ZIP translated"}, status_code=400)
                    if any(".." in n or n.startswith("/") for n in names):
                        return JSONResponse({"error": "plugin ZIP translated"}, status_code=400)
                    manifest_json_name = next((n for n in zf.namelist() if n.endswith("manifest.json")), None)
                    mode_json_name = next((n for n in zf.namelist() if n.endswith("mode.json")), None)
                    if not mode_json_name:
                        return JSONResponse(
                            {"error": "plugin ZIP translated mode.json"},
                            status_code=400,
                        )
                    if not manifest_json_name:
                        return JSONResponse(
                            {"error": "plugin ZIP translated manifest.json"},
                            status_code=400,
                        )
                    manifest_raw = zf.read(manifest_json_name)
                    manifest_parsed = json.loads(manifest_raw.decode("utf-8"))
                    if isinstance(manifest_parsed, dict):
                        manifest = {
                            "plugin_id": str(manifest_parsed.get("plugin_id") or "").strip(),
                            "version": str(manifest_parsed.get("version") or "").strip(),
                            "name": str(manifest_parsed.get("name") or "").strip(),
                            "signature": str(manifest_parsed.get("signature") or "").strip(),
                            "permissions_obj": manifest_parsed.get("permissions") if isinstance(manifest_parsed.get("permissions"), dict) else {},
                        }
                    raw = zf.read(mode_json_name)
                    parsed = json.loads(raw.decode("utf-8"))
                    if isinstance(parsed, dict):
                        mode_def = parsed
            except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
                return JSONResponse({"error": "plugin ZIP translatedfailed"}, status_code=400)
        else:
            try:
                parsed = json.loads(plugin_bytes.decode("utf-8"))
                if isinstance(parsed, dict):
                    plugin_obj = parsed
            except (UnicodeDecodeError, json.JSONDecodeError):
                return JSONResponse({"error": "plugin JSON translatedfailed"}, status_code=400)

    if mode_def is None and isinstance(plugin_obj, dict):
        if isinstance(plugin_obj.get("manifest"), dict):
            m = plugin_obj.get("manifest") or {}
            manifest = {
                "plugin_id": str(m.get("plugin_id") or "").strip(),
                "version": str(m.get("version") or "").strip(),
                "name": str(m.get("name") or "").strip(),
                "signature": str(m.get("signature") or "").strip(),
                "permissions_obj": m.get("permissions") if isinstance(m.get("permissions"), dict) else {},
            }
        if isinstance(plugin_obj.get("mode"), dict):
            mode_def = plugin_obj.get("mode")
        elif isinstance(plugin_obj.get("mode_def"), dict):
            mode_def = plugin_obj.get("mode_def")
        else:
            mode_def = plugin_obj

    if mode_def is None and isinstance(body.get("mode_def"), dict):
        mode_def = body.get("mode_def")

    if not isinstance(mode_def, dict):
        return JSONResponse({"error": "translated mode_def"}, status_code=400)

    # Validate/normalize manifest (required fields for packaged plugins).
    source_mode_id = str(mode_def.get("mode_id") or "PLUGIN_MODE").strip().upper()
    source_mode_id = "".join(ch if ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch == "_" else "_" for ch in source_mode_id)
    source_mode_id = source_mode_id.strip("_") or "PLUGIN_MODE"
    plugin_id = str(manifest.get("plugin_id") or source_mode_id).strip().upper()
    plugin_id = "".join(ch if ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch == "_" else "_" for ch in plugin_id)
    plugin_id = plugin_id.strip("_") or "PLUGIN_MODE"
    version = str(manifest.get("version") or "0.0.0").strip()
    if not str(manifest.get("name") or "").strip():
        manifest["name"] = str(mode_def.get("display_name") or plugin_id).strip()
    if not plugin_id or len(plugin_id) < 3:
        return JSONResponse({"error": "manifest.plugin_id invalid"}, status_code=400)
    if not version or len(version) > 32:
        return JSONResponse({"error": "manifest.version invalid"}, status_code=400)
    try:
        incoming_semver = _parse_semver(version)
    except ValueError:
        return JSONResponse({"error": "manifest.version musttranslated semver，translated 1.2.3"}, status_code=400)

    perm_ok, perm_err = _validate_plugin_permissions(manifest, mode_def)
    if not perm_ok:
        return JSONResponse({"error": perm_err}, status_code=400)

    # Deterministic mode id enables clean update on re-install.
    new_mode_id = f"CUSTOM_PLUGIN_{plugin_id[:30]}"
    mode_def = dict(mode_def)
    mode_def["mode_id"] = new_mode_id

    signature = str(manifest.get("signature") or "").strip()
    if _PLUGIN_REQUIRE_SIGNATURE and not signature:
        return JSONResponse({"error": "plugintranslated signature，translated"}, status_code=400)
    if signature:
        if not _verify_plugin_signature(
            plugin_id=plugin_id,
            version=version,
            mode_def=mode_def,
            signature=signature,
        ):
            return JSONResponse({"error": "plugintranslatedfailed"}, status_code=400)

    ok, err = _validate_mode_def_with_error(mode_def, allow_raw_component_tree=False)
    if not ok:
        return JSONResponse({"error": err or "modetranslatedfailed"}, status_code=400)

    registry = get_registry()
    if registry.is_builtin(new_mode_id):
        return JSONResponse({"error": "mode ID conflict"}, status_code=409)

    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT version FROM installed_plugins
        WHERE user_id = ? AND mac = ? AND plugin_id = ?
        """,
        (user_id, mac, plugin_id),
    )
    existing = await cursor.fetchone()
    action = "installed"
    if existing and existing[0]:
        try:
            current_semver = _parse_semver(str(existing[0]))
            if incoming_semver < current_semver:
                return JSONResponse(
                    {"error": f"translated：translated {existing[0]}，translated {version}"},
                    status_code=409,
                )
            if incoming_semver == current_semver:
                action = "reinstalled"
            else:
                action = "updated"
        except ValueError:
            action = "updated"

    dl = str(mode_def.get("definition_language") or "zh").strip().lower()
    if dl not in ("zh", "en", "hr"):
        dl = "zh"
    success = await save_custom_mode(
        user_id, new_mode_id, mode_def, mac, definition_language=dl
    )
    if not success:
        return JSONResponse({"error": "translatedmodefailed"}, status_code=500)

    registry.unregister_custom(new_mode_id, mac)
    loaded = registry.load_custom_mode_from_dict(
        new_mode_id, mode_def, source="custom", mac=mac, definition_language=dl
    )
    if not loaded:
        from core.config_store import delete_custom_mode
        await delete_custom_mode(user_id, new_mode_id, mac)
        return JSONResponse({"error": "modetranslatedfailed"}, status_code=500)

    logger.info("[DISCOVER] User %s installed local plugin as %s on %s", user_id, new_mode_id, mac)
    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO installed_plugins (user_id, mac, plugin_id, version, custom_mode_id, manifest_json, installed_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, mac, plugin_id) DO UPDATE SET
            version = excluded.version,
            custom_mode_id = excluded.custom_mode_id,
            manifest_json = excluded.manifest_json,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            mac,
            plugin_id,
            version,
            new_mode_id,
            json.dumps(manifest, ensure_ascii=False),
            now,
            now,
        ),
    )
    await db.commit()
    await _log_plugin_event(
        user_id=user_id,
        mac=mac,
        plugin_id=plugin_id,
        event_type=action,
        version=version,
        details={"custom_mode_id": new_mode_id},
    )
    return {
        "ok": True,
        "custom_mode_id": new_mode_id,
        "plugin_id": plugin_id,
        "version": version,
        "action": action,
    }


@router.get("/discover/plugins/installed")
async def list_installed_plugins(
    mac: str = Query(..., description="device MAC"),
    user_id: int = Depends(require_user),
):
    mac_u = (mac or "").strip().upper()
    if not mac_u:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)
    from core.config_store import has_active_membership
    if not await has_active_membership(mac_u, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)

    await _ensure_plugin_install_table()
    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT plugin_id, version, custom_mode_id, manifest_json, installed_at, updated_at
        FROM installed_plugins
        WHERE user_id = ? AND mac = ?
        ORDER BY updated_at DESC
        """,
        (user_id, mac_u),
    )
    rows = await cursor.fetchall()
    items = []
    for row in rows:
        try:
            manifest = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            manifest = {}
        items.append(
            {
                "plugin_id": row[0],
                "version": row[1],
                "custom_mode_id": row[2],
                "manifest": manifest,
                "installed_at": row[4],
                "updated_at": row[5],
            }
        )
    return {"plugins": items}


@router.get("/discover/plugins/events")
async def list_plugin_events(
    mac: str = Query(..., description="device MAC"),
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(require_user),
):
    mac_u = (mac or "").strip().upper()
    if not mac_u:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)
    from core.config_store import has_active_membership
    if not await has_active_membership(mac_u, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)
    await _ensure_plugin_events_table()
    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT plugin_id, event_type, version, details_json, created_at
        FROM plugin_events
        WHERE user_id = ? AND mac = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, mac_u, int(limit)),
    )
    rows = await cursor.fetchall()
    events = []
    for row in rows:
        try:
            details = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            details = {}
        events.append(
            {
                "plugin_id": row[0],
                "event_type": row[1],
                "version": row[2],
                "details": details,
                "created_at": row[4],
            }
        )
    return {"events": events}


@router.delete("/discover/plugins/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    mac: str = Query(..., description="device MAC"),
    user_id: int = Depends(require_user),
):
    mac_u = (mac or "").strip().upper()
    if not mac_u:
        return JSONResponse({"error": "mac cannot be empty"}, status_code=400)
    from core.config_store import has_active_membership, delete_custom_mode
    if not await has_active_membership(mac_u, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)

    await _ensure_plugin_install_table()
    db = await get_main_db()
    plugin_id_u = str(plugin_id or "").strip().upper()
    cursor = await db.execute(
        """
        SELECT custom_mode_id FROM installed_plugins
        WHERE user_id = ? AND mac = ? AND plugin_id = ?
        """,
        (user_id, mac_u, plugin_id_u),
    )
    row = await cursor.fetchone()
    if not row:
        return JSONResponse({"error": "plugintranslatedinstall"}, status_code=404)
    custom_mode_id = str(row[0] or "")
    deleted = await delete_custom_mode(user_id, custom_mode_id, mac_u)
    if not deleted:
        return JSONResponse({"error": "translatedmodedeletefailed"}, status_code=500)
    await db.execute(
        "DELETE FROM installed_plugins WHERE user_id = ? AND mac = ? AND plugin_id = ?",
        (user_id, mac_u, plugin_id_u),
    )
    await db.commit()
    get_registry().unregister_custom(custom_mode_id, mac_u)
    await _log_plugin_event(
        user_id=user_id,
        mac=mac_u,
        plugin_id=plugin_id_u,
        event_type="uninstalled",
        version="0.0.0",
        details={"custom_mode_id": custom_mode_id},
    )
    return {"ok": True}


@router.get("/discover/plugins/export")
async def export_plugin_package(
    mac: str = Query(..., description="device MAC"),
    mode_id: str = Query(..., description="Custom mode id"),
    version: str = Query("1.0.0", description="Plugin semver version"),
    plugin_id: Optional[str] = Query(None, description="Optional plugin id override"),
    user_id: int = Depends(require_user),
):
    mac_u = (mac or "").strip().upper()
    mode_id_u = (mode_id or "").strip().upper()
    if not mac_u or not mode_id_u:
        return JSONResponse({"error": "mac translated mode_id cannot be empty"}, status_code=400)

    from core.config_store import has_active_membership
    if not await has_active_membership(mac_u, user_id):
        return JSONResponse({"error": "device not found or access denied"}, status_code=403)

    try:
        _parse_semver(version)
    except ValueError:
        return JSONResponse({"error": "version musttranslated semver，translated 1.0.0"}, status_code=400)

    custom = await get_user_custom_mode_from_db(user_id, mode_id_u, mac_u)
    if not custom:
        return JSONResponse({"error": "translatedmodedoes not exist"}, status_code=404)

    mode_def = dict(custom.get("definition") or {})
    display_name = str(mode_def.get("display_name") or mode_id_u).strip()

    raw_plugin_id = (plugin_id or mode_id_u).strip().upper()
    if raw_plugin_id.startswith("CUSTOM_PLUGIN_"):
        raw_plugin_id = raw_plugin_id[len("CUSTOM_PLUGIN_"):]
    normalized_plugin_id = "".join(
        ch if ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch == "_" else "_"
        for ch in raw_plugin_id
    ).strip("_") or "PLUGIN_MODE"

    manifest = {
        "plugin_id": normalized_plugin_id,
        "version": version,
        "name": display_name,
    }
    package_mode = dict(mode_def)
    package_mode["mode_id"] = normalized_plugin_id

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("mode.json", json.dumps(package_mode, ensure_ascii=False, indent=2))
    buf.seek(0)

    filename = f"{normalized_plugin_id.lower()}-{version}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
