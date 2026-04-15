"""
translated JSON modetranslated
Get by  JSON content translated LLM translated
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import socket
from ipaddress import ip_address
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import os

import httpx
from httpx import HTTPStatusError
from openai import OpenAIError

from .config import DEFAULT_LLM_PROVIDER, DEFAULT_LLM_MODEL, DEFAULT_IMAGE_PROVIDER, DEFAULT_IMAGE_MODEL
from .content import _build_context_str, _build_style_instructions, _call_llm, _clean_json_response
from .errors import LLMKeyMissingError
from .layout_presets import expand_layout_presets
from .render_tiers import (
    SLOT_SHAPE_FULL,
    SLOT_SHAPE_LARGE,
    SLOT_SHAPE_SMALL,
    SLOT_SHAPE_TALL,
    SLOT_SHAPE_WIDE,
    SLOT_TIER_FULL,
    SLOT_TIER_LG,
    classify_slot_shape,
    classify_slot_tier,
)

logger = logging.getLogger(__name__)

# Experiment switches
DISABLE_FALLBACK = os.environ.get("INKSIGHT_DISABLE_FALLBACK", "").strip().lower() in ("1", "true", "yes")
DISABLE_DEDUP = os.environ.get("INKSIGHT_DISABLE_DEDUP", "").strip().lower() in ("1", "true", "yes")

if DISABLE_FALLBACK:
    logger.warning("[EXP] Fallback is DISABLED via INKSIGHT_DISABLE_FALLBACK")
if DISABLE_DEDUP:
    logger.warning("[EXP] Deduplication is DISABLED via INKSIGHT_DISABLE_DEDUP")

DEDUP_MAX_RETRIES = 2

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_UPLOAD_DIR = _BACKEND_ROOT / "runtime_uploads"

_HTTP_FETCH_MAX_BYTES = int(os.environ.get("INKSIGHT_HTTP_FETCH_MAX_BYTES", "262144"))
_HTTP_FETCH_TIMEOUT = float(os.environ.get("INKSIGHT_HTTP_FETCH_TIMEOUT", "10"))
_HTTP_FETCH_ALLOW_HTTP = os.environ.get("INKSIGHT_HTTP_FETCH_ALLOW_HTTP", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _http_fetch_get_path(data: Any, path: str) -> Any:
    """Read a value from nested dict/list JSON using dot paths (e.g. a.b.0.c)."""
    if path == "":
        return data
    cur: Any = data
    for part in path.split("."):
        if part == "":
            continue
        if cur is None:
            return None
        if isinstance(cur, list):
            if part.isdigit():
                idx = int(part)
                cur = cur[idx] if 0 <= idx < len(cur) else None
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _http_fetch_serialize_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (str, int, float)):
        return str(v)
    try:
        s = json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
    return s if len(s) <= 8000 else s[:8000]


def _normalize_allowed_hosts(entries: list[str]) -> list[str]:
    out: list[str] = []
    for e in entries:
        if not isinstance(e, str):
            continue
        s = e.strip().lower()
        if s:
            out.append(s)
    return out


def _host_matches_http_fetch_allowlist(host: str, allowed: list[str]) -> bool:
    host = (host or "").lower().strip()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    for d in allowed:
        if host == d or host.endswith(f".{d}"):
            return True
    return False


def _http_fetch_ip_blocked(addr: str) -> bool:
    try:
        ip = ip_address(addr)
    except ValueError:
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _http_fetch_resolve_safe(hostname: str) -> bool:
    """Return True if hostname resolves only to non-blocked addresses."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        if _http_fetch_ip_blocked(addr):
            return False
    return True


def _resolve_uploaded_image_bytes(url: str) -> bytes | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    path = parsed.path or ""
    if not path.startswith("/api/uploads/"):
        return None
    upload_id = path.rsplit("/", 1)[-1].strip()
    if not upload_id:
        return None
    try:
        __import__("uuid").UUID(upload_id)
    except ValueError:
        return None
    file_path = _UPLOAD_DIR / f"{upload_id}.bin"
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        return file_path.read_bytes()
    except OSError:
        return None

def _collect_image_fields(blocks: list, fields: set):
    """Recursively collect image field names from layout blocks."""
    for block in blocks:
        if block.get("type") == "image":
            fields.add(block.get("field", "image_url"))
        for child_key in ("children", "left", "right"):
            children = block.get(child_key, [])
            if isinstance(children, list):
                _collect_image_fields(children, fields)


async def _prefetch_images(content: dict, mode_def: dict) -> dict:
    """Pre-fetch any image URLs referenced by the layout into content dict."""
    layout = expand_layout_presets(mode_def.get("layout", {}))
    body_blocks = layout.get("body", [])
    image_fields: set = set()
    _collect_image_fields(body_blocks, image_fields)

    if not image_fields:
        return content

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for field_name in image_fields:
            url = content.get(field_name)
            if url and isinstance(url, str) and url.startswith("http"):
                local_bytes = _resolve_uploaded_image_bytes(url)
                if local_bytes:
                    content[f"_prefetched_{field_name}"] = local_bytes
                    continue
                try:
                    resp = await client.get(url)
                    if resp.status_code < 400:
                        content[f"_prefetched_{field_name}"] = resp.content
                except httpx.HTTPError:
                    logger.warning("[JSONContent] Failed to prefetch image field %s", field_name, exc_info=True)
    return content


def _get_fallback(content_cfg: dict) -> dict:
    """Get fallback content, supporting both single fallback and fallback_pool."""
    pool = content_cfg.get("fallback_pool")
    if pool and isinstance(pool, list) and len(pool) > 0:
        return dict(random.choice(pool))
    return dict(content_cfg.get("fallback", {}))


