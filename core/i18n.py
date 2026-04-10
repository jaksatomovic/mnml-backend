from __future__ import annotations

from fastapi import Request

DEFAULT_LANG = "en"

MESSAGES = {
    "auth.login_required": {
        "zh": "请先登录",
        "en": "Please sign in first",
        "hr": "Prvo se prijavi",
    },
    "auth.no_device_access": {
        "zh": "无设备访问权限",
        "en": "No access permission for this device",
        "hr": "Nemaš pristup ovom uređaju",
    },
    "auth.owner_only": {
        "zh": "仅 owner 可执行此操作",
        "en": "Only owner can perform this action",
        "hr": "Samo vlasnik može izvršiti ovu radnju",
    },
    "auth.admin_required": {
        "zh": "需要管理员认证",
        "en": "Admin authorization required",
        "hr": "Potrebna je administratorska autorizacija",
    },
    "auth.root_required": {
        "zh": "需要 Root 管理员权限",
        "en": "Root administrator privileges required",
        "hr": "Potrebne su root administratorske ovlasti",
    },
    "auth.user_not_found": {
        "zh": "用户不存在",
        "en": "User not found",
        "hr": "Korisnik nije pronađen",
    },
    "auth.device_token_invalid": {
        "zh": "设备 Token 无效或缺失",
        "en": "Device token is invalid or missing",
        "hr": "Token uređaja je neispravan ili nedostaje",
    },
    "auth.device_token_required": {
        "zh": "设备 Token 缺失，请先完成设备注册",
        "en": "Device token missing, please complete device registration first",
        "hr": "Nedostaje token uređaja, prvo dovrši registraciju uređaja",
    },
    "auth.invalid_mac_format": {
        "zh": "MAC 地址格式无效，应为 AA:BB:CC:DD:EE:FF",
        "en": "Invalid MAC format, expected AA:BB:CC:DD:EE:FF",
        "hr": "Neispravan MAC format, očekuje se AA:BB:CC:DD:EE:FF",
    },
}


def normalize_lang(value: object) -> str:
    # FastAPI dependency functions may pass Header(...) defaults when called directly
    # in tests; treat any non-string value as missing language.
    if not isinstance(value, str) or not value:
        return DEFAULT_LANG
    v = value.lower()
    if v.startswith("hr"):
        return "hr"
    if v.startswith("zh"):
        return "zh"
    return "en"


def detect_lang_from_request(request: Request) -> str:
    query_lang = request.query_params.get("lang")
    if query_lang:
        return normalize_lang(query_lang)
    header_lang = request.headers.get("accept-language")
    if header_lang:
        return normalize_lang(header_lang.split(",")[0].strip())
    return DEFAULT_LANG


def msg(key: str, lang: str) -> str:
    item = MESSAGES.get(key)
    if not item:
        return key
    return item.get(lang) or item.get(DEFAULT_LANG) or key
