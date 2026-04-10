from __future__ import annotations

from fastapi import Request

DEFAULT_LANG = "en"

MESSAGES = {
    "auth.login_required": {
        "zh": "translated",
        "en": "Please sign in first",
        "hr": "Prvo se prijavi",
    },
    "auth.no_device_access": {
        "zh": "translated",
        "en": "No access permission for this device",
        "hr": "Nemaš pristup ovom uređaju",
    },
    "auth.owner_only": {
        "zh": "translated owner translated",
        "en": "Only owner can perform this action",
        "hr": "Samo vlasnik može izvršiti ovu radnju",
    },
    "auth.admin_required": {
        "zh": "translated",
        "en": "Admin authorization required",
        "hr": "Potrebna je administratorska autorizacija",
    },
    "auth.root_required": {
        "zh": "translated Root translated",
        "en": "Root administrator privileges required",
        "hr": "Potrebne su root administratorske ovlasti",
    },
    "auth.user_not_found": {
        "zh": "userdoes not exist",
        "en": "User not found",
        "hr": "Korisnik nije pronađen",
    },
    "auth.device_token_invalid": {
        "zh": "device Token invalidtranslated",
        "en": "Device token is invalid or missing",
        "hr": "Token uređaja je neispravan ili nedostaje",
    },
    "auth.device_token_required": {
        "zh": "device Token translated，translated",
        "en": "Device token missing, please complete device registration first",
        "hr": "Nedostaje token uređaja, prvo dovrši registraciju uređaja",
    },
    "auth.invalid_mac_format": {
        "zh": "MAC translatedinvalid，translated AA:BB:CC:DD:EE:FF",
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