def _compute_content_hash(result: dict) -> str:
    text = json.dumps(result, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _is_api_key_error(e: Exception) -> bool:
    """Check if exception indicates API key is invalid/expired (401/403)."""
    if isinstance(e, HTTPStatusError):
        status_code = e.response.status_code if hasattr(e, 'response') and e.response else None
        return status_code in (401, 403)
    
    if isinstance(e, OpenAIError):
        error_message = str(e).lower()
        error_code = getattr(e, 'status_code', None) or getattr(e, 'code', None)
        if error_code in (401, 403):
            return True
        auth_keywords = ("401", "403", "unauthorized", "invalid", "authentication")
        return any(kw in error_message for kw in auth_keywords)
    
    return False


def _validate_content_quality(result: dict, schema: dict | None = None) -> bool:
    """Validate LLM output quality. Returns True if acceptable."""
    if not result:
        return False
    for key, val in result.items():
        if isinstance(val, str) and len(val) > 500:
            return False
    important_keys = [k for k in result if k in ("quote", "question", "body", "word", "event_title", "challenge", "name_cn", "text")]
    for k in important_keys:
        if not result.get(k):
            return False
    return True


async def _generate_http_fetch_content(
    mode_def: dict,
    content_cfg: dict,
    fallback: dict,
    *,
    date_str: str = "",
    weather_str: str = "",
    festival: str = "",
    daily_word: str = "",
    upcoming_holiday: str = "",
    days_until_holiday: int = 0,
    language: str | None = None,
    config: dict | None = None,
    **_: Any,
) -> dict:
    """Fetch JSON from an allowlisted HTTPS URL and map fields into layout content."""
    mode_id = str(mode_def.get("mode_id") or "HTTP_FETCH")
    raw_url = str(content_cfg.get("url", "")).strip()
    allowed = _normalize_allowed_hosts(list(content_cfg.get("allowed_hosts") or []))
    response_map = content_cfg.get("response_map") or {}
    if not isinstance(response_map, dict) or not response_map:
        logger.warning("[JSONContent] http_fetch missing response_map for %s", mode_id)
        return dict(fallback)

    context = _build_context_str(
        date_str,
        weather_str,
        festival,
        daily_word,
        upcoming_holiday,
        days_until_holiday,
        language=language,
    )
    city = ""
    cfg = config or {}
    if isinstance(cfg.get("city"), str):
        city = cfg["city"]

    url = raw_url.replace("{context}", quote(context, safe=""))
    url = url.replace("{city}", quote(city, safe=""))

    try:
        parsed = urlparse(url)
    except ValueError:
        logger.warning("[JSONContent] http_fetch invalid URL for %s", mode_id)
        return dict(fallback)

    scheme = (parsed.scheme or "").lower()
    if scheme == "https":
        pass
    elif scheme == "http" and _HTTP_FETCH_ALLOW_HTTP:
        pass
    else:
        logger.warning("[JSONContent] http_fetch rejected scheme for %s", mode_id)
        return dict(fallback)

    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return dict(fallback)

    if not _host_matches_http_fetch_allowlist(hostname, allowed):
        logger.warning("[JSONContent] http_fetch host not in allowlist: %s", hostname)
        return dict(fallback)

    safe_resolve = await asyncio.to_thread(_http_fetch_resolve_safe, hostname)
    if not safe_resolve:
        logger.warning("[JSONContent] http_fetch DNS/SSRF blocked for %s", hostname)
        return dict(fallback)

    headers_in = content_cfg.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(headers_in, dict):
        for k, v in list(headers_in.items())[:32]:
            if isinstance(k, str) and isinstance(v, str) and k.strip():
                headers[k.strip()] = v[:2048]

    timeout = httpx.Timeout(_HTTP_FETCH_TIMEOUT)
    max_bytes = max(1024, min(_HTTP_FETCH_MAX_BYTES, 2 * 1024 * 1024))

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            async with client.stream("GET", url, headers=headers or None) as resp:
                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("response too large")
                    chunks.append(chunk)
        raw_body = b"".join(chunks)
    except (httpx.HTTPError, ValueError, TypeError) as e:
        logger.warning("[JSONContent] http_fetch request failed for %s: %s", mode_id, e, exc_info=True)
        return dict(fallback)

    try:
        payload = json.loads(raw_body.decode("utf-8", errors="replace"))
    except JSONDecodeError:
        logger.warning("[JSONContent] http_fetch invalid JSON for %s", mode_id)
        return dict(fallback)

    if not isinstance(payload, (dict, list)):
        return dict(fallback)

    out: dict[str, Any] = dict(fallback)
    for out_key, json_path in response_map.items():
        if not isinstance(out_key, str) or not isinstance(json_path, str):
            continue
        val = _http_fetch_get_path(payload, json_path.strip())
        out[out_key] = _http_fetch_serialize_value(val)

    return out


async def generate_json_mode_content(
    mode_def: dict,
    *,
    config: dict | None = None,
    date_ctx: dict | None = None,
    date_str: str = "",
    weather_str: str = "",
    festival: str = "",
    daily_word: str = "",
    upcoming_holiday: str = "",
    days_until_holiday: int = 0,
    character_tones: list[str] | None = None,
    language: str | None = None,
    content_tone: str | None = None,
    llm_provider: str = "",
    llm_model: str = "",
    llm_base_url: str | None = None,
    image_provider: str = "",
    image_model: str = "",
    mac: str = "",
    screen_w: int = 400,
    screen_h: int = 300,
    slot_type: str | None = None,
    api_key: str = "",
    image_api_key: str = "",
) -> dict:
    """Generate content for a JSON-defined mode.

    Supports content types:
    - static: returns static_data from the definition
    - llm: calls LLM with prompt template, parses output per output_format
    - llm_json: calls LLM, parses JSON response using output_schema
    - external_data: fetches data from built-in providers (HN/PH/V2EX)
    - image_gen: generates image data payload (ARTWALL provider)
    - computed: computes content from config/date without LLM
    - composite: merges results from multiple nested content steps
    - http_fetch: GET JSON from an allowlisted URL; maps fields via response_map
    """
    content_cfg = mode_def.get("content", {})
    ctype = content_cfg.get("type", "static")
    fallback = _get_fallback(content_cfg)
    mode_id = str(mode_def.get("mode_id") or "").upper()

    # Preview-only overrides: backend/api/index.py may inject per-mode overrides into
    # config["mode_overrides"][MODE_ID]. We allow these overrides to fill/replace
    # generated content fields (e.g. custom quote text, image_url for photo modes).
    override = {}
    try:
        cfg = config or {}
        mo = cfg.get("mode_overrides", {})
        if isinstance(mo, dict) and mode_id:
            candidate = mo.get(mode_id, {})
            if isinstance(candidate, dict):
                override = candidate
    except Exception:
        override = {}

    common_args = dict(
        date_str=date_str,
        weather_str=weather_str,
        festival=festival,
        daily_word=daily_word,
        upcoming_holiday=upcoming_holiday,
        days_until_holiday=days_until_holiday,
        character_tones=character_tones,
        language=language,
        content_tone=content_tone,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        image_provider=image_provider,
        image_model=image_model,
        config=config or {},
        date_ctx=date_ctx or {},
        api_key=api_key,
        image_api_key=image_api_key,
        screen_w=screen_w,
        screen_h=screen_h,
        slot_type=slot_type,
    )

    # If override explicitly provides content fields, short-circuit LLM for llm_json.
    if ctype == "llm_json" and isinstance(override, dict) and override:
        quote = override.get("quote")
        author = override.get("author")
        if isinstance(quote, str) and quote.strip():
            result = dict(fallback)
            result["quote"] = quote.strip()
            if isinstance(author, str) and author.strip():
                result["author"] = author.strip()
            result = await _prefetch_images(result, mode_def)
            return result

    if ctype == "static":
        content = dict(content_cfg.get("static_data", fallback))
        if isinstance(override, dict) and override:
            # Merge overrides into static content (preview-only).
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content
    if ctype == "computed":
        content = await _generate_computed_content(mode_def, content_cfg, fallback, **common_args)
        if isinstance(override, dict) and override:
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                if mode_id == "COUNTDOWN" and k in {"events", "countdownEvents", "message"}:
                    continue
                if mode_id == "HABIT" and k in {"habitItems", "habits", "summary", "week_progress", "week_total"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content
    if ctype == "external_data":
        content = await _generate_external_data_content(mode_def, content_cfg, fallback, **common_args)
        if isinstance(override, dict) and override:
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content
    if ctype == "image_gen":
        content = await _generate_image_gen_content(mode_def, content_cfg, fallback, **common_args)
        if isinstance(override, dict) and override:
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content
    if ctype == "composite":
        content = await _generate_composite_content(mode_def, content_cfg, fallback, **common_args)
        if isinstance(override, dict) and override:
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content
    if ctype == "http_fetch":
        content = await _generate_http_fetch_content(mode_def, content_cfg, fallback, **common_args)
        if isinstance(override, dict) and override:
            for k, v in override.items():
                if k in {"city", "llm_provider", "llm_model", "image_provider", "image_model"}:
                    continue
                content[k] = v
        content = await _prefetch_images(content, mode_def)
        return content

    provider = llm_provider or DEFAULT_LLM_PROVIDER
    model = llm_model or DEFAULT_LLM_MODEL
    temperature = content_cfg.get("temperature", 0.8)

    context = _build_context_str(
        date_str, weather_str, festival, daily_word,
        upcoming_holiday, days_until_holiday,
        language=language,
    )
    base_prompt = content_cfg.get("prompt_template", "").replace("{context}", context)

    style = _build_style_instructions(character_tones, language, content_tone)
    if style:
        base_prompt += style

    tier = classify_slot_tier(screen_w, screen_h)
    if tier != SLOT_TIER_FULL:
        if language == "en":
            base_prompt += (
                f"\nNote: Content is shown in a compact tile ({screen_w}×{screen_h}px, layout tier {tier}). "
                "Keep text short."
            )
        elif language == "zh":
            base_prompt += (
                f"\n注意：该内容将在较小的显示区域（{screen_w}×{screen_h}像素，档位{tier}）呈现，请保持简短。"
            )
        elif language == "hr":
            base_prompt += (
                f"\nNapomena: prikaz je u kompaktnom okviru ({screen_w}×{screen_h} px, {tier}). Drži tekst kratak."
            )
        else:
            base_prompt += (
                f"\nNote: Content is shown in a compact tile ({screen_w}×{screen_h}px). Keep text short."
            )

    mode_id = mode_def.get("mode_id", "CUSTOM")
    logger.info(f"[JSONContent] Generating content for {mode_id} via {provider}/{model}")

    # Load recent content hashes for dedup
    recent_hashes: list[str] = []
    dedup_hint = ""
    if mac and ctype in ("llm", "llm_json") and not DISABLE_DEDUP:
        try:
            from .stats_store import get_recent_content_hashes, get_recent_content_summaries
            recent_hashes = await get_recent_content_hashes(mac, mode_id, limit=20)
            summaries = await get_recent_content_summaries(mac, mode_id, limit=3)
            if summaries:
                if language == "en":
                    dedup_hint = "\nAvoid repeating these recent topics: " + "; ".join(summaries)
                else:
                    dedup_hint = "\ntranslated：" + "；".join(summaries)
        except (OSError, TypeError, ValueError):
            logger.warning("[JSONContent] Failed to load dedup context for %s:%s", mac, mode_id, exc_info=True)

    for attempt in range(1 + DEDUP_MAX_RETRIES):
        prompt = base_prompt
        if attempt > 0 and dedup_hint:
            prompt += dedup_hint

        llm_ok = False
        api_key_invalid = False
        try:
            text = await _call_llm(provider, model, prompt, temperature=temperature, api_key=api_key, base_url=llm_base_url)
            llm_ok = True
        except (LLMKeyMissingError, httpx.HTTPError, HTTPStatusError, OpenAIError, OSError, TypeError, ValueError) as e:
            # translated LLM translated（translated OpenAI/DeepSeek translated BadRequestError translated），
            # translated 4xx/5xx translated 500，translated fallback translated。
            logger.error(f"[JSONContent] LLM call failed for {mode_id}: {e}")
            if DISABLE_FALLBACK:
                result = {"text": f"[LLM_ERROR] {e}", "_is_fallback": True, "_llm_used": True, "_llm_ok": False}
                return _apply_post_process(result, content_cfg)
            # translated API key translatedinvalidtranslated（401/403 translated），translated api_key_invalid translated
            if isinstance(e, LLMKeyMissingError):
                api_key_invalid = True
                logger.warning(f"[JSONContent] API key missing or invalid for {mode_id}: {e}")
            elif isinstance(e, HTTPStatusError):
                status_code = e.response.status_code if hasattr(e, "response") and e.response else None
                if status_code in (401, 403):
                    api_key_invalid = True
                    logger.warning(f"[JSONContent] API key invalid or expired for {mode_id}: HTTP {status_code}")
            elif isinstance(e, OpenAIError):
                # OpenAI/translated SDK translated
                # translated「translated」translated API key translated，translated Model Not Exist translated key translated。
                error_message = str(e).lower()
                error_code = getattr(e, "status_code", None) or getattr(e, "code", None)
                if (
                    error_code in (401, 403)
                    or "401" in error_message
                    or "403" in error_message
                    or "unauthorized" in error_message
                    or "auth" in error_message
                    or "api key" in error_message
                    or "apikey" in error_message
                ):
                    api_key_invalid = True
                    logger.warning(f"[JSONContent] API key invalid or expired for {mode_id}: {e}")
            fb = dict(fallback)
            # translated，translated/translated
            fb["_is_fallback"] = True
            fb["_used_fallback"] = True
            # Mark LLM status for downstream billing/observability.
            fb["_llm_used"] = True
            fb["_llm_ok"] = False
            if api_key_invalid:
                fb["_api_key_invalid"] = True
            return fb

        if ctype == "llm":
            result = _parse_llm_output(text, content_cfg, fallback)
        elif ctype == "llm_json":
            result = _parse_llm_json_output(text, content_cfg, fallback)
        else:
            result = {"text": text}

        if not _validate_content_quality(result, content_cfg.get("output_schema")):
            logger.warning(f"[JSONContent] Quality check failed for {mode_id}, using fallback")
            if DISABLE_FALLBACK:
                result["_is_fallback"] = True
                result["_llm_used"] = True
                result["_llm_ok"] = llm_ok
                return _apply_post_process(result, content_cfg)
            fb = _apply_post_process(dict(fallback), content_cfg)
            fb["_is_fallback"] = True
            fb["_used_fallback"] = True
            fb["_llm_used"] = True
            fb["_llm_ok"] = llm_ok
            return fb

        content_hash = _compute_content_hash(result)
        if content_hash not in recent_hashes:
            break
        logger.info(f"[JSONContent] Dedup retry {attempt + 1} for {mode_id} (hash collision)")

    result = _apply_post_process(result, content_cfg)
    result = await _prefetch_images(result, mode_def)
    # Mark LLM status for downstream billing/observability.
    result["_llm_used"] = True
    result["_llm_ok"] = True
    return result


async def _generate_computed_content(mode_def: dict, content_cfg: dict, fallback: dict, **kwargs) -> dict:
    provider = content_cfg.get("provider", "")
    if provider == "countdown":
        from .content import generate_countdown_content
        config = content_cfg.get("config", {})
        cfg = dict(config if config else (kwargs.get("config") or {}))
        mode_settings = (kwargs.get("config") or {}).get("mode_settings", {})
        if isinstance(mode_settings, dict):
            events = mode_settings.get("countdownEvents")
            if isinstance(events, list):
                cfg["countdownEvents"] = events
        mode_overrides = (kwargs.get("config") or {}).get("mode_overrides", {})
        if isinstance(mode_overrides, dict):
            override = mode_overrides.get("COUNTDOWN")
            if isinstance(override, dict):
                override_events = override.get("countdownEvents")
                if not isinstance(override_events, list):
                    override_events = override.get("events")
                if isinstance(override_events, list):
                    cfg["countdownEvents"] = [
                        {
                            "name": str(ev.get("name", "")),
                            "date": str(ev.get("date", "")),
                            "type": "countup" if ev.get("type") == "countup" else "countdown",
                        }
                        for ev in override_events
                        if isinstance(ev, dict)
                    ]
        return await generate_countdown_content(config=cfg)
    if provider == "daily_meta":
        from datetime import datetime as _dt
        date_ctx = kwargs.get("date_ctx", {}) or {}
        lang = kwargs.get("language", "zh")
        result = dict(fallback)
        if lang == "en":
            _MONTH_EN = ["January", "February", "March", "April", "May", "June",
                         "July", "August", "September", "October", "November", "December"]
            _WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            _now = _dt.now()
            month_idx = _now.month - 1
            weekday_idx = date_ctx.get("weekday", _now.weekday())
            result.update({
                "year": date_ctx.get("year"),
                "day": date_ctx.get("day"),
                "month_cn": _MONTH_EN[month_idx],
                "weekday_cn": _WEEKDAY_EN[weekday_idx],
                "day_of_year": date_ctx.get("day_of_year"),
                "days_in_year": date_ctx.get("days_in_year"),
            })
        else:
            result.update({
                "year": date_ctx.get("year"),
                "day": date_ctx.get("day"),
                "month_cn": date_ctx.get("month_cn"),
                "weekday_cn": date_ctx.get("weekday_cn"),
                "day_of_year": date_ctx.get("day_of_year"),
                "days_in_year": date_ctx.get("days_in_year"),
            })
        return result
    if provider == "lifebar":
        import calendar
        from datetime import datetime
        now = datetime.now()
        date_ctx = kwargs.get("date_ctx", {}) or {}
        cfg = kwargs.get("config") or {}
        lang = kwargs.get("language", "zh")

        day_of_year = date_ctx.get("day_of_year") or now.timetuple().tm_yday
        days_in_year = date_ctx.get("days_in_year") or 365
        year_pct = round(day_of_year / days_in_year * 100, 1)

        days_in_month = calendar.monthrange(now.year, now.month)[1]
        month_pct = round(now.day / days_in_month * 100, 1)

        weekday_num = now.weekday() + 1
        week_pct = round(weekday_num / 7 * 100, 1)

        birth_year = int(cfg.get("birth_year", 0)) or 1995
        life_expect = int(cfg.get("life_expect", 0)) or 80
        age = now.year - birth_year
        life_pct = min(round(age / life_expect * 100, 1), 100.0)

        if lang == "en":
            _MONTH_EN_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            return {
                "year_pct": year_pct, "year_label": f"{now.year} elapsed",
                "month_pct": month_pct, "month_label": _MONTH_EN_SHORT[now.month - 1],
                "week_pct": week_pct, "week_label": "Week",
                "life_pct": life_pct, "life_label": "Life",
                "day_of_year": day_of_year, "days_in_year": days_in_year,
                "day": now.day, "days_in_month": days_in_month,
                "weekday_num": weekday_num, "week_total": 7,
                "age": age, "life_expect": life_expect,
            }
        return {
            "year_pct": year_pct, "year_label": f"{now.year} translated",
            "month_pct": month_pct, "month_label": f"{now.month}month",
            "week_pct": week_pct, "week_label": "translated",
            "life_pct": life_pct, "life_label": "translated",
            "day_of_year": day_of_year, "days_in_year": days_in_year,
            "day": now.day, "days_in_month": days_in_month,
            "weekday_num": weekday_num, "week_total": 7,
            "age": age, "life_expect": life_expect,
        }

    if provider == "memo":
        config = kwargs.get("config") or {}
        lang = kwargs.get("language", "zh")
        mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}
        memo_text = mode_settings.get("memo_text", "") if isinstance(mode_settings.get("memo_text", ""), str) else ""
        if not memo_text:
            memo_text = config.get("memo_text", "")
        memo_text = memo_text if isinstance(memo_text, str) else ""
        if not memo_text:
            default_hint = "Set your memo in the config page." if lang == "en" else "translated"
            memo_text = fallback.get("memo_text", default_hint)
        return {"memo_text": memo_text}

    if provider == "habit":
        config = kwargs.get("config") or {}
        lang = kwargs.get("language", "zh")
        configured_items = None
        mo = config.get("mode_overrides", {})
        if isinstance(mo, dict):
            habit_ov = mo.get("HABIT", {})
            if isinstance(habit_ov, dict):
                configured_items = habit_ov.get("habitItems")

        habits = []
        if isinstance(configured_items, list) and configured_items:
            for item in configured_items:
                if isinstance(item, dict):
                    n = item.get("name", "")
                    done = bool(item.get("done", False))
                elif isinstance(item, str):
                    n = item
                    done = False
                else:
                    continue
                if n:
                    habits.append({"name": n, "done": done, "status": "●" if done else "○"})

        completed = sum(1 for h in habits if h.get("done"))
        total = len(habits) if habits else 0
        if habits:
            lines = [f"{h['name']} {h['status']}" for h in habits]
            if lang == "en":
                lines.append(f"\nCompleted {completed}/{total} today")
            else:
                lines.append(f"\ntranslated {completed}/{total} translated")
            summary = "\n".join(lines)
        else:
            summary = fallback.get("summary", "")
        return {
            "habits": habits,
            "summary": summary,
            "week_progress": completed,
            "week_total": total,
        }

    if provider == "calendar_grid":
        import calendar as cal_mod
        from datetime import datetime
        from zhdate import ZhDate
        from .config import SOLAR_FESTIVALS, LUNAR_FESTIVALS, SOLAR_TERMS

        lang = kwargs.get("language", "zh")
        is_en = lang == "en"

        EN_HOLIDAYS: dict[tuple[int, int], str] = {
            (1, 1): "New Year",
            (2, 14): "Valentine",
            (3, 8): "Women's",
            (3, 17): "St Patrick",
            (4, 1): "April Fool",
            (4, 22): "Earth Day",
            (5, 1): "May Day",
            (6, 1): "Children",
            (7, 4): "July 4th",
            (10, 31): "Halloween",
            (11, 11): "Veterans",
            (12, 24): "Xmas Eve",
            (12, 25): "Christmas",
            (12, 31): "NYE",
        }

        def _en_floating_holidays(y: int, m: int) -> dict[int, str]:
            result: dict[int, str] = {}
            if m == 1:
                _jan1_wd = datetime(y, 1, 1).weekday()
                mlk = 15 + (0 - _jan1_wd) % 7 + 7
                result[mlk] = "MLK Day"
            if m == 2:
                _feb1_wd = datetime(y, 2, 1).weekday()
                pres = 15 + (0 - _feb1_wd) % 7 + 7
                result[pres] = "President"
            if m == 5:
                last_mon = 31
                while datetime(y, 5, last_mon).weekday() != 0:
                    last_mon -= 1
                result[last_mon] = "Memorial"
            if m == 9:
                _sep1_wd = datetime(y, 9, 1).weekday()
                labor = 1 + (0 - _sep1_wd) % 7
                result[labor] = "Labor Day"
            if m == 10:
                _oct1_wd = datetime(y, 10, 1).weekday()
                columbus = 8 + (0 - _oct1_wd) % 7
                result[columbus] = "Columbus"
            if m == 11:
                _nov1_wd = datetime(y, 11, 1).weekday()
                thx = 22 + (3 - _nov1_wd) % 7
                result[thx] = "Thxgiving"
            if m == 3 or m == 4:
                import math
                a = y % 19; b, c = divmod(y, 100); d, e = divmod(b, 4)
                f = (b + 8) // 25; g = (b - f + 1) // 3
                h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4)
                l = (32 + 2 * e + 2 * i - h - k) % 7
                em = (a + 11 * h + 22 * l) // 451
                easter_m = (h + l - 7 * em + 114) // 31
                easter_d = ((h + l - 7 * em + 114) % 31) + 1
                if easter_m == m:
                    result[easter_d] = "Easter"
            return result

        LUNAR_DAY_NAMES = [
            "", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated",
            "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated",
            "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated", "translated",
        ]
        _MONTH_EN = ["", "January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"]

        now = datetime.now()
        year, month, day = now.year, now.month, now.day
        first_weekday, days_in_month = cal_mod.monthrange(year, month)
        rows: list[list[str]] = []
        week: list[str] = [""] * first_weekday
        for d in range(1, days_in_month + 1):
            week.append(str(d))
            if len(week) == 7:
                rows.append(week)
                week = []
        if week:
            week.extend([""] * (7 - len(week)))
            rows.append(week)

        config = kwargs.get("config") or {}
        mode_settings = config.get("mode_settings", {})
        if not isinstance(mode_settings, dict):
            mode_settings = {}
        reminders = mode_settings.get("reminders", {})
        if not isinstance(reminders, dict):
            reminders = {}
        mo = config.get("mode_overrides", {})
        if isinstance(mo, dict):
            cal_ov = mo.get("CALENDAR", {})
            if isinstance(cal_ov, dict) and isinstance(cal_ov.get("reminders"), dict):
                reminders = {**reminders, **cal_ov["reminders"]}

        day_labels: dict[str, str] = {}
        day_label_types: dict[str, str] = {}
        today_lunar = ""
        today_festival = ""
        for d in range(1, days_in_month + 1):
            ds = str(d)
            reminder_key = f"{month}-{d}"
            if reminder_key in reminders:
                text = str(reminders[reminder_key])
                max_len = 8 if is_en else 5
                day_labels[ds] = (text[:max_len] + "…") if len(text) > max_len else text
                day_label_types[ds] = "reminder"
                continue
            if is_en:
                floating = _en_floating_holidays(year, month)
                hol = EN_HOLIDAYS.get((month, d), "") or floating.get(d, "")
                day_labels[ds] = hol
                day_label_types[ds] = "festival" if hol else ""
                if d == day:
                    today_festival = hol
                continue
            solar_fest = SOLAR_FESTIVALS.get((month, d), "")
            solar_term = SOLAR_TERMS.get((year, month, d), "")
            try:
                zh = ZhDate.from_datetime(datetime(year, month, d))
                lunar_fest = LUNAR_FESTIVALS.get((zh.lunar_month, zh.lunar_day), "")
                lunar_name = LUNAR_DAY_NAMES[zh.lunar_day] if zh.lunar_day < len(LUNAR_DAY_NAMES) else ""
            except (ValueError, OverflowError):
                lunar_fest = ""
                lunar_name = ""

            if solar_fest or lunar_fest:
                day_labels[ds] = solar_fest or lunar_fest
                day_label_types[ds] = "festival"
            elif solar_term:
                day_labels[ds] = solar_term
                day_label_types[ds] = "solar_term"
            else:
                day_labels[ds] = lunar_name
                day_label_types[ds] = "lunar"

            if d == day:
                try:
                    zh_today = ZhDate.from_datetime(now)
                    today_lunar = f"lunar{zh_today.chinese()}"
                except (ValueError, OverflowError):
                    today_lunar = ""
                today_festival = solar_fest or lunar_fest or solar_term

        today_key = f"{month}-{day}"
        if is_en:
            reminder_hint = f"Today's reminder: {reminders[today_key]}" if today_key in reminders else ""
            cal_title = f"{_MONTH_EN[month]} {year}"
            weekday_headers = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        else:
            reminder_hint = f"translated: {reminders[today_key]}" if today_key in reminders else ""
            cal_title = f"{year}year{month}month"
            weekday_headers = ["translated", "translated", "translated", "translated", "translated", "translated", "day"]

        return {
            "calendar_title": cal_title,
            "weekday_headers": weekday_headers,
            "calendar_rows": rows,
            "today_day": str(day),
            "day_labels": day_labels,
            "day_label_types": day_label_types,
            "lunar_date": today_lunar,
            "festival": today_festival,
            "reminder_hint": reminder_hint,
        }

    if provider == "timetable":
        from datetime import datetime
        lang = kwargs.get("language", "zh")
        is_en = lang == "en"
        now = datetime.now()
        config = kwargs.get("config") or {}
        mode_settings = config.get("mode_settings", {})
        if not isinstance(mode_settings, dict):
            mode_settings = {}
        mo = config.get("mode_overrides", {})
        if isinstance(mo, dict):
            tt_ov = mo.get("TIMETABLE", {})
            if isinstance(tt_ov, dict):
                if "style" in tt_ov:
                    mode_settings = {**mode_settings, **tt_ov}

        style = str(mode_settings.get("style", "daily"))
        periods = mode_settings.get("periods")
        courses = mode_settings.get("courses")

        if not isinstance(periods, list) or not isinstance(courses, dict):
            style = "weekly"
            periods = ["08:00-09:30", "10:00-11:30", "14:00-15:30", "16:00-17:30"]
            if is_en:
                courses = {
                    "0-0": "Calculus/A201", "0-2": "Linear Algebra/A201",
                    "1-1": "English/B305", "1-3": "PE/Gym",
                    "2-0": "Data Struct/C102", "2-2": "Networks/C102",
                    "3-1": "Probability/A201", "3-3": "Politics/D405",
                    "4-0": "OS/C102",
                }
            else:
                courses = {
                    "0-0": "translated/A201", "0-2": "translated/A201",
                    "1-1": "translated/B305", "1-3": "translated/translated",
                    "2-0": "translated/C102", "2-2": "translated/C102",
                    "3-1": "translated/A201", "3-3": "translated/D405",
                    "4-0": "translated/C102",
                }

        if is_en:
            weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            weekdays_short = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        else:
            weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            weekdays_short = ["translated", "translated", "translated", "translated", "translated"]

        wd = now.weekday()
        current_day = wd if wd < 5 else -1

        current_period = -1
        for pi, p_label in enumerate(periods):
            try:
                start_part = p_label.split("-")[0].strip()
                parts = start_part.replace("：", ":").split(":")
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                if now.hour > h or (now.hour == h and now.minute >= m):
                    current_period = pi
            except (ValueError, IndexError):
                pass

        if style == "weekly":
            grid: list[list[str]] = []
            for pi in range(len(periods)):
                row = []
                for di in range(5):
                    row.append(str(courses.get(f"{di}-{pi}", "")))
                grid.append(row)
            if is_en:
                title = f"{weekday_names[wd]} · This Week" if wd < 7 else "This Week"
            else:
                title = f"{weekday_names[wd]} · translated" if wd < 7 else "translated"
            return {
                "style": "weekly",
                "periods": periods,
                "grid": grid,
                "current_day": current_day,
                "current_period": current_period,
                "weekdays": weekdays_short,
                "timetable_title": title,
            }

        slots = []
        if current_day >= 0:
            for pi, p_label in enumerate(periods):
                val = str(courses.get(f"{current_day}-{pi}", ""))
                if not val:
                    continue
                if "/" in val:
                    name, location = val.split("/", 1)
                else:
                    name, location = val, ""
                slots.append({
                    "time": p_label,
                    "name": name,
                    "location": location,
                    "current": pi == current_period,
                })
        if is_en:
            title = f"{weekday_names[wd]} · Today" if wd < 7 else "Today"
        else:
            title = f"{weekday_names[wd]} · translated" if wd < 7 else "translated"
        return {
            "style": "daily",
            "timetable_title": title,
            "slots": slots,
            "slot_count": len(slots),
            "current_day": current_day,
            "current_period": current_period,
        }

    return dict(fallback)


