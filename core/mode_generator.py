"""
AI modetranslated
Get by translated（translatedimage）generate InkSight mode JSON translated
"""
from __future__ import annotations

import json
import logging
import re

from .content import _get_client, _clean_json_response
from .mode_registry import _validate_mode_def

logger = logging.getLogger(__name__)

# Vision-capable models per provider
VISION_MODELS = {}

AVAILABLE_ICONS = (
    "art, body, book, breakfast, cloud, cookie, dinner, electric_bolt, "
    "exercise, flag, foggy, food, global, lunch, meat, partly_cloudy, "
    "rainy, rice, snow, star, sunny, thunderstorm, tips, vegetable, vital, yes, zen"
)

IMAGE_INTENT_PATTERNS = (
    r"translated", r"translated", r"generate.*translated", r"generate.*translated", r"translated", r"translated",
    r"image", r"translated", r"translated", r"translated", r"translated", r"translated", r"translated", r"translated",
    r"translated", r"translated", r"translated", r"translated", r"translated", r"translated", r"translated", r"translated",
    r"translated", r"translated", r"translated", r"translated", r"translated", r"translated",
    r"text2image", r"image generation", r"generate.*image", r"create.*image",
    r"image", r"illustration", r"poster", r"wallpaper", r"artwork", r"render",
    r"photo", r"painting", r"drawing", r"sketch",
)

# Compact examples embedded directly
_ZEN_EXAMPLE = """{
  "mode_id": "ZEN", "display_name": "translated", "icon": "zen", "cacheable": true,
  "description": "translated",
  "content": {
    "type": "llm_json",
    "prompt_template": "translated。translated，translated。\\ntranslated JSON translated：{{\\"word\\": \\"translated\\", \\"source\\": \\"translated（10translated）\\"}}\\ntranslated。\\ntranslated：{context}",
    "output_schema": { "word": { "type": "string", "default": "translated" }, "source": { "type": "string", "default": "translated" } },
    "temperature": 0.8,
    "fallback": { "word": "translated", "source": "translated" }
  },
  "layout": {
    "status_bar": { "line_width": 1, "dashed": true },
    "body": [
      { "type": "centered_text", "field": "word", "font": "noto_serif_regular", "font_size": 96, "max_width_ratio": 0.7, "vertical_center": true },
      { "type": "spacer", "height": 10 },
      { "type": "text", "field": "source", "font": "noto_serif_light", "font_size": 9, "align": "center", "max_lines": 1 }
    ],
    "footer": { "label": "ZEN", "attribution_template": "— ..." }
  }
}"""

_STOIC_EXAMPLE = """{
  "mode_id": "STOIC", "display_name": "translated", "icon": "book", "cacheable": true,
  "description": "translated、translated，translated",
  "content": {
    "type": "llm_json",
    "prompt_template": "translated。Get by translated，translated+translated。\\ntranslated JSON translated：{{\\"quote\\": \\"translated（40translated）\\", \\"author\\": \\"translated\\", \\"interpretation\\": \\"translated（20translated）\\"}}\\ntranslated JSON。\\ntranslated：{context}",
    "output_schema": {
      "quote": { "type": "string", "default": "The impediment to action advances action." },
      "author": { "type": "string", "default": "Marcus Aurelius" },
      "interpretation": { "type": "string", "default": "translated，translated。" }
    },
    "temperature": 0.8,
    "fallback": { "quote": "The impediment to action advances action.", "author": "Marcus Aurelius", "interpretation": "translated，translated。" }
  },
  "layout": {
    "status_bar": { "line_width": 1 },
    "body": [
      { "type": "centered_text", "field": "quote", "font": "noto_serif_regular", "font_size": 20, "max_width_ratio": 0.88, "vertical_center": true }
    ],
    "footer": { "label": "STOIC", "attribution_template": "— {author}" }
  }
}"""


