"""
testtextmodetext API key text

testtext：
1. text api_key - text
2. text - text
3. text api_key - text
4. text - text
5. test pipeline.py text api_key text
6. test json_content.py text api_key text
7. test mode_generator.py text api_key text
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.errors import LLMKeyMissingError
from core.pipeline import _generate_content_for_persona
from core.json_content import generate_json_mode_content
from core.mode_generator import generate_mode_definition, _call_llm_with_messages
from core.content import _get_client


@pytest.fixture
def sample_date_ctx():
    """A typical date context dict."""
    return {
        "date_str": "2/16 Mon",
        "time_str": "09:30:00",
        "weekday": 0,
        "hour": 9,
        "is_weekend": False,
        "year": 2026,
        "day": 16,
        "month_cn": "February",
        "weekday_cn": "Mon",
        "day_of_year": 47,
        "days_in_year": 365,
        "festival": "",
        "is_holiday": False,
        "is_workday": True,
        "upcoming_holiday": "Qingming Festival",
        "days_until_holiday": 48,
        "holiday_date": "04/05",
        "daily_word": "spring breeze",
    }


@pytest.fixture
def sample_weather():
    """A typical weather dict."""
    return {
        "temp": 12,
        "weather_code": 1,
        "weather_str": "12°C",
    }


@pytest.fixture
def custom_mode_def():
    """A custom mode definition for testing."""
    return {
        "mode_id": "TEST_CUSTOM",
        "display_name": "testtextmode",
        "content": {
            "type": "llm_json",
            "prompt_template": "testtext {context}",
            "output_schema": {
                "quote": {"type": "string", "default": "defaulttext"},
                "author": {"type": "string", "default": "defaulttext"},
            },
            "fallback": {"quote": "defaulttext", "author": "defaulttext"},
        },
        "layout": {"body": []},
    }


def _mock_registry(*, json_modes=None):
    """Build a mock ModeRegistry for JSON modes."""
    json_modes = set(json_modes or [])
    mock_reg = MagicMock()
    mock_reg.is_json_mode.side_effect = lambda p: p in json_modes
    
    def _get_json_mode(p, mac=None, *args, **kwargs):
        # testtext mac，textmode ID text JSON mode
        if p in json_modes:
            jm = MagicMock()
            jm.definition = {
                "mode_id": p,
                "content": {"type": "llm_json", "prompt_template": "test {context}", "output_schema": {"quote": {"default": "test"}}, "fallback": {"quote": "test"}},
                "layout": {"body": []},
            }
            return jm
        return None
    
    mock_reg.get_json_mode.side_effect = _get_json_mode
    return mock_reg


class TestPipelineApiKey:
    """test pipeline.py text api_key text"""

    @pytest.mark.asyncio
    async def test_pipeline_passes_user_api_key_to_json_content(self, sample_date_ctx, sample_weather, custom_mode_def):
        """test pipeline text api_key"""
        mock_reg = _mock_registry(json_modes=["TEST_CUSTOM"])
        user_api_key = "sk-user-key-12345"
        
        # text api_key
        from core.crypto import encrypt_api_key
        encrypted_key = encrypt_api_key(user_api_key)
        
        # text，pipeline text llm_api_key text Key，
        # text shared.build_image text config["user_api_key"]。
        # text generate_json_mode_content text api_key，
        # text config["user_api_key"] text。
        config = {
            "user_api_key": user_api_key,
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
        }
        
        with (
            patch("core.mode_registry.get_registry", return_value=mock_reg),
            patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gc,
        ):
            mock_gc.return_value = {"quote": "test", "author": "test"}
            
            await _generate_content_for_persona(
                "TEST_CUSTOM",
                config,
                sample_date_ctx,
                sample_weather["weather_str"],
            )
            
            # text api_key text
            call_args = mock_gc.call_args
            assert call_args is not None
            assert call_args.kwargs.get("api_key") == user_api_key

    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_decrypted_key(self, sample_date_ctx, sample_weather, custom_mode_def):
        """test pipeline text"""
        mock_reg = _mock_registry(json_modes=["TEST_CUSTOM"])
        
        # text user_api_key text（textinvalid）
        config = {
            "user_api_key": "",
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
        }
        
        with (
            patch("core.mode_registry.get_registry", return_value=mock_reg),
            patch("core.crypto.decrypt_api_key", return_value=""),  # text
            patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gc,
        ):
            mock_gc.return_value = {"quote": "test", "author": "test"}
            
            await _generate_content_for_persona(
                "TEST_CUSTOM",
                config,
                sample_date_ctx,
                sample_weather["weather_str"],
            )
            
            # text（textinvalid）
            call_args = mock_gc.call_args
            assert call_args is not None
            assert call_args.kwargs.get("api_key") == ""

    @pytest.mark.asyncio
    async def test_pipeline_uses_none_when_no_config(self, sample_date_ctx, sample_weather, custom_mode_def):
        """test pipeline text None"""
        mock_reg = _mock_registry(json_modes=["TEST_CUSTOM"])
        
        config = {
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
        }
        
        with (
            patch("core.mode_registry.get_registry", return_value=mock_reg),
            patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gc,
        ):
            mock_gc.return_value = {"quote": "test", "author": "test"}
            
            await _generate_content_for_persona(
                "TEST_CUSTOM",
                config,
                sample_date_ctx,
                sample_weather["weather_str"],
            )
            
            # text None（text）
            call_args = mock_gc.call_args
            assert call_args is not None
            assert call_args.kwargs.get("api_key") is None


class TestJsonContentApiKey:
    """test json_content.py text api_key text"""

    @pytest.mark.asyncio
    async def test_json_content_uses_user_api_key(self, custom_mode_def):
        """test json_content text api_key"""
        user_api_key = "sk-user-key-12345"
        
        with patch("core.json_content._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"quote": "test", "author": "test"}'
            
            await generate_json_mode_content(
                custom_mode_def,
                date_str="2025-03-12",
                weather_str="sunny 15°C",
                api_key=user_api_key,
            )
            
            # text _call_llm text api_key
            mock_llm.assert_called_once()
            call_args = mock_llm.call_args
            assert call_args.kwargs.get("api_key") == user_api_key

    @pytest.mark.asyncio
    async def test_json_content_uses_env_var_when_api_key_is_none(self, custom_mode_def):
        """test json_content text api_key text None text"""
        env_api_key = "sk-env-key-67890"
        
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}),
            patch("core.json_content._call_llm", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.return_value = '{"quote": "test", "author": "test"}'
            
            await generate_json_mode_content(
                custom_mode_def,
                date_str="2025-03-12",
                weather_str="sunny 15°C",
                api_key=None,  # text
            )
            
            # text _call_llm text，_get_client text
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_json_content_raises_error_when_user_key_empty(self, custom_mode_def):
        """test json_content text api_key text"""
        with (
            patch.dict(os.environ, {}, clear=True),  # text
            patch("core.json_content._call_llm", new_callable=AsyncMock) as mock_llm,
        ):
            # _get_client text LLMKeyMissingError
            mock_llm.side_effect = LLMKeyMissingError("text API key textinvalid")
            
            result = await generate_json_mode_content(
                custom_mode_def,
                date_str="2025-03-12",
                weather_str="sunny 15°C",
                api_key="",  # text
            )
            
            # text fallback text，text api_key_invalid
            assert "quote" in result
            assert result.get("_api_key_invalid") is True

    @pytest.mark.asyncio
    async def test_json_content_passes_api_key_to_nested_calls(self, custom_mode_def):
        """test json_content text api_key"""
        user_api_key = "sk-user-key-12345"
        
        # test external_data text（briefing provider）
        mode_def_briefing = {
            "mode_id": "TEST_BRIEFING",
            "content": {
                "type": "external_data",
                "provider": "briefing",
                "summarize": True,
                "include_insight": True,
            },
            "layout": {"body": []},
        }
        
        with (
            patch("core.content.fetch_hn_top_stories", new_callable=AsyncMock) as mock_hn,
            patch("core.content.fetch_ph_top_product", new_callable=AsyncMock) as mock_ph,
            patch("core.content.fetch_v2ex_hot", new_callable=AsyncMock) as mock_v2ex,
            patch("core.content.summarize_briefing_content", new_callable=AsyncMock) as mock_summarize,
            patch("core.content.generate_briefing_insight", new_callable=AsyncMock) as mock_insight,
        ):
            mock_hn.return_value = [{"title": "test", "score": 10}]
            mock_ph.return_value = {"name": "test", "tagline": "test"}
            mock_v2ex.return_value = []
            mock_summarize.return_value = ([{"title": "test"}], {"name": "test"})
            mock_insight.return_value = "test insight"
            
            await generate_json_mode_content(
                mode_def_briefing,
                date_str="2025-03-12",
                weather_str="sunny 15°C",
                language="en",
                api_key=user_api_key,
            )
            
            # text api_key
            mock_summarize.assert_called_once()
            assert mock_summarize.call_args.kwargs.get("api_key") == user_api_key
            assert mock_summarize.call_args.kwargs.get("language") == "en"
            mock_insight.assert_called_once()
            assert mock_insight.call_args.kwargs.get("api_key") == user_api_key
            assert mock_insight.call_args.kwargs.get("language") == "en"


class TestModeGeneratorApiKey:
    """test mode_generator.py text api_key text"""

    @pytest.mark.asyncio
    async def test_mode_generator_uses_user_api_key(self):
        """test mode_generator text api_key"""
        user_api_key = "sk-user-key-12345"
        
        with patch("core.mode_generator._get_client") as mock_get_client:
            mock_client = MagicMock()
            # text mock response
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message = MagicMock(content='{"mode_id": "TEST", "display_name": "Test"}')
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock(total_tokens=100)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = (mock_client, 1024)
            
            try:
                await _call_llm_with_messages(
                    "deepseek",
                    "deepseek-chat",
                    [{"role": "user", "content": "test"}],
                    api_key=user_api_key,
                )
            except Exception:
                pass  # text，text api_key text
            
            # text _get_client text api_key
            mock_get_client.assert_called_once()
            call_args = mock_get_client.call_args
            assert call_args.kwargs.get("api_key") == user_api_key

    @pytest.mark.asyncio
    async def test_generate_mode_definition_passes_api_key(self):
        """test generate_mode_definition text api_key"""
        user_api_key = "sk-user-key-12345"
        
        with (
            patch("core.mode_generator._call_llm_with_messages", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.return_value = '{"mode_id": "TEST", "display_name": "Test", "content": {"type": "llm"}, "layout": {"body": []}}'
            
            try:
                await generate_mode_definition(
                    description="testmode",
                    provider="deepseek",
                    model="deepseek-chat",
                    api_key=user_api_key,
                )
            except Exception:
                pass  # text，text api_key text
            
            # text _call_llm_with_messages text api_key
            mock_llm.assert_called_once()
            call_args = mock_llm.call_args
            assert call_args.kwargs.get("api_key") == user_api_key


class TestGetClientApiKey:
    """test _get_client text api_key text"""

    def test_get_client_uses_user_api_key(self):
        """test _get_client text api_key"""
        user_api_key = "sk-user-key-12345"
        
        client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=user_api_key)
        
        assert client is not None
        assert max_tokens > 0
        # text client text api_key（text client text api_key text）
        assert hasattr(client, "_client")
        # text：AsyncOpenAI text api_key text，text，text

    def test_get_client_uses_env_var_when_api_key_is_none(self):
        """test _get_client text api_key text None text"""
        env_api_key = "sk-env-key-67890"
        
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}):
            client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=None)
            
            assert client is not None
            assert max_tokens > 0

    def test_get_client_raises_error_when_user_key_empty(self):
        """test _get_client text api_key text"""
        with (
            patch.dict(os.environ, {}, clear=True),  # text
        ):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key="")
            
            # text"text"
            assert "text" in str(exc_info.value)

    def test_get_client_raises_error_when_no_key_at_all(self):
        """test _get_client text api_key text"""
        with (
            patch.dict(os.environ, {}, clear=True),  # text
        ):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key=None)
            
            # text"text"（text）
            assert "text" not in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
