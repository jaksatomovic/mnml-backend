"""
modetranslated
translated Python modetranslated JSON translatedmodetranslated、translated、translated
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from PIL import Image

from .layout_presets import compile_layout_dsl, validate_layout_dsl

logger = logging.getLogger(__name__)

@dataclass
class ContentContext:
    """translated Python translatedmodetranslated。"""
    config: dict
    date_ctx: dict
    weather_str: str
    date_str: str
    festival: str = ""
    daily_word: str = ""
    upcoming_holiday: str = ""
    days_until_holiday: int = 0
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    language: str = "zh"
    content_tone: str = "neutral"
    character_tones: list[str] = field(default_factory=list)
    api_key: Optional[str] = None
    image_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None


ContentFn = Callable[[ContentContext], Awaitable[dict]]
RenderFn = Callable[..., Image.Image]

MODES_DIR = os.path.join(os.path.dirname(__file__), "modes")
BUILTIN_JSON_DIR = os.path.join(MODES_DIR, "builtin")
BUILTIN_ZH_DIR = os.path.join(BUILTIN_JSON_DIR, "zh")
BUILTIN_EN_DIR = os.path.join(BUILTIN_JSON_DIR, "en")
BUILTIN_HR_DIR = os.path.join(BUILTIN_JSON_DIR, "hr")
CUSTOM_JSON_DIR = os.path.join(MODES_DIR, "custom")
CUSTOM_ZH_DIR = os.path.join(CUSTOM_JSON_DIR, "zh")
CUSTOM_EN_DIR = os.path.join(CUSTOM_JSON_DIR, "en")
CUSTOM_HR_DIR = os.path.join(CUSTOM_JSON_DIR, "hr")
SCHEMA_PATH = os.path.join(MODES_DIR, "schema", "mode_schema.json")

_SUPPORTED_MODE_LOCALES = frozenset({"zh", "en", "hr"})


@dataclass
class ModeInfo:
    mode_id: str
    display_name: str
    icon: str = "star"
    cacheable: bool = True
    description: str = ""
    source: str = "builtin"  # "builtin" | "builtin_json" | "custom"
    settings_schema: list[dict] = field(default_factory=list)


@dataclass
class BuiltinMode:
    info: ModeInfo
    content_fn: ContentFn
    render_fn: RenderFn


@dataclass
class JsonMode:
    info: ModeInfo
    definition: dict = field(default_factory=dict)
    file_path: str = ""
    mac: Optional[str] = None  # Device MAC address for device-specific custom modes
    definition_language: str = "zh"  # zh | en | hr — which locale this definition was authored for


class ModeRegistry:
    """Central registry for all display modes (builtin Python + JSON-defined)."""

    def __init__(self) -> None:
        self._builtin: dict[str, BuiltinMode] = {}
        self._json_modes: dict[str, JsonMode] = {}  # mode_id -> primary JsonMode (zh + registry for listing)
        self._en_json_modes: dict[str, JsonMode] = {}  # mode_id -> English JsonMode
        self._hr_json_modes: dict[str, JsonMode] = {}  # mode_id -> Croatian JsonMode
        self._device_modes: dict[str, set[str]] = {}  # mac -> set of mode_ids

    # ── Registration ─────────────────────────────────────────

    def register_builtin(
        self,
        mode_id: str,
        content_fn: ContentFn,
        render_fn: RenderFn,
        *,
        display_name: str = "",
        icon: str = "star",
        cacheable: bool = True,
        description: str = "",
    ) -> None:
        mode_id = mode_id.upper()
        info = ModeInfo(
            mode_id=mode_id,
            display_name=display_name or mode_id,
            icon=icon,
            cacheable=cacheable,
            description=description,
            source="builtin",
        )
        self._builtin[mode_id] = BuiltinMode(
            info=info, content_fn=content_fn, render_fn=render_fn
        )
        logger.debug(f"[Registry] Registered builtin mode: {mode_id}")

    def load_json_mode(
        self,
        path: str,
        *,
        source: str = "custom",
        definition_language: str = "zh",
    ) -> Optional[str]:
        """Load and validate a single JSON mode definition. Returns mode_id or None on error."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                definition = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[Registry] Failed to load {path}: {e}")
            return None

        mode_id = definition.get("mode_id", "").upper()
        if not mode_id:
            logger.error(f"[Registry] Missing mode_id in {path}")
            return None

        if not _validate_mode_def(definition):
            logger.error(f"[Registry] Validation failed for {path}")
            return None

        if mode_id in self._builtin:
            logger.warning(
                f"[Registry] JSON mode {mode_id} shadows builtin — skipped"
            )
            return None

        dl = definition_language if definition_language in _SUPPORTED_MODE_LOCALES else "zh"
        info = ModeInfo(
            mode_id=mode_id,
            display_name=definition.get("display_name", mode_id),
            icon=definition.get("icon", "star"),
            cacheable=definition.get("cacheable", True),
            description=definition.get("description", ""),
            source=source,
            settings_schema=definition.get("settings_schema", []) if isinstance(definition.get("settings_schema", []), list) else [],
        )
        self._json_modes[mode_id] = JsonMode(
            info=info, definition=definition, file_path=path, definition_language=dl
        )
        logger.info(f"[Registry] Loaded JSON mode: {mode_id} from {path}")
        return mode_id

    def load_directory(
        self,
        dir_path: str,
        *,
        source: str = "custom",
        definition_language: str = "zh",
    ) -> list[str]:
        """Load all .json files from a directory. Returns list of loaded mode_ids."""
        loaded = []
        if not os.path.isdir(dir_path):
            return loaded
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(dir_path, fname)
            mid = self.load_json_mode(
                path, source=source, definition_language=definition_language
            )
            if mid:
                loaded.append(mid)
        return loaded

    def load_builtin_locale_directory(self, lang: str, dir_path: str) -> list[str]:
        """Load builtin JSON overrides for a locale into _en_json_modes or _hr_json_modes."""
        loaded: list[str] = []
        if lang not in ("en", "hr"):
            return loaded
        if not os.path.isdir(dir_path):
            return loaded
        target = self._en_json_modes if lang == "en" else self._hr_json_modes
        src = "builtin_json_en" if lang == "en" else "builtin_json_hr"
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(dir_path, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    definition = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"[Registry] Failed to load {lang.upper()} builtin mode {path}: {e}")
                continue
            mode_id = definition.get("mode_id", "").upper()
            if not mode_id or not _validate_mode_def(definition):
                logger.error(f"[Registry] Invalid {lang} builtin mode file: {path}")
                continue
            info = ModeInfo(
                mode_id=mode_id,
                display_name=definition.get("display_name", mode_id),
                icon=definition.get("icon", "star"),
                cacheable=definition.get("cacheable", True),
                description=definition.get("description", ""),
                source=src,
                settings_schema=definition.get("settings_schema", []) if isinstance(definition.get("settings_schema", []), list) else [],
            )
            target[mode_id] = JsonMode(
                info=info, definition=definition, file_path=path, definition_language=lang
            )
            loaded.append(mode_id)
        if loaded:
            logger.info(f"[Registry] Loaded {len(loaded)} builtin {lang} mode overrides")
        return loaded

    def load_custom_locale_directory(self, lang: str, dir_path: str) -> list[str]:
        """Load custom modes from custom/en or custom/hr: locale map + _json_modes for listing."""
        loaded: list[str] = []
        if lang not in ("en", "hr"):
            return loaded
        if not os.path.isdir(dir_path):
            return loaded
        target = self._en_json_modes if lang == "en" else self._hr_json_modes
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(dir_path, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    definition = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"[Registry] Failed to load custom {lang} mode {path}: {e}")
                continue
            mode_id = definition.get("mode_id", "").upper()
            if not mode_id or not _validate_mode_def(definition):
                logger.error(f"[Registry] Invalid custom {lang} mode file: {path}")
                continue
            if mode_id in self._builtin:
                logger.warning(
                    f"[Registry] Custom JSON mode {mode_id} shadows builtin — skipped"
                )
                continue
            info = ModeInfo(
                mode_id=mode_id,
                display_name=definition.get("display_name", mode_id),
                icon=definition.get("icon", "star"),
                cacheable=definition.get("cacheable", True),
                description=definition.get("description", ""),
                source="custom",
                settings_schema=definition.get("settings_schema", []) if isinstance(definition.get("settings_schema", []), list) else [],
            )
            jm = JsonMode(
                info=info, definition=definition, file_path=path, definition_language=lang
            )
            target[mode_id] = jm
            if mode_id not in self._json_modes:
                self._json_modes[mode_id] = jm
            loaded.append(mode_id)
        if loaded:
            logger.info(f"[Registry] Loaded {len(loaded)} custom {lang} JSON modes from {dir_path}")
        return loaded

    def unregister_custom(self, mode_id: str, mac: Optional[str] = None) -> bool:
        """Unregister a custom mode. If mac is provided, only unregister if it matches."""
        mode_id = mode_id.upper()
        jm = self._json_modes.get(mode_id)
        if jm and jm.info.source == "custom":
            # Normalize mac to uppercase for comparison
            normalized_mac = mac.upper() if mac else None
            if normalized_mac is None or jm.mac == normalized_mac:
                # Remove from device tracking
                if jm.mac and jm.mac in self._device_modes:
                    self._device_modes[jm.mac].discard(mode_id)
                    if not self._device_modes[jm.mac]:
                        del self._device_modes[jm.mac]
                del self._json_modes[mode_id]
                self._en_json_modes.pop(mode_id, None)
                self._hr_json_modes.pop(mode_id, None)
                return True
        return False
    
    def unregister_device_modes(self, mac: str) -> int:
        """Unregister all custom modes for a specific device. Returns count of unregistered modes."""
        mac = mac.upper()
        if mac not in self._device_modes:
            return 0
        mode_ids = list(self._device_modes[mac])
        count = 0
        for mode_id in mode_ids:
            if self.unregister_custom(mode_id, mac):
                count += 1
        return count

    def load_custom_mode_from_dict(
        self,
        mode_id: str,
        definition: dict,
        *,
        source: str = "custom",
        mac: Optional[str] = None,
        definition_language: str = "zh",
    ) -> Optional[str]:
        """Load a custom mode from a dictionary (e.g., from database). Returns mode_id or None on error."""
        mode_id = mode_id.upper()
        if not mode_id:
            logger.error(f"[Registry] Missing mode_id in definition")
            return None

        if not _validate_mode_def(definition):
            logger.error(f"[Registry] Validation failed for {mode_id}")
            return None

        if mode_id in self._builtin:
            logger.warning(
                f"[Registry] Custom mode {mode_id} shadows builtin — skipped"
            )
            return None

        dl = definition_language if definition_language in _SUPPORTED_MODE_LOCALES else "zh"
        info = ModeInfo(
            mode_id=mode_id,
            display_name=definition.get("display_name", mode_id),
            icon=definition.get("icon", "star"),
            cacheable=definition.get("cacheable", True),
            description=definition.get("description", ""),
            source=source,
            settings_schema=definition.get("settings_schema", []) if isinstance(definition.get("settings_schema", []), list) else [],
        )
        # Normalize mac to uppercase if provided
        normalized_mac = mac.upper() if mac else None
        jm = JsonMode(
            info=info,
            definition=definition,
            file_path="",
            mac=normalized_mac,
            definition_language=dl,
        )
        if dl == "zh":
            self._json_modes[mode_id] = jm
        elif dl == "en":
            self._en_json_modes[mode_id] = jm
            if mode_id not in self._json_modes:
                self._json_modes[mode_id] = jm
        elif dl == "hr":
            self._hr_json_modes[mode_id] = jm
            if mode_id not in self._json_modes:
                self._json_modes[mode_id] = jm
        # Track mode for device
        if normalized_mac:
            if normalized_mac not in self._device_modes:
                self._device_modes[normalized_mac] = set()
            self._device_modes[normalized_mac].add(mode_id)
        logger.info(
            f"[Registry] Loaded custom mode from database: {mode_id} ({dl})"
            + (f" (device {normalized_mac})" if normalized_mac else "")
        )
        return mode_id

    async def load_user_custom_modes(self, user_id: int, mac: Optional[str] = None) -> list[str]:
        """Load custom modes for a user from database into registry, optionally filtered by device MAC."""
        from core.config_store import get_user_custom_modes
        # If mac is provided, unregister all modes for this device first to ensure clean state
        if mac:
            mac = mac.upper()
            unregistered_count = self.unregister_device_modes(mac)
            if unregistered_count > 0:
                logger.debug(f"[Registry] Unregistered {unregistered_count} existing modes for device {mac}")
        
        loaded_ids = []
        user_modes = await get_user_custom_modes(user_id, mac)
        for mode_data in user_modes:
            mode_id = mode_data["mode_id"]
            definition = mode_data["definition"]
            mode_mac = mode_data.get("mac")  # Get mac from database
            # Normalize mac to uppercase
            if mode_mac:
                mode_mac = mode_mac.upper()
            # Unregister first to avoid conflicts (especially important when loading device-specific modes)
            self.unregister_custom(mode_id, mode_mac)
            loaded = self.load_custom_mode_from_dict(
                mode_id,
                definition,
                source="custom",
                mac=mode_mac,
                definition_language=str(
                    mode_data.get("definition_language") or "zh"
                ).lower(),
            )
            if loaded:
                loaded_ids.append(loaded)
        if loaded_ids:
            device_info = f" on device {mac}" if mac else ""
            logger.info(f"[Registry] Loaded {len(loaded_ids)} custom modes for user {user_id}{device_info}")
        return loaded_ids

    # ── Queries ──────────────────────────────────────────────

    def is_supported(self, mode_id: str, mac: Optional[str] = None) -> bool:
        """Check if a mode is supported. If mac is provided, only check modes for that device."""
        mode_id = mode_id.upper()
        if mode_id in self._builtin:
            return True
        jm = self._json_modes.get(mode_id)
        if jm:
            # If mac is provided, only return True if the mode belongs to that device (or has no mac)
            if mac:
                mac = mac.upper()
                # Return True if mode has no mac (legacy/builtin_json) or matches the device
                return jm.mac is None or jm.mac == mac
            # If mac is not provided, check all modes (for backward compatibility)
            return True
        return False

    def get_supported_ids(self) -> set[str]:
        return set(self._builtin.keys()) | set(self._json_modes.keys())

    def get_cacheable_ids(self) -> set[str]:
        ids: set[str] = set()
        for mid, bm in self._builtin.items():
            if bm.info.cacheable:
                ids.add(mid)
        for mid, jm in self._json_modes.items():
            if jm.info.cacheable:
                ids.add(mid)
        return ids

    def get_mode_info(self, mode_id: str) -> Optional[ModeInfo]:
        mode_id = mode_id.upper()
        if mode_id in self._builtin:
            return self._builtin[mode_id].info
        jm = self._json_modes.get(mode_id)
        return jm.info if jm else None

    def get_builtin(self, mode_id: str) -> Optional[BuiltinMode]:
        return self._builtin.get(mode_id.upper())

    def get_json_mode(self, mode_id: str, mac: Optional[str] = None, *, language: str = "zh") -> Optional[JsonMode]:
        """Resolve JSON mode for device locale: en/hr overrides, then fallback zh."""
        uid = mode_id.upper()
        lang = (language or "zh").strip().lower()
        if lang not in _SUPPORTED_MODE_LOCALES:
            lang = "zh"

        def _with_mac(jm: Optional[JsonMode]) -> Optional[JsonMode]:
            if not jm:
                return None
            if mac:
                mac_u = mac.upper()
                if jm.mac is not None and jm.mac != mac_u:
                    return None
            return jm

        if lang == "en":
            jm = _with_mac(self._en_json_modes.get(uid))
            if jm:
                return jm
            return _with_mac(self._json_modes.get(uid))

        if lang == "hr":
            jm = _with_mac(self._hr_json_modes.get(uid))
            if jm:
                return jm
            jm = _with_mac(self._en_json_modes.get(uid))
            if jm:
                return jm
            return _with_mac(self._json_modes.get(uid))

        # zh (default)
        return _with_mac(self._json_modes.get(uid))

    def is_json_mode(self, mode_id: str) -> bool:
        return mode_id.upper() in self._json_modes

    def is_builtin(self, mode_id: str) -> bool:
        return mode_id.upper() in self._builtin

    def list_modes(self, mac: Optional[str] = None) -> list[ModeInfo]:
        """List all modes. If mac is provided, only return modes for that device."""
        infos: list[ModeInfo] = []
        for bm in self._builtin.values():
            infos.append(bm.info)
        for jm in self._json_modes.values():
            # If mac is provided, only include modes for that device (or modes without mac)
            if mac:
                mac = mac.upper()
                if jm.mac is not None and jm.mac != mac:
                    continue
            infos.append(jm.info)
        return sorted(infos, key=lambda m: m.mode_id)

    def get_mode_icon_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for mid, bm in self._builtin.items():
            result[mid] = bm.info.icon
        for mid, jm in self._json_modes.items():
            result[mid] = jm.info.icon
        return result


