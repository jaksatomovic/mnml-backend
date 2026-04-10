"""
translated for InkSight backend.

translated InkSightError，translated HTTP translated。
api/index.py translated JSON translated。
"""
from __future__ import annotations


class InkSightError(Exception):
    """Base error for all InkSight errors."""

    status_code: int = 500

    def __init__(self, message: str = "", detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(message)


class LLMError(InkSightError):
    """LLM provider errors (API timeout, rate limit, connection failure)."""

    status_code = 502


class LLMKeyMissingError(LLMError):
    """API key not configured for the requested LLM provider."""

    status_code = 503


class ContentGenerationError(InkSightError):
    """Content generation failed (LLM returned invalid data, JSON parse error)."""

    status_code = 500


class WeatherAPIError(InkSightError):
    """Weather API call failed after retries."""

    status_code = 502


class DeviceConfigError(InkSightError):
    """Device configuration error (invalid MAC, missing config)."""

    status_code = 400


class CacheError(InkSightError):
    """Cache read/write error."""

    status_code = 500