async def _generate_external_data_content(mode_def: dict, content_cfg: dict, fallback: dict, **kwargs) -> dict:
    from .content import (
        fetch_hn_top_stories,
        fetch_ph_top_product,
        fetch_v2ex_hot,
        summarize_briefing_content,
        generate_briefing_insight,
    )

    provider = content_cfg.get("provider", "")
    llm_provider = kwargs.get("llm_provider") or DEFAULT_LLM_PROVIDER
    llm_model = kwargs.get("llm_model") or DEFAULT_LLM_MODEL
    api_key = kwargs.get("api_key")
    llm_base_url = kwargs.get("llm_base_url")
    language = kwargs.get("language", "zh") or "zh"

    if provider == "briefing":
        hn_limit = int(content_cfg.get("hn_limit", 2))
        v2ex_limit = int(content_cfg.get("v2ex_limit", 1))
        summarize = bool(content_cfg.get("summarize", True))
        include_insight = bool(content_cfg.get("include_insight", True))

        import asyncio as _asyncio
        hn_items, ph_item, v2ex_items = await _asyncio.gather(
            fetch_hn_top_stories(limit=hn_limit),
            fetch_ph_top_product(),
            fetch_v2ex_hot(limit=v2ex_limit),
        )
        if not hn_items and not ph_item and not v2ex_items:
            fb = dict(fallback)
            fb["_is_fallback"] = True
            fb["_used_fallback"] = True
            fb["_llm_used"] = False
            fb["_llm_ok"] = False
            return fb
        
        llm_failed = False
        if summarize:
            summarized_hn, summarized_ph = await summarize_briefing_content(
                hn_items, ph_item, llm_provider, llm_model, api_key=api_key, llm_base_url=llm_base_url, language=language
            )
            # translated None，translated summarize failedtranslated
            if summarized_hn is None or summarized_ph is None:
                llm_failed = True
            else:
                hn_items = summarized_hn
                ph_item = summarized_ph
        
        insight = ""
        if include_insight:
            insight = await generate_briefing_insight(hn_items, ph_item, llm_provider, llm_model, api_key=api_key, llm_base_url=llm_base_url, language=language)
            # translated None，translated insight generatefailedtranslated
            if insight is None:
                llm_failed = True
                insight = ""
        
        result = dict(fallback)
        ph_name = ""
        ph_tagline = ""
        if isinstance(ph_item, dict):
            ph_name = str(ph_item.get("name", ""))
            ph_tagline = str(ph_item.get("tagline", ""))
        result.update({
            "hn_items": hn_items or result.get("hn_items", []),
            "ph_item": ph_item or result.get("ph_item", {}),
            "v2ex_items": v2ex_items or result.get("v2ex_items", []),
            "insight": insight or result.get("insight", ""),
            "ph_name": ph_name,
            "ph_tagline": ph_tagline,
        })
        
        # translated LLM translated
        if summarize or include_insight:
            result["_llm_used"] = True
            if llm_failed:
                result["_llm_ok"] = False
                result["_used_fallback"] = True
                logger.warning(f"[JSONContent] BRIEFING LLM calls failed, marked as fallback")
            else:
                result["_llm_ok"] = True
        
        return result

    if provider == "weather_forecast":
        from .config import SCREEN_HEIGHT, SCREEN_WIDTH
        from .context import extract_location_settings, get_weather_forecast
        try:
            config = kwargs.get("config") or {}
            mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}
            sw = int(kwargs.get("screen_w") or SCREEN_WIDTH)
            sh = int(kwargs.get("screen_h") or SCREEN_HEIGHT)
            tier = classify_slot_tier(sw, sh)
            if tier == SLOT_TIER_FULL:
                days = mode_settings.get("forecast_days", 4)
                if not isinstance(days, int):
                    days = 4
                days = max(1, min(7, days))
            else:
                st_grid = str(kwargs.get("slot_type") or "").strip().upper()
                if st_grid == "SMALL":
                    days = 2
                elif st_grid == "WIDE":
                    days = 4
                elif st_grid == "TALL":
                    days = 3
                elif st_grid == "FULL":
                    days = 7
                elif st_grid:
                    days = 3
                else:
                    shape = classify_slot_shape(sw, sh)
                    if shape == SLOT_SHAPE_LARGE or tier == SLOT_TIER_LG:
                        days = 7
                    elif shape == SLOT_SHAPE_WIDE:
                        days = 4
                    elif shape == SLOT_SHAPE_TALL:
                        days = 3
                    elif shape == SLOT_SHAPE_SMALL:
                        days = 2
                    else:
                        days = 3
            data = await get_weather_forecast(
                days=days,
                language=kwargs.get("language", "zh") or "zh",
                **extract_location_settings(config),
            )
            if not data:
                return dict(fallback)
            if not data.get("today_temp") or data["today_temp"] == "--":
                return dict(fallback)
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get weather forecast: {e}", exc_info=True)
            return dict(fallback)

    if provider == "halo_f1":
        from .f1 import get_halo_f1_snapshot
        try:
            config = kwargs.get("config") or {}
            timezone_name = str(config.get("timezone", "") or "").strip()
            mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}
            top_n = mode_settings.get("top_n", 20)
            standings_view = str(mode_settings.get("standings_view", "both") or "both").strip().lower()
            if not isinstance(top_n, int):
                top_n = 20
            top_n = max(3, min(20, top_n))
            if standings_view not in {"both", "drivers", "constructors"}:
                standings_view = "both"

            data = await get_halo_f1_snapshot(
                timezone_name=timezone_name,
                top_n=top_n,
                standings_view=standings_view,
            )
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, KeyError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get Halo F1 data: {e}", exc_info=True)
            return dict(fallback)

    if provider == "halo_f1_news":
        from .f1 import get_halo_f1_news
        try:
            config = kwargs.get("config") or {}
            mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}
            item_limit = mode_settings.get("item_limit", 5)
            if not isinstance(item_limit, int):
                item_limit = 5
            item_limit = max(3, min(8, item_limit))

            data = await get_halo_f1_news(limit=item_limit)
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, KeyError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get Halo F1 news: {e}", exc_info=True)
            return dict(fallback)

    if provider == "halo_f1_results":
        from .f1 import get_halo_f1_results
        try:
            config = kwargs.get("config") or {}
            mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}
            item_limit = mode_settings.get("item_limit", 10)
            if not isinstance(item_limit, int):
                item_limit = 10
            item_limit = max(5, min(20, item_limit))

            data = await get_halo_f1_results(limit=item_limit)
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, KeyError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get Halo F1 results: {e}", exc_info=True)
            return dict(fallback)

    if provider == "halo_f1_weekend":
        from .f1 import get_halo_f1_weekend
        try:
            config = kwargs.get("config") or {}
            timezone_name = str(config.get("timezone", "") or "").strip()
            language = str(kwargs.get("language", "en") or "en")

            data = await get_halo_f1_weekend(timezone_name=timezone_name, language=language)
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, KeyError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get Halo F1 weekend: {e}", exc_info=True)
            return dict(fallback)

    if provider == "bf6_profile":
        from .bf6 import get_bf6_profile_snapshot
        try:
            config = kwargs.get("config") or {}
            mode_settings = config.get("mode_settings", {}) if isinstance(config.get("mode_settings", {}), dict) else {}

            username = str(mode_settings.get("bf6_username", "") or "").strip()
            platform = str(mode_settings.get("bf6_platform", "pc") or "pc").strip().lower()

            if not username:
                fb = dict(fallback)
                fb["error"] = "Set BF6 username in mode settings"
                return fb

            data = await get_bf6_profile_snapshot(username=username, platform=platform)
            merged = dict(fallback)
            merged.update(data)
            return merged
        except (httpx.HTTPError, TypeError, ValueError, KeyError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Failed to get BF6 profile: {e}", exc_info=True)
            fb = dict(fallback)
            fb["error"] = "BF6 profile unavailable"
            return fb

    return dict(fallback)


async def _generate_image_gen_content(mode_def: dict, content_cfg: dict, fallback: dict, **kwargs) -> dict:
    provider = content_cfg.get("provider", "")
    if provider == "text2image":
        from .content import generate_artwall_content
        mode_id = str(mode_def.get("mode_id", "") or "").upper()
        mode_display_name = str(mode_def.get("display_name", "") or "")
        mode_description = str(mode_def.get("description", "") or "")
        prompt_hint = str(content_cfg.get("prompt_hint", "") or "")
        prompt_template = str(content_cfg.get("prompt_template", "") or "")
        fallback_title = str(fallback.get("artwork_title", "") or "")
        api_key = kwargs.get("api_key")
        llm_provider = kwargs.get("llm_provider") or DEFAULT_LLM_PROVIDER
        llm_model = kwargs.get("llm_model") or DEFAULT_LLM_MODEL
        try:
            result = await generate_artwall_content(
                date_str=kwargs.get("date_str", ""),
                weather_str=kwargs.get("weather_str", ""),
                festival=kwargs.get("festival", ""),
                colors=int(kwargs.get("colors", 2) or 2),
                llm_provider=llm_provider,
                llm_model=llm_model,
                image_provider=kwargs.get("image_provider") or DEFAULT_IMAGE_PROVIDER,
                image_model=kwargs.get("image_model") or DEFAULT_IMAGE_MODEL,
                mode_display_name=mode_display_name,
                mode_description=mode_description,
                prompt_hint=prompt_hint,
                prompt_template=prompt_template,
                fallback_title=fallback_title,
                image_api_key=kwargs.get("image_api_key"),
                api_key=api_key,
                llm_base_url=kwargs.get("llm_base_url"),
                language=kwargs.get("language", "zh"),
            )
            # translated；translated JSON translated fallback/fallback_pool
            if mode_id != "ARTWALL":
                result["artwork_title"] = ""
                result["description"] = ""
            if result.get("image_url"):
                # successtranslated
                result["_llm_used"] = True
                result["_llm_ok"] = True
                return result
            else:
                # translated，translated fallback
                logger.warning(f"[JSONContent] image_gen for {mode_id} returned no image_url, using fallback")
                fb = dict(fallback)
                fb["_llm_used"] = True
                fb["_llm_ok"] = False
                fb["_used_fallback"] = True
                return fb
        except Exception as e:
            logger.warning(f"[JSONContent] image_gen failed for {mode_id}: {e}", exc_info=True)
            fb = dict(fallback)
            fb["_llm_used"] = True
            fb["_llm_ok"] = False
            fb["_used_fallback"] = True
            return fb
    return dict(fallback)


async def _generate_composite_content(mode_def: dict, content_cfg: dict, fallback: dict, **kwargs) -> dict:
    steps = content_cfg.get("steps", [])
    result: dict[str, Any] = {}
    any_llm_used = False
    any_llm_failed = False
    
    for step in steps:
        try:
            resolved_step = step
            if result and step.get("type") == "llm":
                pt = step.get("prompt_template", "")
                if pt and "{" in pt:
                    import re as _re
                    def _repl(m: _re.Match, _acc=result) -> str:
                        if m.group(1) == "context":
                            return m.group(0)
                        v = _acc.get(m.group(1), "")
                        return str(v) if v else ""
                    resolved_step = {**step, "prompt_template": _re.sub(r"\{(\w+)\}", _repl, pt)}
            step_mode_def = {
                "mode_id": mode_def.get("mode_id", "COMPOSITE"),
                "content": resolved_step,
            }
            part = await generate_json_mode_content(step_mode_def, **kwargs)
            if isinstance(part, dict):
                # translated step translated LLM
                if part.get("_llm_used"):
                    any_llm_used = True
                    if not part.get("_llm_ok", True):
                        any_llm_failed = True
                # translated，translated
                part_clean = {k: v for k, v in part.items() if not k.startswith("_")}
                result.update(part_clean)
        except (LLMKeyMissingError, httpx.HTTPError, OSError, TypeError, ValueError, JSONDecodeError) as e:
            logger.warning(f"[JSONContent] Step failed in composite mode {mode_def.get('mode_id', 'UNKNOWN')}: {e}", exc_info=True)
            any_llm_failed = True
            # Continue with next step instead of failing entirely
            continue
    
    if not result:
        fb = dict(fallback)
        if any_llm_used:
            fb["_llm_used"] = True
            fb["_llm_ok"] = False
            fb["_used_fallback"] = True
        return fb
    
    merged = dict(fallback)
    merged.update(result)
    
    # translated LLM translated
    if any_llm_used:
        merged["_llm_used"] = True
        if any_llm_failed:
            merged["_llm_ok"] = False
            merged["_used_fallback"] = True
        else:
            merged["_llm_ok"] = True
    
    return merged


def _apply_post_process(result: dict, content_cfg: dict) -> dict:
    """Apply optional post-processing rules to content fields."""
    rules = content_cfg.get("post_process", {})
    for field_name, rule in rules.items():
        val = result.get(field_name, "")
        if not isinstance(val, str):
            continue
        if rule == "first_char":
            result[field_name] = val[:1] if val else ""
        elif rule == "strip_quotes":
            result[field_name] = val.strip('""\u201c\u201d\u300c\u300d')
    return result


def _parse_llm_output(text: str, content_cfg: dict, fallback: dict) -> dict:
    """Parse LLM text output according to output_format."""
    fmt = content_cfg.get("output_format", "raw")

    if fmt == "text_split":
        return _parse_text_split(text, content_cfg, fallback)
    elif fmt == "json":
        return _parse_json_output(text, content_cfg, fallback)
    else:
        fields = content_cfg.get("output_fields", ["text"])
        return {fields[0]: text}


def _parse_text_split(text: str, content_cfg: dict, fallback: dict) -> dict:
    """Split text by separator and map to output_fields."""
    sep = content_cfg.get("output_separator", "|")
    fields = content_cfg.get("output_fields", ["text"])
    parts = text.split(sep)

    result = {}
    for i, field_name in enumerate(fields):
        if i < len(parts):
            result[field_name] = parts[i].strip().strip('""\u201c\u201d')
        else:
            result[field_name] = fallback.get(field_name, "")
    return result


def _parse_json_output(text: str, content_cfg: dict, fallback: dict) -> dict:
    """Parse JSON from LLM response."""
    try:
        cleaned = _clean_json_response(text)
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return dict(fallback)

        fields = content_cfg.get("output_fields")
        if fields:
            return {f: data.get(f, fallback.get(f, "")) for f in fields}
        return data
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[JSONContent] JSON parse failed: {e}")
        return dict(fallback)


def _parse_llm_json_output(text: str, content_cfg: dict, fallback: dict) -> dict:
    """Parse JSON from LLM response using output_schema for defaults."""
    schema = content_cfg.get("output_schema", {})
    try:
        cleaned = _clean_json_response(text)
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return dict(fallback)

        result = {}
        for field_name, field_def in schema.items():
            default = field_def.get("default", "")
            result[field_name] = data.get(field_name, default)
        return result
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[JSONContent] JSON parse failed: {e}")
        return dict(fallback)