def _build_generation_prompt(description: str) -> str:
    """Build the meta-prompt that teaches the LLM to produce valid mode JSON."""
    return f"""translated InkSight modetranslated。InkSight translated，screen 400x300 translated，1translated。

translatedGet by translated，translated InkSight mode JSON translated。

## mode JSON translated

### translated（translated icon/cacheable/description）
- mode_id: translated+translated+translated，2-32translated，translated，translated "MY_VOCAB"
- display_name: translated，translated32translated
- icon: translated，translated: {AVAILABLE_ICONS}
- cacheable: translated，translated（default true）
- description: translated，translated200translated

### content config（translated "llm_json" translated）
- type: "llm_json"
- prompt_template: LLM translated，**must**translated {{context}} translated。translated JSON translatedmusttranslated {{{{ }}}} translated
- output_schema: translated，translated type（"string"/"number"/"array"/"boolean"）translated default
- temperature: 0.0-2.0，translated 0.7-0.9
- fallback: translated，translatedmusttranslated output_schema translated

### layout config
- status_bar: {{"line_width": 1}} translated {{"line_width": 1, "dashed": true}}
- body: translated（translated），**translated**
- footer: {{"label": "MODE_ID", "attribution_template": "— {{field_name}}"}}

### translated
- centered_text: translated。translated: field, font, font_size, vertical_center(bool), max_width_ratio(0.3-1.0)
- text: translated。translated: field translated template, font, font_size, align(left/center/right), margin_x, max_lines
- separator: translated。translated: style(solid/dashed/short), margin_x
- spacer: translated。translated: height
- list: list。translated: field(translated), max_items, item_template, numbered(bool), item_spacing, margin_x
- section: translated。translated: title, icon, children(translated)
- icon_text: translated+translated。translated: icon, text/field, font_size
- two_column: translated。translated: left(translated), right(translated), left_width, gap
- big_number: translated。translated: field, font_size, align
- key_value: translated。translated: field, label, font_size
- group: translated。translated: title, children(translated)

### translated
noto_serif_light, noto_serif_regular, noto_serif_bold, lora_regular, lora_bold

## translated1：translatedmode（translated）
{_ZEN_EXAMPLE}

## translated2：translatedmode（translated+translated）
{_STOIC_EXAMPLE}

## translated
1. translated 400x300 translated，translated，translated
2. 1translated，translated，translated
3. font_size translated: translated 14-18, translated 12-14, translated 9-11, translated 36-96
4. fallback translatedmusttranslated，translated output_schema translated
5. prompt_template translated JSON translatedmusttranslated {{{{}}}} translated，translated {{context}} translated
6. body translated，translated 2-6 translated

## translated
{description}

translated JSON modetranslated，translated。"""


def _supports_vision(provider: str, model: str) -> bool:
    """Check if the given provider/model supports image input."""
    models = VISION_MODELS.get(provider, set())
    return model in models


def _build_messages(prompt: str, image_base64: str | None = None,
                    provider: str = "", model: str = "") -> list[dict]:
    """Build OpenAI-compatible messages, optionally with image."""
    if image_base64 and _supports_vision(provider, model):
        # Strip data URL prefix if present
        if "," in image_base64 and image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1]
        return [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }},
            ],
        }]
    return [{"role": "user", "content": prompt}]


