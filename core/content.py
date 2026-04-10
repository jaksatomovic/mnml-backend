from __future__ import annotations

import datetime
import json
import os
import re
import base64
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import logging
import httpx
from openai import AsyncOpenAI, OpenAIError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .errors import LLMKeyMissingError
from .config import DEFAULT_LLM_PROVIDER, DEFAULT_LLM_MODEL

logger = logging.getLogger(__name__)

_LLM_RECOVERABLE_ERRORS = (
    LLMKeyMissingError,
    OpenAIError,
    httpx.HTTPError,
    ConnectionError,
    TimeoutError,
    ValueError,
)


def _chat_completion_extra_body(provider: str, model: str) -> dict | None:
    """Return provider/model-specific extra_body parameters.

    Aliyun exposes Qwen thinking control via its OpenAI-compatible endpoint.
    Keep qwen3.5-flash on non-thinking mode unless the caller explicitly
    implements a separate switch later.
    """
    return None


def _extract_llm_base_url(ctx) -> str | None:
    """Extract optional LLM base_url from various ctx shapes (dict / ContentContext / None)."""
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        v = (ctx.get("llm_base_url") or "").strip()
        return v or None
    return getattr(ctx, "llm_base_url", None)


def _save_generated_image_bytes(image_bytes: bytes, content_type: str = "image/png") -> str:
    """Persist generated image bytes under runtime_uploads and return URL."""
    backend_root = Path(__file__).resolve().parent.parent
    upload_dir = backend_root / "runtime_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    upload_id = str(uuid.uuid4())
    (upload_dir / f"{upload_id}.bin").write_bytes(image_bytes)
    (upload_dir / f"{upload_id}.json").write_text(
        json.dumps({"content_type": content_type}, ensure_ascii=True),
        encoding="utf-8",
    )
    origin = (os.getenv("INKSIGHT_BACKEND_PUBLIC_BASE") or "http://127.0.0.1:8080").rstrip("/")
    return f"{origin}/api/uploads/{upload_id}"

# LLM Provider configurations
LLM_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "models": {"deepseek-chat": {"name": "DeepSeek Chat", "max_tokens": 1024}},
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models": {
            "gpt-4o-mini": {"name": "GPT-4o mini", "max_tokens": 1024},
            "gpt-4.1-mini": {"name": "GPT-4.1 mini", "max_tokens": 1024},
        },
    },
}

PROMPTS = {
    "DAILY": (
        "translated。Get by translated，translated，translated JSON translated，translated：\n"
        "1. quote: translated（translated，20translated，translated：translated、translated、translated、translated、translated）\n"
        "2. author: translated\n"
        "3. book_title: translated（translated，translated，translated）\n"
        '4. book_author: translated + " translated"\n'
        "5. book_desc: translated（25translated）\n"
        "6. tip: translated（30translated，translated）\n"
        "7. season_text: translated（10translated）\n"
        "translated：translated，translated，translated。translated JSON，translated。\n"
        "translated：{context}"
    ),
}


# ── Shared helpers ───────────────────────────────────────────


def _clean_json_response(text: str) -> str:
    """Remove markdown code fences and extract JSON from LLM responses."""
    cleaned = text.strip()
    # Remove markdown code fences (```json, ```JSON, ``` etc.)
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        cleaned = cleaned.rsplit("```", 1)[0]
    # Try to extract a JSON object if surrounded by other text
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        cleaned = match.group(0)
    return cleaned.strip()


def _build_context_str(
    date_str: str,
    weather_str: str,
    festival: str = "",
    daily_word: str = "",
    upcoming_holiday: str = "",
    days_until: int = 0,
    language: str = "zh",
) -> str:
    def _has_cjk(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))

    if language == "en":
        parts = [f"Date: {date_str}", f"Weather: {weather_str}"]
        if festival and not _has_cjk(festival):
            parts.append(f"Festival: {festival}")
        if upcoming_holiday and days_until > 0 and not _has_cjk(upcoming_holiday):
            parts.append(f"{upcoming_holiday} in {days_until} days")
        if daily_word and not _has_cjk(daily_word):
            parts.append(f"Word of the day: {daily_word}")
    else:
        parts = [f"translated: {date_str}", f"weather: {weather_str}"]
        if festival:
            parts.append(f"festival: {festival}")
        if upcoming_holiday and days_until > 0:
            parts.append(f"{days_until}translated{upcoming_holiday}")
        if daily_word:
            parts.append(f"translated: {daily_word}")
    return ", ".join(parts)