# ── Validation ───────────────────────────────────────────────


def _validate_mode_def_with_error(
    definition: dict, *, allow_raw_component_tree: bool = True
) -> tuple[bool, str | None]:
    mode_id = definition.get("mode_id", "")
    if not isinstance(mode_id, str) or not mode_id:
        return False, "mode_id is required"

    content = definition.get("content")
    if not isinstance(content, dict):
        return False, "content must be an object"
    ctype = content.get("type", "")
    if ctype not in (
        "llm",
        "llm_json",
        "static",
        "external_data",
        "image_gen",
        "computed",
        "composite",
        "http_fetch",
    ):
        return False, "content.type is invalid"
    if ctype in ("llm", "llm_json") and not content.get("prompt_template"):
        return False, "content.prompt_template is required"
    if ctype in ("llm", "llm_json") and not content.get("fallback"):
        return False, "content.fallback is required"
    if ctype == "http_fetch":
        url = content.get("url")
        if not isinstance(url, str) or len(url.strip()) < 8:
            return False, "content.url is required for http_fetch"
        allowed = content.get("allowed_hosts")
        if not isinstance(allowed, list) or len(allowed) == 0:
            return False, "content.allowed_hosts must be a non-empty list for http_fetch"
        if not all(isinstance(h, str) and h.strip() for h in allowed):
            return False, "content.allowed_hosts entries must be non-empty strings"
        rm = content.get("response_map")
        if not isinstance(rm, dict) or len(rm) == 0:
            return False, "content.response_map must be a non-empty object for http_fetch"
        if not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in rm.items()):
            return False, "content.response_map must map string keys to non-empty path strings"
        if not content.get("fallback"):
            return False, "content.fallback is required for http_fetch"
        hdrs = content.get("headers")
        if hdrs is not None and not isinstance(hdrs, dict):
            return False, "content.headers must be an object when set"

    layout = definition.get("layout")
    if not isinstance(layout, dict):
        return False, "layout must be an object"
    layout_engine = layout.get("layout_engine")
    try:
        validate_layout_dsl(layout, allow_raw_body=allow_raw_component_tree)
        layout = compile_layout_dsl(layout, allow_raw_body=allow_raw_component_tree)
    except ValueError as exc:
        return False, str(exc)
    body = layout.get("body")
    if layout_engine == "component_tree":
        if not isinstance(body, dict) or not body.get("type"):
            return False, "component_tree layout requires a compiled body"
    else:
        if not isinstance(body, list) or len(body) == 0:
            return False, "layout.body must contain at least one block"

    overrides = definition.get("layout_overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            return False, "layout_overrides must be an object"
        for key, val in overrides.items():
            if not isinstance(val, dict):
                return False, f"layout_overrides.{key} must be an object"

    variants = definition.get("variants")
    if variants is not None:
        if not isinstance(variants, dict):
            return False, "variants must be an object"
        for _k, val in variants.items():
            if not isinstance(val, dict):
                return False, "variants values must be objects"

    sst = definition.get("supported_slot_types")
    if sst is not None:
        if not isinstance(sst, list):
            return False, "supported_slot_types must be a list"
        for item in sst:
            if not isinstance(item, str) or not item.strip():
                return False, "supported_slot_types entries must be non-empty strings"

    return True, None


def _validate_mode_def(definition: dict, *, allow_raw_component_tree: bool = True) -> bool:
    """Lightweight validation without jsonschema dependency."""
    ok, _ = _validate_mode_def_with_error(
        definition, allow_raw_component_tree=allow_raw_component_tree
    )
    return ok


# ── Singleton ────────────────────────────────────────────────

_registry: Optional[ModeRegistry] = None


def get_registry() -> ModeRegistry:
    """Get or create the global mode registry singleton."""
    global _registry
    if _registry is None:
        _registry = ModeRegistry()
        _init_registry(_registry)
    return _registry


def _init_registry(registry: ModeRegistry) -> None:
    builtin_loaded = registry.load_directory(
        BUILTIN_ZH_DIR, source="builtin_json", definition_language="zh"
    )
    if builtin_loaded:
        logger.info(f"[Registry] Loaded {len(builtin_loaded)} builtin zh JSON modes")
    registry.load_builtin_locale_directory("en", BUILTIN_EN_DIR)
    registry.load_builtin_locale_directory("hr", BUILTIN_HR_DIR)
    custom_zh = registry.load_directory(CUSTOM_ZH_DIR, source="custom", definition_language="zh")
    if custom_zh:
        logger.info(f"[Registry] Loaded {len(custom_zh)} custom zh JSON modes")
    registry.load_custom_locale_directory("en", CUSTOM_EN_DIR)
    registry.load_custom_locale_directory("hr", CUSTOM_HR_DIR)


def reset_registry() -> None:
    """Reset the singleton (useful for tests)."""
    global _registry
    _registry = None