async def _call_llm_with_messages(
    provider: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Call LLM with pre-built messages (supports multimodal)."""
    client, _ = _get_client(provider, model, api_key=api_key, base_url=base_url)
    request_kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    response = await client.chat.completions.create(
        **request_kwargs,
    )
    text = response.choices[0].message.content.strip()

    finish_reason = response.choices[0].finish_reason
    usage = response.usage
    logger.info(
        f"[MODE_GEN] {provider}/{model} tokens={usage.total_tokens}, "
        f"finish={finish_reason}"
    )
    if finish_reason == "length":
        logger.warning("[MODE_GEN] Response truncated due to max_tokens limit")

    return text


def _auto_fix(definition: dict) -> dict:
    """Auto-fix common issues in LLM-generated mode definitions."""
    # Force mode_id uppercase
    mode_id = definition.get("mode_id", "")
    if isinstance(mode_id, str):
        mode_id = re.sub(r"[^A-Z0-9_]", "_", mode_id.upper())
        if not mode_id or not mode_id[0].isalpha():
            mode_id = "MY_" + mode_id
        definition["mode_id"] = mode_id[:32]

    # Ensure display_name exists
    if not definition.get("display_name"):
        definition["display_name"] = mode_id.replace("_", " ").title()

    # Ensure content section
    content = definition.get("content", {})

    # Ensure prompt_template contains {context}
    pt = content.get("prompt_template", "")
    if isinstance(pt, str) and "{context}" not in pt:
        content["prompt_template"] = pt + "\ntranslated：{context}"

    # Ensure fallback has all output_schema fields
    schema = content.get("output_schema", {})
    fallback = content.get("fallback", {})
    if schema and isinstance(schema, dict) and isinstance(fallback, dict):
        for key, field_def in schema.items():
            if key not in fallback:
                default = ""
                if isinstance(field_def, dict):
                    default = field_def.get("default", "")
                fallback[key] = default
        content["fallback"] = fallback

    # Ensure layout.body exists and is non-empty
    layout = definition.get("layout", {})
    body = layout.get("body", [])
    if not body:
        layout["body"] = [{"type": "centered_text", "field": "text",
                           "font_size": 16, "vertical_center": True}]
    definition["layout"] = layout

    # Ensure footer label matches mode_id
    footer = layout.get("footer", {})
    if not footer.get("label"):
        footer["label"] = definition.get("mode_id", "CUSTOM")
        layout["footer"] = footer

    return definition


def _is_image_generation_request(description: str) -> bool:
    text = (description or "").lower()
    for pattern in IMAGE_INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _force_image_gen_mode(definition: dict) -> dict:
    mode_id = (definition.get("mode_id") or "MY_IMAGE").upper()
    display_name = definition.get("display_name") or "translated"
    icon = definition.get("icon") or "art"

    fixed = dict(definition)
    fixed["mode_id"] = mode_id
    fixed["display_name"] = display_name
    fixed["icon"] = icon
    fixed["cacheable"] = False
    fixed["description"] = fixed.get("description") or "AI translatedmode"
    fixed["content"] = {
        "type": "image_gen",
        "provider": "text2image",
        "fallback": {
            "artwork_title": display_name,
            "image_url": "",
            "description": "translatedgenerating",
        },
    }
    fixed["layout"] = {
        "status_bar": {"line_width": 1},
        "body": [
            {"type": "text", "field": "artwork_title", "font_size": 14, "align": "center", "max_lines": 1},
            {"type": "image", "field": "image_url", "width": 220, "height": 150},
            {"type": "text", "field": "description", "font_size": 11, "align": "center", "max_lines": 2},
        ],
        "footer": {"label": mode_id, "attribution_template": "— AI Image"},
    }
    return fixed


async def generate_mode_definition(
    description: str,
    image_base64: str | None = None,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Generate a mode JSON definition from natural language description.

    Returns dict with keys: ok, mode_def (on success), error (on failure),
    warning (optional).
    """
    warning = None
    prefer_image_gen = _is_image_generation_request(description)

    # Check vision support
    if image_base64 and not _supports_vision(provider, model):
        warning = "translatedimagetranslated，translatedimage"
        image_base64 = None

    prompt = _build_generation_prompt(description)
    messages = _build_messages(prompt, image_base64, provider, model)

    # Call LLM
    raw_text = await _call_llm_with_messages(
        provider, model, messages,
        temperature=0.3,
        max_tokens=2048,
        api_key=api_key,
        base_url=base_url,
    )

    # Clean and parse
    cleaned = _clean_json_response(raw_text)
    try:
        definition = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[MODE_GEN] Invalid JSON from LLM: {e}")
        return {
            "ok": False,
            "error": f"AI translated JSON: {e}",
            "raw_response": raw_text[:500],
        }

    if not isinstance(definition, dict):
        return {"ok": False, "error": "AI translated JSON translated"}

    # Auto-fix common issues
    definition = _auto_fix(definition)

    if prefer_image_gen:
        definition = _force_image_gen_mode(definition)

    # Validate
    if not _validate_mode_def(definition):
        return {
            "ok": False,
            "error": "translatedmodetranslatedfailed，translated",
            "mode_def": definition,
        }

    result = {"ok": True, "mode_def": definition}
    if warning:
        result["warning"] = warning
    return result