def _build_style_instructions(
    character_tones: list[str] | None, language: str | None, content_tone: str | None
) -> str:
    is_en = language == "en"
    parts = []

    if character_tones:
        safe_tones = [t for t in character_tones if len(t) <= 20 and "\n" not in t]
        if safe_tones:
            names = ", ".join(safe_tones) if is_en else "、".join(safe_tones)
            if is_en:
                parts.append(f"Mimic the speaking style of {names}")
            else:
                parts.append(f"translated「{names}」translated")

    if is_en:
        tone_map = {
            "positive": "uplifting and encouraging",
            "neutral": "balanced and restrained",
            "deep": "reflective and philosophical",
            "humor": "light-hearted and witty",
        }
        if content_tone and content_tone != "neutral":
            parts.append(f"Overall tone should be {tone_map.get(content_tone, 'balanced')}")
    else:
        tone_map_zh = {
            "positive": "translated、translated",
            "neutral": "translated、translated",
            "deep": "translated、translated",
            "humor": "translated、translated",
        }
        if content_tone and content_tone != "neutral":
            parts.append(f"translatedtonetranslated{tone_map_zh.get(content_tone, 'translated')}")

    if is_en:
        parts.append("All output MUST be in English")
        return "\nAdditional style: " + "; ".join(parts) + "."
    if not parts:
        return ""
    return "\ntranslated：" + "；".join(parts) + "。"


