"""
Pydantic Pydantic input validation models
Provide request type and range validation for API endpoints
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import get_supported_modes

# MAC translated：AA:BB:CC:DD:EE:FF
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# allowed  LLM translated
_VALID_PROVIDERS = {"deepseek", "openai"}
_VALID_IMAGE_PROVIDERS = {"deepseek"}

# allowed translated
_VALID_LANGUAGES = {"zh", "en", "hr", "mixed"}

# allowed translatedtone
_VALID_TONES = {"positive", "neutral", "deep", "humor"}

# allowed refresh strategy
_VALID_STRATEGIES = {"random", "cycle", "time_slot", "smart"}
_VALID_DEVICE_RENDER_MODES = {"mode", "surface"}

# translatedtonetranslated：translated、translated、translated
_SAFE_TONE_RE = re.compile(
    r"^[\u4e00-\u9fff\u3400-\u4dbf"   # CJK Unified Ideographs
    r"a-zA-Z0-9"
    r"\s·\-\.\u3001\u3002"             # space, middot, dash, period, CN punctuation
    r"]{1,20}$"
)


class ConfigRequest(BaseModel):
    """translated"""

    mac: str = Field(..., description="device MAC translated (AA:BB:CC:DD:EE:FF)")
    nickname: str = Field(default="", max_length=32, description="translated")
    modes: list[str] = Field(
        default=["STOIC"],
        min_length=1,
        max_length=10,
        description="translatedmodelist",
    )
    refreshStrategy: str = Field(
        default="random", description="refresh strategy: random / cycle"
    )
    refreshInterval: int = Field(
        default=60, ge=10, le=1440, description="translated(translated), 10~1440"
    )
    language: str = Field(default="en", description="(deprecated) translated，translated modeLanguage translated")
    modeLanguage: str = Field(default="en", description="modetranslated: zh / en / hr")
    contentTone: str = Field(default="neutral", description="tone: positive / neutral / deep / humor")
    city: str = Field(default="Zagreb", max_length=40, description="City name")
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, description="locationlatitude")
    longitude: Optional[float] = Field(default=None, ge=-180, le=180, description="locationlongitude")
    timezone: str = Field(default="", max_length=64, description="locationtimezone")
    admin1: str = Field(default="", max_length=64, description="locationtranslatedadministrative region")
    country: str = Field(default="", max_length=64, description="locationtranslatedcountry")
    characterTones: list[str] = Field(
        default_factory=list, max_length=5, description="translatedtonelist"
    )
    llmProvider: str = Field(default="deepseek", description="LLM translated")
    llmModel: str = Field(default="deepseek-chat", max_length=50, description="LLM translated")
    imageProvider: str = Field(default="deepseek", description="translated")
    imageModel: str = Field(default="", max_length=50, description="translated")
    countdownEvents: list[dict] = Field(
        default_factory=list,
        max_length=10,
        description="translated [{name, date, type}]",
    )
    timeSlotRules: list[dict] = Field(
        default_factory=list,
        max_length=24,
        description="translated [{startHour, endHour, modes}]",
    )
    memoText: str = Field(default="", description="MEMO modetranslated")
    llmApiKey: str = Field(default="", max_length=200, description="LLM API Key (encrypted at rest)")
    imageApiKey: str = Field(default="", max_length=200, description="Image API Key (encrypted at rest)")
    screenSize: str = Field(default="400x300", description="translated: 400x300 / 296x128 / 800x480")
    modeOverrides: dict[str, dict] = Field(
        default_factory=dict,
        description="translatedmodetranslated，key translated mode_id，value translated city/llm_provider/llm_model translatedmodetranslated",
    )
    is_focus_listening: bool = Field(
        default=False,
        description="translated（Focus Mode）",
    )
    always_active: bool = Field(
        default=False,
        description="translated",
    )
    deviceMode: str = Field(default="mode", description="Device render mode: mode | surface")
    assignedMode: str = Field(default="", description="Assigned legacy mode id")
    assignedSurface: str = Field(default="", description="Assigned surface id")
    surfaces: list[dict] = Field(default_factory=list, max_length=50, description="Surface definitions")
    surfaceSchedule: list[dict] = Field(default_factory=list, max_length=48, description="Surface schedule rules")
    renderMode: Optional[str] = Field(default=None, description="Alias for deviceMode (spec: render_mode)")
    render_mode: Optional[str] = Field(default=None, description="Alias for deviceMode")
    assigned: Optional[str] = Field(default=None, description="Alias: assignedSurface (surface) or assignedMode (mode)")

    @model_validator(mode="before")
    @classmethod
    def normalize_spec_aliases(cls, data: Any) -> Any:
        """Accept render_mode / renderMode and assigned (spec) alongside deviceMode / assignedSurface."""
        if not isinstance(data, dict):
            return data
        rm = data.get("renderMode") or data.get("render_mode")
        if rm is not None and str(rm).strip():
            data["deviceMode"] = str(rm).strip().lower()
        asg = data.get("assigned")
        if asg is not None and str(asg).strip():
            dm = str(data.get("deviceMode") or data.get("device_mode") or "mode").strip().lower()
            if dm == "surface" and not str(data.get("assignedSurface") or data.get("assigned_surface") or "").strip():
                data["assignedSurface"] = str(asg).strip()
            elif dm != "surface" and not str(data.get("assignedMode") or data.get("assigned_mode") or "").strip():
                data["assignedMode"] = str(asg).strip().upper()
        return data

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        if not _MAC_RE.match(v):
            raise ValueError("MAC translatedinvalid，translated AA:BB:CC:DD:EE:FF")
        return v

    @field_validator("modes")
    @classmethod
    def validate_modes(cls, v: list[str]) -> list[str]:
        supported = get_supported_modes()
        cleaned = []
        for mode in v:
            m = mode.upper().strip()
            # translated CUSTOM_* / MY_* translated，translated 422/500
            if not (m.startswith("CUSTOM_") or m.startswith("MY_") or m in supported):
                raise ValueError(f"unsupported mode: {mode}，translated: {supported}")
            cleaned.append(m)
        return cleaned

    @field_validator("refreshStrategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in _VALID_STRATEGIES:
            raise ValueError(f"invalidrefresh strategy: {v}，translated: {_VALID_STRATEGIES}")
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in _VALID_LANGUAGES:
            raise ValueError(f"invalidtranslated: {v}，translated: {_VALID_LANGUAGES}")
        return v

    @field_validator("contentTone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        if v not in _VALID_TONES:
            raise ValueError(f"invalidtone: {v}，translated: {_VALID_TONES}")
        return v

    @field_validator("llmProvider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"invalid LLM translated: {v}，translated: {_VALID_PROVIDERS}")
        return v

    @field_validator("imageProvider")
    @classmethod
    def validate_image_provider(cls, v: str) -> str:
        if v not in _VALID_IMAGE_PROVIDERS:
            raise ValueError(f"invalidtranslated: {v}，translated: {_VALID_IMAGE_PROVIDERS}")
        return v

    @field_validator("characterTones")
    @classmethod
    def validate_character_tones(cls, v: list[str]) -> list[str]:
        cleaned = []
        for t in v:
            t = t.strip()[:20]
            if not t:
                continue
            if not _SAFE_TONE_RE.match(t):
                raise ValueError(
                    f"translatedtonetranslated: {t!r}，translated、translated"
                )
            cleaned.append(t)
        return cleaned

    @field_validator("modeOverrides")
    @classmethod
    def validate_mode_overrides(cls, v: dict[str, dict]) -> dict[str, dict]:
        cleaned: dict[str, dict] = {}
        for mode_id, raw in v.items():
            if not isinstance(mode_id, str):
                continue
            key = mode_id.strip().upper()
            if not key:
                continue
            if not isinstance(raw, dict):
                continue

            item: dict[str, object] = {}
            city = raw.get("city")
            if isinstance(city, str) and city.strip():
                item["city"] = city.strip()[:40]

            latitude = raw.get("latitude")
            if latitude not in ("", None):
                try:
                    item["latitude"] = float(latitude)
                except (TypeError, ValueError):
                    raise ValueError(f"invalidlocationlatitude: {latitude}")

            longitude = raw.get("longitude")
            if longitude not in ("", None):
                try:
                    item["longitude"] = float(longitude)
                except (TypeError, ValueError):
                    raise ValueError(f"invalidlocationlongitude: {longitude}")

            timezone = raw.get("timezone")
            if isinstance(timezone, str) and timezone.strip():
                item["timezone"] = timezone.strip()[:64]

            admin1 = raw.get("admin1")
            if isinstance(admin1, str) and admin1.strip():
                item["admin1"] = admin1.strip()[:64]

            country = raw.get("country")
            if isinstance(country, str) and country.strip():
                item["country"] = country.strip()[:64]

            provider = raw.get("llm_provider", raw.get("llmProvider"))
            if isinstance(provider, str) and provider.strip():
                if provider not in _VALID_PROVIDERS:
                    raise ValueError(f"invalid LLM translated: {provider}，translated: {_VALID_PROVIDERS}")
                item["llm_provider"] = provider

            model = raw.get("llm_model", raw.get("llmModel"))
            if isinstance(model, str) and model.strip():
                item["llm_model"] = model.strip()[:50]

            for k, val in raw.items():
                if k in {
                    "city",
                    "latitude",
                    "longitude",
                    "timezone",
                    "admin1",
                    "country",
                    "llm_provider",
                    "llmProvider",
                    "llm_model",
                    "llmModel",
                }:
                    continue
                if isinstance(val, (str, int, float, bool, list, dict)) or val is None:
                    item[k] = val

            if item:
                cleaned[key] = item
        return cleaned

    @field_validator("deviceMode")
    @classmethod
    def validate_device_mode(cls, v: str) -> str:
        mode = str(v or "").strip().lower()
        if mode not in _VALID_DEVICE_RENDER_MODES:
            raise ValueError("deviceMode must be 'mode' or 'surface'")
        return mode

    @field_validator("surfaces")
    @classmethod
    def validate_surfaces(cls, v: list[dict]) -> list[dict]:
        cleaned: list[dict] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            surface_id = str(item.get("id") or "").strip()
            if not surface_id:
                continue
            normalized = dict(item)
            normalized["id"] = surface_id
            normalized["type"] = "surface"
            cleaned.append(normalized)
        return cleaned


class RenderQuery(BaseModel):
    """translated Query translated。"""

    model_config = ConfigDict(populate_by_name=True)

    v: float = Field(default=3.3, description="Battery voltage")
    mac: Optional[str] = Field(default=None, description="Device MAC address")
    persona: Optional[str] = Field(default=None, description="Force persona")
    rssi: Optional[int] = Field(default=None, description="WiFi RSSI (dBm)")
    refresh_min: Optional[int] = Field(default=None, ge=1, le=1440, description="Device effective refresh interval in minutes")
    w: int = Field(default=400, ge=100, le=1600, description="Screen width in pixels")
    h: int = Field(default=300, ge=100, le=1200, description="Screen height in pixels")
    next_mode: Optional[int] = Field(default=None, alias="next", description="1 = advance to next mode")
    colors: int = Field(default=2, ge=2, le=4, description="Device color capability (2=BW, 3=BWR, 4=BWRY)")

    @field_validator("mac")
    @classmethod
    def validate_optional_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return ConfigRequest.validate_mac(v)


class DeviceHeartbeatRequest(BaseModel):
    """translated。"""

    battery_voltage: Optional[float] = Field(default=3.3, ge=0.0, le=10.0)
    wifi_rssi: Optional[int] = Field(default=None, ge=-150, le=0)


class OkResponse(BaseModel):
    ok: bool = True


class ConfigSaveResponse(OkResponse):
    config_id: int


class UserPreferencesRequest(BaseModel):
    push_enabled: bool = Field(default=False)
    push_time: str = Field(default="08:00", min_length=4, max_length=5)
    push_modes: list[str] = Field(default_factory=list, max_length=10)
    widget_mode: str = Field(default="STOIC", max_length=40)
    locale: str = Field(default="en", max_length=8)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)

    @field_validator("push_time")
    @classmethod
    def validate_push_time(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("push_time musttranslated HH:MM translated")
        return v

    @field_validator("push_modes")
    @classmethod
    def validate_push_modes(cls, v: list[str]) -> list[str]:
        supported = get_supported_modes()
        cleaned: list[str] = []
        for mode in v:
            mid = str(mode).strip().upper()
            if not mid:
                continue
            if mid not in supported:
                raise ValueError(f"unsupported mode: {mode}")
            cleaned.append(mid)
        return cleaned

    @field_validator("widget_mode")
    @classmethod
    def validate_widget_mode(cls, v: str) -> str:
        mode = str(v).strip().upper()
        if mode not in get_supported_modes():
            raise ValueError(f"unsupported  widget_mode: {mode}")
        return mode


class PushRegistrationRequest(BaseModel):
    push_token: str = Field(..., min_length=8, max_length=512)
    platform: str = Field(..., min_length=2, max_length=16)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    push_time: str = Field(default="08:00", min_length=4, max_length=5)

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        platform = str(v).strip().lower()
        if platform not in {"ios", "android", "expo"}:
            raise ValueError("platform musttranslated ios / android / expo")
        return platform

    @field_validator("push_time")
    @classmethod
    def validate_push_registration_time(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("push_time musttranslated HH:MM translated")
        return v
