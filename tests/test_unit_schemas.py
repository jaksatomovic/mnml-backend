"""
Unit tests for Pydantic input validation schemas.
"""
import pytest
from pydantic import ValidationError
from core.schemas import ConfigRequest


class TestConfigRequest:
    """Tests for the ConfigRequest Pydantic model."""

    def test_valid_config(self):
        body = ConfigRequest(
            mac="AA:BB:CC:DD:EE:FF",
            nickname="MyDevice",
            modes=["STOIC", "ZEN"],
            refreshStrategy="cycle",
            refreshInterval=30,
            always_active=True,
            language="zh",
            contentTone="neutral",
            city="Beijing",
            latitude=39.9042,
            longitude=116.4074,
            timezone="Asia/Shanghai",
            llmProvider="deepseek",
            llmModel="deepseek-chat",
        )
        assert body.mac == "AA:BB:CC:DD:EE:FF"
        assert body.modes == ["STOIC", "ZEN"]
        assert body.refreshInterval == 30
        assert body.always_active is True
        assert body.latitude == pytest.approx(39.9042)

    def test_invalid_mac_format(self):
        with pytest.raises(ValidationError, match="MAC"):
            ConfigRequest(mac="invalid-mac")

    def test_invalid_mac_too_short(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB")

    def test_unsupported_mode(self):
        with pytest.raises(ValidationError, match="textmode"):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", modes=["INVALID_MODE"])

    def test_modes_uppercased(self):
        body = ConfigRequest(mac="AA:BB:CC:DD:EE:FF", modes=["stoic", "zen"])
        assert body.modes == ["STOIC", "ZEN"]

    def test_empty_modes_rejected(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", modes=[])

    def test_refresh_interval_min(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", refreshInterval=5)

    def test_refresh_interval_max(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", refreshInterval=2000)

    def test_invalid_language(self):
        with pytest.raises(ValidationError, match="invalidtext"):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", language="fr")

    def test_invalid_tone(self):
        with pytest.raises(ValidationError, match="invalidtext"):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", contentTone="angry")

    def test_invalid_provider(self):
        with pytest.raises(ValidationError, match="invalid LLM text"):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", llmProvider="openai")

    def test_invalid_strategy(self):
        with pytest.raises(ValidationError, match="invalidtext"):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", refreshStrategy="sequential")

    def test_nickname_max_length(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", nickname="a" * 50)

    def test_defaults(self):
        body = ConfigRequest(mac="AA:BB:CC:DD:EE:FF")
        assert body.nickname == ""
        assert body.modes == ["STOIC"]
        assert body.refreshStrategy == "random"
        assert body.refreshInterval == 60
        assert body.always_active is False
        assert body.language == "zh"
        assert body.contentTone == "neutral"
        assert body.city == "Hangzhou"
        assert body.latitude is None
        assert body.llmProvider == "deepseek"

    def test_model_dump(self):
        body = ConfigRequest(mac="AA:BB:CC:DD:EE:FF", modes=["DAILY"])
        d = body.model_dump()
        assert isinstance(d, dict)
        assert d["mac"] == "AA:BB:CC:DD:EE:FF"
        assert d["modes"] == ["DAILY"]

    def test_character_tones_cleaned(self):
        body = ConfigRequest(
            mac="AA:BB:CC:DD:EE:FF",
            characterTones=["  Lu Xun ", "", "  Mo Yan  "],
        )
        assert body.characterTones == ["Lu Xun", "Mo Yan"]

    def test_mode_overrides_accept_location_fields(self):
        body = ConfigRequest(
            mac="AA:BB:CC:DD:EE:FF",
            modeOverrides={
                "WEATHER": {
                    "city": "Pingyang",
                    "latitude": 27.66,
                    "longitude": 120.56,
                    "timezone": "Asia/Shanghai",
                    "admin1": "Zhejiang",
                    "country": "China",
                }
            },
        )
        assert body.modeOverrides["WEATHER"]["city"] == "Pingyang"
        assert body.modeOverrides["WEATHER"]["latitude"] == pytest.approx(27.66)

    def test_device_mode_surface_accepted(self):
        body = ConfigRequest(
            mac="AA:BB:CC:DD:EE:FF",
            deviceMode="surface",
            assignedSurface="work",
            surfaces=[{"id": "work", "layout": [{"type": "text", "content": "x"}]}],
        )
        assert body.deviceMode == "surface"
        assert body.surfaces[0]["id"] == "work"

    def test_device_mode_rejects_invalid(self):
        with pytest.raises(ValidationError):
            ConfigRequest(mac="AA:BB:CC:DD:EE:FF", deviceMode="advanced")