def _get_client(
    provider: str = "deepseek", model: str = "deepseek-chat",
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[AsyncOpenAI, int]:
    """Get OpenAI client for specified provider and return max_tokens"""
    # DeepSeek/OpenAI-only backend: fallback to deepseek for unsupported providers.
    provider = (provider or "").strip().lower()
    if provider not in {"deepseek", "openai"}:
        provider = "deepseek"
    user_provided_key = api_key is not None  # translated api_key（translated）
    
    if api_key is None:
        # translated api_key，translatedGet 
        api_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        env_key = api_key_map.get(provider, "DEEPSEEK_API_KEY")
        api_key = os.getenv(env_key, "")

    if not api_key or api_key.startswith("sk-your-"):
        # translated api_key translatedinvalid，translated
        if user_provided_key:
            raise LLMKeyMissingError(
                f"translated API key translatedinvalid（provider: {provider}）。translated API key config。"
            )
        else:
            raise LLMKeyMissingError(
                f"Missing or invalid API key for {provider}. Please set the API key in .env file or device config."
            )

    config = LLM_CONFIGS.get(provider, LLM_CONFIGS["deepseek"])
    resolved_base_url = config["base_url"]
    model_config = config["models"].get(model, {"max_tokens": 120})
    max_tokens = model_config["max_tokens"]

    return AsyncOpenAI(api_key=api_key, base_url=resolved_base_url), max_tokens


class LLMClient:
    """Unified LLM client with retry, timeout, and logging."""

    def __init__(self, provider: str = "deepseek", model: str = "deepseek-chat", api_key: str | None = None, base_url: str | None = None):
        self.provider = provider
        self.model = model
        self._client, self._max_tokens = _get_client(provider, model, api_key=api_key, base_url=base_url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((
            ConnectionError,
            TimeoutError,
            httpx.ConnectError,
            httpx.ReadTimeout,
        )),
        before_sleep=lambda rs: logger.warning(
            f"[LLM] Retry {rs.attempt_number}/3 after {type(rs.outcome.exception()).__name__}..."
        ),
        reraise=True,
    )
    async def call(
        self, prompt: str, temperature: float = 0.8, max_tokens: int | None = None,
    ) -> str:
        """Call the LLM with retry logic. Returns response text."""
        request_kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature,
        }
        extra_body = _chat_completion_extra_body(self.provider, self.model)
        if extra_body is not None:
            request_kwargs["extra_body"] = extra_body
        response = await self._client.chat.completions.create(
            **request_kwargs,
        )
        text = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        usage = response.usage
        logger.info(
            f"[LLM] {self.provider}/{self.model} tokens={usage.total_tokens}, finish={finish_reason}"
        )
        if finish_reason == "length":
            logger.warning("[LLM] Content truncated due to max_tokens limit")
        return text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception_type((
        ConnectionError,
        TimeoutError,
        httpx.ConnectError,
        httpx.ReadTimeout,
    )),
    before_sleep=lambda rs: logger.warning(
        f"[LLM] Retry {rs.attempt_number}/3 after {type(rs.outcome.exception()).__name__}..."
    ),
    reraise=True,
)
async def _call_llm(
    provider: str,
    model: str,
    prompt: str,
    temperature: float = 0.8,
    max_tokens: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Unified LLM call: create client, call API, return response text.

    Retries up to 3 times with exponential backoff for transient errors.
    Raises ValueError when the API key is missing (no retry).
    """
    client, default_max_tokens = _get_client(provider, model, api_key=api_key, base_url=base_url)
    request_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens or default_max_tokens,
        "temperature": temperature,
    }
    extra_body = _chat_completion_extra_body(provider, model)
    if extra_body is not None:
        request_kwargs["extra_body"] = extra_body
    response = await client.chat.completions.create(
        **request_kwargs,
    )
    text = response.choices[0].message.content.strip()

    finish_reason = response.choices[0].finish_reason
    usage = response.usage
    logger.info(
        f"[LLM] {provider}/{model} tokens={usage.total_tokens}, finish={finish_reason}"
    )
    if finish_reason == "length":
        logger.warning("[LLM] Content truncated due to max_tokens limit")

    return text


# ── Core content generation ──────────────────────────────────


async def generate_content(
    persona: str,
    date_str: str,
    weather_str: str,
    character_tones: list[str] | None = None,
    language: str | None = None,
    content_tone: str | None = None,
    festival: str = "",
    daily_word: str = "",
    upcoming_holiday: str = "",
    days_until_holiday: int = 0,
    llm_provider: str = "deepseek",
    llm_model: str = "deepseek-chat",
    api_key: str | None = None,
    llm_base_url: str | None = None,
) -> dict:
    context = _build_context_str(
        date_str,
        weather_str,
        festival,
        daily_word,
        upcoming_holiday,
        days_until_holiday,
        language=language or "zh",
    )
    prompt_template = PROMPTS.get(persona)
    if not prompt_template:
        logger.warning(f"[LLM] No prompt template for persona={persona}, returning fallback")
        return _fallback_content(persona)
    prompt = prompt_template.format(context=context)

    style = _build_style_instructions(character_tones, language, content_tone)
    if style:
        prompt += style

    logger.info(f"[LLM] Calling {llm_provider}/{llm_model} for persona={persona}")

    try:
        text = await _call_llm(llm_provider, llm_model, prompt, temperature=0.8, api_key=api_key, base_url=llm_base_url)
    except _LLM_RECOVERABLE_ERRORS as e:
        logger.error(f"[LLM] ✗ FAILED - {type(e).__name__}: {e}")
        return _fallback_content(persona)

    if persona == "DAILY":
        try:
            cleaned = _clean_json_response(text)
            data = json.loads(cleaned)
            return {
                "quote": data.get("quote", ""),
                "author": data.get("author", ""),
                "book_title": data.get("book_title", ""),
                "book_author": data.get("book_author", ""),
                "book_desc": data.get("book_desc", ""),
                "tip": data.get("tip", ""),
                "season_text": data.get("season_text", ""),
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[LLM] ✗ FAILED to parse DAILY JSON: {e}")
            logger.info(f"[LLM] Raw response: {text[:200]}...")
            return _fallback_content("DAILY")

    return {"quote": text, "author": ""}


def _fallback_content(persona: str) -> dict:
    """Fallback content for Python builtin modes when LLM calls fail.

    JSON-defined modes (STOIC, ROAST, ZEN, FITNESS, POETRY) have their own
    fallback data in their JSON definitions — see core/modes/builtin/*.json.
    """
    if persona == "DAILY":
        return {
            "quote": "translated，translated。",
            "author": "translated·translated",
            "book_title": "《translated》",
            "book_author": "translated·translated translated",
            "book_desc": "translated，translated。",
            "tip": "translated，translated，translated。",
            "season_text": "Start of Springtranslated，translated。",
        }
    if persona == "BRIEFING":
        return {
            "hn_items": [
                {"title": "Hacker News API translated", "score": 0},
                {"title": "please try again later", "score": 0},
                {"title": "translated", "score": 0},
            ],
            "ph_item": {"name": "Product Hunt", "tagline": "translatedGet failed"},
            "v2ex_items": [],
            "insight": "translatedGet ，translated。",
        }
    if persona == "COUNTDOWN":
        return {"events": []}
    return {"quote": "...", "author": ""}


# ── Hacker News & Product Hunt ───────────────────────────────


async def fetch_hn_top_stories(limit: int = 3) -> list[dict]:
    """Get  Hacker News translated Top N（translated story）"""
    import asyncio as _asyncio

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json"
            )
            if resp.status_code != 200:
                logger.error(f"[HN] Failed to fetch top stories: {resp.status_code}")
                return []

            story_ids = resp.json()[:limit]

            async def _fetch_one(sid: int) -> dict | None:
                r = await client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                )
                if r.status_code == 200:
                    s = r.json()
                    return {
                        "title": s.get("title", "No title"),
                        "score": s.get("score", 0),
                        "url": s.get("url", ""),
                    }
                return None

            results = await _asyncio.gather(*[_fetch_one(sid) for sid in story_ids])
            stories = [s for s in results if s is not None]

            logger.info(f"[HN] Fetched {len(stories)} stories (concurrent)")
            return stories

    except (httpx.HTTPError, ValueError, TypeError) as e:
        logger.error(f"[HN] Error: {e}")
        return []


async def fetch_ph_top_product() -> dict:
    """Get  Product Hunt translated #1 translated（translated RSS）"""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get("https://www.producthunt.com/feed")
            if resp.status_code != 200:
                logger.error(f"[PH] Failed to fetch RSS: {resp.status_code}")
                return {}

            root = ET.fromstring(resp.content)

            namespaces = {
                "atom": "http://www.w3.org/2005/Atom",
                "media": "http://search.yahoo.com/mrss/",
            }

            items = (
                root.findall(".//item")
                or root.findall(".//entry", namespaces)
                or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            )

            if not items:
                logger.warning(f"[PH] No items found in RSS. Root tag: {root.tag}")
                return {}

            first_item = items[0]

            title = first_item.find("title") or first_item.find(
                "{http://www.w3.org/2005/Atom}title"
            )
            description = (
                first_item.find("description")
                or first_item.find("summary")
                or first_item.find("{http://www.w3.org/2005/Atom}summary")
                or first_item.find("content")
                or first_item.find("{http://www.w3.org/2005/Atom}content")
            )

            tagline_text = ""
            if description is not None and description.text:
                tagline_text = re.sub(r"<[^>]+>", "", description.text).strip()
                tagline_text = tagline_text[:100]

            product = {
                "name": title.text if title is not None else "Unknown Product",
                "tagline": tagline_text,
            }

            logger.info(f"[PH] Fetched product: {product['name']}")
            return product

    except (httpx.HTTPError, ET.ParseError) as e:
        logger.exception("[PH] Error fetching Product Hunt product")
        return {}


# ── V2EX ─────────────────────────────────────────────────────


async def fetch_v2ex_hot(limit: int = 3) -> list[dict]:
    """Get  V2EX translated"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://www.v2ex.com/api/topics/hot.json")
            if resp.status_code == 200:
                topics = resp.json()[:limit]
                return [
                    {
                        "title": t.get("title", ""),
                        "node": t.get("node", {}).get("title", ""),
                    }
                    for t in topics
                ]
            logger.error(f"[V2EX] Failed to fetch hot topics: {resp.status_code}")
    except (httpx.HTTPError, ValueError, TypeError) as e:
        logger.error(f"[V2EX] Error: {e}")
    return []


# ── Briefing mode ────────────────────────────────────────────


async def generate_briefing_insight(
    hn_stories: list[dict],
    ph_product: dict,
    llm_provider: str = "deepseek",
    llm_model: str = "deepseek-chat",
    api_key: str | None = None,
    llm_base_url: str | None = None,
    language: str = "zh",
) -> str:
    """translated LLM translated"""
    hn_summary = "\n".join(
        [f"- {s['title']} ({s['score']} points)" for s in hn_stories[:3]]
    )
    ph_summary = f"Product Hunt #1: {ph_product.get('name', 'N/A')}"

    if language == "en":
        prompt = f"""You are a technology industry analyst. Based on today's Hacker News top stories and the top Product Hunt launch, write one short industry insight in English (under 20 words).

Hacker News Top 3:
{hn_summary}

{ph_summary}

Requirements:
1. Output the insight only, with no prefix or quotes
2. Focus on technology trends or industry movement
3. Keep it concise, sharp, and suitable for a morning briefing
4. All output must be in English"""
    else:
        prompt = f"""translated。Get by translated Hacker News translated Product Hunt translated，translated（30translated）。

Hacker News Top 3:
{hn_summary}

{ph_summary}

translated：
1. translated，translated
2. translated
3. translated，translated"""

    try:
        insight = await _call_llm(llm_provider, llm_model, prompt, temperature=0.7, api_key=api_key, base_url=llm_base_url)
        logger.info(f"[BRIEFING] Generated insight: {insight[:50]}...")
        return insight
    except _LLM_RECOVERABLE_ERRORS as e:
        logger.error(f"[BRIEFING] Failed to generate insight: {e}")
        return None  # translated None translatedfailed


async def summarize_briefing_content(
    stories: list[dict],
    ph_product: dict,
    llm_provider: str = "deepseek",
    llm_model: str = "deepseek-chat",
    api_key: str | None = None,
    llm_base_url: str | None = None,
    language: str = "zh",
) -> tuple[list[dict], dict]:
    """translated LLM translated HN stories translated PH tagline（translated 3-4 translated）"""
    try:
        titles_to_summarize = []
        for i, story in enumerate(stories):
            title = story.get("title", "")
            if title and len(title) >= 20:
                titles_to_summarize.append((i, title))

        ph_tagline = ""
        ph_name = ""
        if ph_product and ph_product.get("tagline") and len(ph_product["tagline"]) > 30:
            ph_name = ph_product.get("name", "")
            ph_tagline = ph_product["tagline"]

        # Build a single batch prompt for all summaries
        if not titles_to_summarize and not ph_tagline:
            return stories, ph_product

        if language == "en":
            prompt_parts = [
                "# Role",
                "You are a tech editor skilled at summarizing technology news in concise English.",
                "",
                "# Tasks",
                "Complete the following summarization tasks in order and return the result in JSON.",
                "",
            ]
        else:
            prompt_parts = [
                "# Role",
                "translated，translated。",
                "",
                "# Tasks",
                "translated，translated JSON translated。",
                "",
            ]

        if titles_to_summarize:
            prompt_parts.append("## HN Stories Summary" if language == "en" else "## HN Stories translated")
            prompt_parts.append(
                "Write an English summary under 20 words for each title:"
                if language == "en"
                else "translated 30 translated："
            )
            for idx, (_, title) in enumerate(titles_to_summarize):
                prompt_parts.append(f"  {idx + 1}. {title}")
            prompt_parts.append("")

        if ph_tagline:
            prompt_parts.append("## Product Hunt Summary" if language == "en" else "## Product Hunt translated")
            prompt_parts.append(f"Product name: {ph_name}" if language == "en" else f"translated：{ph_name}")
            prompt_parts.append(f"Original tagline: {ph_tagline}" if language == "en" else f"translatedSlogan：{ph_tagline}")
            prompt_parts.append(
                "Rewrite it as an English introduction under 20 words."
                if language == "en"
                else "translated 30 translated。"
            )
            prompt_parts.append("")

        prompt_parts.append("# Output (JSON only)" if language == "en" else "# Output (translated JSON)")
        prompt_parts.append('{')
        if titles_to_summarize:
            prompt_parts.append(
                '  "hn_summaries": ["summary 1", "summary 2", ...],'
                if language == "en"
                else '  "hn_summaries": ["translated1", "translated2", ...],'
            )
        if ph_tagline:
            prompt_parts.append(
                '  "ph_summary": "English introduction"'
                if language == "en"
                else '  "ph_summary": "translated"'
            )
        prompt_parts.append('}')

        batch_prompt = "\n".join(prompt_parts)

        text = await _call_llm(
            llm_provider, llm_model, batch_prompt,
            max_tokens=300, temperature=0.5, api_key=api_key, base_url=llm_base_url,
        )
        cleaned = _clean_json_response(text)
        data = json.loads(cleaned)

        # Apply HN summaries
        hn_summaries = data.get("hn_summaries", [])
        summarized_stories = list(stories)
        for summary_idx, (story_idx, _) in enumerate(titles_to_summarize):
            if summary_idx < len(hn_summaries):
                summary = str(hn_summaries[summary_idx]).strip('"').strip("「」")
                summarized_stories[story_idx] = {**stories[story_idx], "summary": summary}

        logger.info(f"[BRIEFING] Batch-summarized {len(titles_to_summarize)} HN stories in 1 LLM call")

        # Apply PH summary
        summarized_ph = ph_product.copy() if ph_product else {}
        if ph_tagline and data.get("ph_summary"):
            summary = str(data["ph_summary"]).strip('"').strip("「」")
            summarized_ph["tagline_original"] = ph_tagline
            summarized_ph["tagline"] = summary
            logger.info("[BRIEFING] Batch-summarized PH tagline")

        return summarized_stories, summarized_ph

    except _LLM_RECOVERABLE_ERRORS + (json.JSONDecodeError, TypeError) as e:
        logger.error(f"[BRIEFING] Batch summarize failed, returning originals: {e}")
        return None, None  


async def generate_briefing_content(
    ctx=None,
    llm_provider: str = "deepseek",
    llm_model: str = "deepseek-chat",
    summarize: bool = True,
    api_key: str | None = None,
) -> dict:
    """generate BRIEFING modetranslated"""
    if ctx is not None:
        llm_provider = ctx.llm_provider
        llm_model = ctx.llm_model
        api_key = ctx.api_key
    language = getattr(ctx, "language", "zh") if ctx is not None else "zh"
    import asyncio as _asyncio

    logger.info("[BRIEFING] Starting content generation...")

    # Fetch HN, PH, and V2EX concurrently
    hn_stories, ph_product, v2ex_topics = await _asyncio.gather(
        fetch_hn_top_stories(limit=2),
        fetch_ph_top_product(),
        fetch_v2ex_hot(limit=1),
    )

    if not hn_stories and not ph_product and not v2ex_topics:
        logger.error("[BRIEFING] All data sources failed, using fallback")
        if language == "en":
            return {
                "hn_items": [
                    {"title": "Hacker News API unavailable", "score": 0},
                    {"title": "Please try again later", "score": 0},
                    {"title": "Or check your network connection", "score": 0},
                ],
                "ph_item": {"name": "Product Hunt", "tagline": "Failed to fetch data"},
                "v2ex_items": [],
                "insight": "Unable to fetch today's tech briefing. Please refresh later.",
            }
        return _fallback_content("BRIEFING")

    if summarize:
        llm_base_url = _extract_llm_base_url(ctx)
        (hn_stories, ph_product), insight = await _asyncio.gather(
            summarize_briefing_content(
                hn_stories, ph_product, llm_provider, llm_model, api_key=api_key, llm_base_url=llm_base_url, language=language
            ),
            generate_briefing_insight(
                hn_stories, ph_product, llm_provider, llm_model, api_key=api_key, llm_base_url=llm_base_url, language=language
            ),
        )
    else:
        llm_base_url = _extract_llm_base_url(ctx)
        insight = await generate_briefing_insight(
            hn_stories, ph_product, llm_provider, llm_model, api_key=api_key, llm_base_url=llm_base_url, language=language
        )

    result = {
        "hn_items": hn_stories if hn_stories else [{"title": "Failed to fetch data", "score": 0}] if language == "en" else [{"title": "translatedGet failed", "score": 0}],
        "ph_item": ph_product if ph_product else {"name": "N/A", "tagline": ""},
        "v2ex_items": v2ex_topics if v2ex_topics else [],
        "insight": insight or ("Unable to fetch today's tech briefing. Please refresh later." if language == "en" else "translatedGet ，translated。"),
    }

    logger.info("[BRIEFING] Content generation complete")
    return result


# ── Countdown mode ───────────────────────────────────────────


async def generate_countdown_content(
    ctx=None,
    config: dict | None = None,
    **kwargs,
) -> dict:
    """generate COUNTDOWN modetranslated — translated，translated LLM"""
    if ctx is not None:
        config = ctx.config
    logger.info("[COUNTDOWN] Computing countdown events...")

    cfg = config or {}
    raw_events = cfg.get("countdownEvents", [])
    language = str(cfg.get("mode_language") or cfg.get("modeLanguage") or "zh").lower()
    content_tone = str(cfg.get("content_tone") or cfg.get("contentTone") or "neutral").lower()

    today = datetime.date.today()
    computed_events = []

    for evt in raw_events:
        name = evt.get("name", "")
        date_str = evt.get("date", "")
        evt_type = evt.get("type", "countdown")

        if not name or not date_str:
            continue

        try:
            target = datetime.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue

        delta = (target - today).days

        if evt_type == "countdown" and delta < 0:
            continue
        if evt_type == "countup":
            delta = abs(delta)

        computed_events.append({
            "name": name,
            "date": date_str,
            "type": evt_type,
            "days": abs(delta) if evt_type == "countdown" else delta,
        })

    # Sort: countdown events by nearest first, then countup
    computed_events.sort(key=lambda e: (0 if e["type"] == "countdown" else 1, e["days"]))

    if not computed_events:
        # Provide default countdown events
        new_year = datetime.date(today.year + 1, 1, 1)
        days_to_ny = (new_year - today).days
        computed_events = [
            {"name": "New Year's Day", "date": str(new_year), "type": "countdown", "days": days_to_ny},
        ]

    logger.info(f"[COUNTDOWN] Computed {len(computed_events)} events")
    primary_event = computed_events[0]
    message = _build_countdown_message(
        primary_event.get("name", ""),
        primary_event.get("type", "countdown"),
        int(primary_event.get("days", 0) or 0),
        language,
        content_tone,
    )
    return {"events": computed_events, "message": message}


def _build_countdown_message(
    name: str,
    evt_type: str,
    days: int,
    language: str,
    content_tone: str,
) -> str:
    safe_name = str(name or "").strip() or ("the day" if language == "en" else "translated")
    tone = content_tone if content_tone in {"positive", "neutral", "deep", "humor"} else "neutral"

    if language == "en":
        if evt_type == "countup":
            templates = {
                "positive": "{name} has begun. Keep the momentum going.",
                "neutral": "Every day after {name} still counts.",
                "deep": "{name} has passed, but its meaning keeps unfolding.",
                "humor": "{name} is already behind you. Nice, now act like a pro.",
            }
        elif days == 0:
            templates = {
                "positive": "It is {name} today. Go make it count.",
                "neutral": "{name} is here today. Stay focused.",
                "deep": "{name} has arrived. Meet it with a steady heart.",
                "humor": "{name} is today. No dramatic exits now.",
            }
        else:
            templates = {
                "positive": "{name} is getting closer. Keep going.",
                "neutral": "Step by step, you are moving toward {name}.",
                "deep": "Before {name} arrives, these days are shaping you.",
                "humor": "{name} is waiting ahead. Breathe, then follow the plan.",
            }
    else:
        if evt_type == "countup":
            templates = {
                "positive": "{name}translated，translated。",
                "neutral": "{name}translated，translated。",
                "deep": "{name}translated，translated。",
                "humor": "{name}translated，translated。",
            }
        elif days == 0:
            templates = {
                "positive": "translated{name}，translated。",
                "neutral": "{name}translated，translated。",
                "deep": "{name}translated，translated。",
                "humor": "{name}translated，translated，translated。",
            }
        else:
            templates = {
                "positive": "{name}translated，translated。",
                "neutral": "translated{name}，translated。",
                "deep": "{name}translated，translated。",
                "humor": "{name}translated，translated，translated。",
            }

    return templates.get(tone, templates["neutral"]).format(name=safe_name)


# ── Artwall mode ─────────────────────────────────────────────


async def generate_artwall_content(
    ctx=None,
    date_str: str = "",
    weather_str: str = "",
    festival: str = "",
    colors: int = 2,
    llm_provider: str = DEFAULT_LLM_PROVIDER,
    llm_model: str = DEFAULT_LLM_MODEL,
    image_provider: str = "deepseek",
    image_model: str = "",
    mode_display_name: str = "",
    mode_description: str = "",
    prompt_hint: str = "",
    prompt_template: str = "",
    fallback_title: str = "",
    image_api_key: str | None = None,
    api_key: str | None = None,
    llm_base_url: str | None = None,
    language: str = "zh",
) -> dict:
    """Generate ARTWALL mode content via text-to-image model."""
    if ctx is not None:
        date_str = ctx.date_str
        weather_str = ctx.weather_str
        festival = ctx.festival
        llm_provider = getattr(ctx, "llm_provider", llm_provider)
        llm_model = getattr(ctx, "llm_model", llm_model)
        api_key = getattr(ctx, "api_key", api_key)
    logger.info("[ARTWALL] Starting content generation (lang=%s)...", language)

    is_en = language == "en"
    supports_color = colors >= 3
    supports_yellow = colors >= 4
    art_description = "translated" if supports_color else "translated"

    context_parts = []
    if weather_str:
        context_parts.append(f"Weather: {weather_str}" if is_en else f"weather：{weather_str}")
    if festival:
        context_parts.append(f"Festival: {festival}" if is_en else f"festival：{festival}")
    if date_str:
        context_parts.append(f"Date: {date_str}" if is_en else f"translated：{date_str}")

    context = ", ".join(context_parts) if is_en else "，".join(context_parts)
    if not context:
        context = "Today" if is_en else "translated"
    intent_parts = [p.strip() for p in (mode_display_name, mode_description, prompt_hint, prompt_template) if isinstance(p, str) and p.strip()]
    intent = "; ".join(intent_parts[:4]) if is_en else "；".join(intent_parts[:4])
    title_seed = (fallback_title or mode_display_name or ("Ink Muse" if is_en else "translated")).strip()

    if is_en:
        title_prompt = f"""Generate a poetic and evocative artwork title (max 5 words) based on the following:

{context}
Theme: {intent or title_seed}

Requirements:
1. Poetic and evocative, like a painting's title
2. Maximum 5 words
3. Atmospheric, leaving room for imagination
4. Output only the title, nothing else"""
    else:
        title_prompt = f"""Get by translated，translated（8translated）：

{context}
translated：{intent or title_seed}

translated：
1. translated，translated
2. 8translated
3. translated，translated
4. translated，translated"""

    artwork_title = title_seed
    try:
        title_text = await _call_llm(
            llm_provider,
            llm_model,
            title_prompt,
            api_key=api_key,
            base_url=_extract_llm_base_url(ctx) or llm_base_url,
        )
        cleaned = title_text.strip('"').strip("「」").strip("'").strip()
        artwork_title = cleaned or artwork_title
        logger.info(f"[ARTWALL] Generated title via {llm_provider}/{llm_model}: {artwork_title}")
    except _LLM_RECOVERABLE_ERRORS as e:
        logger.warning(f"[ARTWALL] Title generation failed, use fallback title: {e}")

    try:
        if supports_color:
            palette_text = "translated、translated、translated、translated" if supports_yellow else "translated、translated、translated"
            image_prompt = f"""
translated：translated，translated，translated。
translated：translated{palette_text}，translated、translated、translated、translated。
translated：blacktranslated；translated；{"translated；" if supports_yellow else ""}whitetranslated。
translated：translated、translated、translated，translated。
translated：translated，translated，translated，translated400x300translated。
translated：translated、translated、translated。
translated：{intent or artwork_title}。
translated：translated{artwork_title}translated。translated：{context}（translated，translated）。
"""
        else:
            image_prompt = f"""
translated：translated，translated，translated。
translated：translated，translated、translated、translated。
translated：translated、translated、translated，translated。
translated：translated，translated(Negative Space)，translated，translated。
translated：translatedwhite(#FFFFFF)，translated。
translated：translated、translated、translated(Zen minimalism)。
translated：{intent or artwork_title}。
translated：translatedblacktranslated{artwork_title}translated。translated：{context}（translated）。
"""

        logger.info(f"[ARTWALL] Image prompt: {image_prompt[:100]}...")

        provider = (llm_provider or "").strip().lower()
        if provider != "openai":
            logger.warning("[ARTWALL] Image generation requires OpenAI provider; using fallback")
            return {
                "artwork_title": artwork_title,
                "image_url": "",
                "description": art_description,
                "prompt": image_prompt,
            }

        image_model_resolved = (image_model or "").strip() or "gpt-image-1"
        client, _ = _get_client(provider, llm_model, api_key=api_key, base_url=llm_base_url)
        img_resp = await client.images.generate(
            model=image_model_resolved,
            prompt=image_prompt,
            size="1024x1024",
        )
        image_url = ""
        data = getattr(img_resp, "data", None) or []
        if data:
            first = data[0]
            url = getattr(first, "url", None)
            b64_json = getattr(first, "b64_json", None)
            if isinstance(url, str) and url.strip():
                image_url = url.strip()
            elif isinstance(b64_json, str) and b64_json.strip():
                image_bytes = base64.b64decode(b64_json)
                image_url = _save_generated_image_bytes(image_bytes, "image/png")

        if not image_url:
            logger.warning("[ARTWALL] OpenAI image generation returned no image")
            return {
                "artwork_title": artwork_title,
                "image_url": "",
                "description": art_description,
                "prompt": image_prompt,
            }

        return {
            "artwork_title": artwork_title,
            "image_url": image_url,
            "description": art_description,
            "prompt": image_prompt,
        }

    except (
        httpx.HTTPError,
        OpenAIError,
        OSError,
        TypeError,
        ValueError,
        AttributeError,
    ) as e:
        logger.exception("[ARTWALL] Failed to generate artwall content")
        return {
            "artwork_title": artwork_title,
            "image_url": "",
            "description": "translated",
            "prompt": "",
        }


# ── Recipe mode ──────────────────────────────────────────────


async def generate_recipe_content(
    ctx=None,
    llm_provider: str = "deepseek",
    llm_model: str = "deepseek-chat",
    api_key: str | None = None,
) -> dict:
    """generate RECIPE modetranslated - translated"""
    if ctx is not None:
        llm_provider = ctx.llm_provider
        llm_model = ctx.llm_model
        api_key = ctx.api_key
    logger.info("[RECIPE] Starting content generation...")

    month = datetime.datetime.now().month

    season_map = {
        1: "Major Cold·January",
        2: "Start of Spring·February",
        3: "Awakening of Insects·March",
        4: "Clear and Bright·April",
        5: "Start of Summer·May",
        6: "Grain in Ear·June",
        7: "Minor Heat·July",
        8: "Start of Autumn·August",
        9: "White Dew·September",
        10: "Cold Dew·October",
        11: "Start of Winter·translatedJanuary",
        12: "Major Snow·translatedFebruary",
    }

    prompt = f"""translated。Get by translated（{month}month），translated。

translated：
1. translated：translated，translated+translated+translated
2. translated：1translated+1translated+translated
3. translated：1translated+1translated+translated/translated
4. translated（translated：translated✓ translated✓ translatedC✓）

translated JSON translated：
{{
  "breakfast": "translated（translated：translated·translated·translated）",
  "lunch": {{
    "meat": "translated",
    "veg": "translated",
    "staple": "translated"
  }},
  "dinner": {{
    "meat": "translated",
    "veg": "translated",
    "staple": "translated/translated"
  }},
  "nutrition": "translated（translated：translated✓ translated✓ translatedC✓ translated✓）"
}}

translated JSON，translated。"""

    try:
        text = await _call_llm(llm_provider, llm_model, prompt, api_key=api_key, base_url=_extract_llm_base_url(ctx))
        cleaned = _clean_json_response(text)
        data = json.loads(cleaned)
        logger.info("[RECIPE] Generated meal plan")

        return {
            "season": season_map.get(month, f"{month}month"),
            "breakfast": data.get("breakfast", "translated·translated·translated"),
            "lunch": data.get(
                "lunch",
                {"meat": "translated", "veg": "translated", "staple": "translated"},
            ),
            "dinner": data.get(
                "dinner",
                {"meat": "translated", "veg": "translated", "staple": "translated"},
            ),
            "nutrition": data.get("nutrition", "translated✓ translated✓ translatedC✓ translated✓"),
        }

    except _LLM_RECOVERABLE_ERRORS + (json.JSONDecodeError, TypeError) as e:
        logger.exception("[RECIPE] Failed to generate recipe content")
        return {
            "season": season_map.get(month, f"{month}month"),
            "breakfast": "translated·translated·translated",
            "lunch": {"meat": "translated", "veg": "translated", "staple": "translated"},
            "dinner": {"meat": "translated", "veg": "translated", "staple": "translated"},
            "nutrition": "translated✓ translated✓ translatedC✓ translated✓",
        }
