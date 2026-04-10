"""
test JSON text
testtext（text LLM API text）
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.errors import LLMKeyMissingError
from core.json_content import (
    _parse_llm_output,
    _parse_text_split,
    _parse_json_output,
    _parse_llm_json_output,
    _apply_post_process,
    generate_json_mode_content,
)


def test_parse_text_split_basic():
    cfg = {
        "output_separator": "|",
        "output_fields": ["quote", "author"],
    }
    fallback = {"quote": "default", "author": "unknown"}

    result = _parse_text_split("text | Li Bai", cfg, fallback)
    assert result["quote"] == "text"
    assert result["author"] == "Li Bai"


def test_parse_text_split_missing_fields():
    cfg = {
        "output_separator": "|",
        "output_fields": ["quote", "author"],
    }
    fallback = {"quote": "default", "author": "anonymous"}

    result = _parse_text_split("text", cfg, fallback)
    assert result["quote"] == "text"
    assert result["author"] == "anonymous"


def test_parse_text_split_strips_quotes():
    cfg = {
        "output_separator": "|",
        "output_fields": ["quote", "author"],
    }
    fallback = {}

    result = _parse_text_split('"Hello World" | Author', cfg, fallback)
    assert result["quote"] == "Hello World"


def test_parse_json_output_basic():
    cfg = {
        "output_fields": ["title", "author"],
    }
    fallback = {"title": "default", "author": "unknown"}

    result = _parse_json_output('{"title": "Quiet Night Thought", "author": "Li Bai"}', cfg, fallback)
    assert result["title"] == "Quiet Night Thought"
    assert result["author"] == "Li Bai"


def test_parse_json_output_with_markdown_fence():
    cfg = {
        "output_fields": ["title", "note"],
    }
    fallback = {"title": "default", "note": "text"}

    text = '```json\n{"title": "text", "note": "text"}\n```'
    result = _parse_json_output(text, cfg, fallback)
    assert result["title"] == "text"
    assert result["note"] == "text"


def test_parse_json_output_missing_fields_use_fallback():
    cfg = {
        "output_fields": ["a", "b", "c"],
    }
    fallback = {"a": "1", "b": "2", "c": "3"}

    result = _parse_json_output('{"a": "hello"}', cfg, fallback)
    assert result["a"] == "hello"
    assert result["b"] == "2"
    assert result["c"] == "3"


def test_parse_json_output_invalid_json_returns_fallback():
    cfg = {"output_fields": ["text"]}
    fallback = {"text": "defaulttext"}

    result = _parse_json_output("not json at all {{{", cfg, fallback)
    assert result["text"] == "defaulttext"


def test_parse_llm_json_output_with_schema():
    cfg = {
        "output_schema": {
            "workout_name": {"type": "string", "default": "defaulttext"},
            "duration": {"type": "string", "default": "15 min"},
            "exercises": {"type": "array", "default": []},
        },
    }
    fallback = {"workout_name": "fallback", "duration": "0", "exercises": []}

    text = '{"workout_name": "core workout", "duration": "20 min", "exercises": [{"name": "squat"}]}'
    result = _parse_llm_json_output(text, cfg, fallback)
    assert result["workout_name"] == "core workout"
    assert result["duration"] == "20 min"
    assert len(result["exercises"]) == 1


def test_parse_llm_json_output_uses_schema_defaults():
    cfg = {
        "output_schema": {
            "title": {"type": "string", "default": "defaulttext"},
            "items": {"type": "array", "default": ["a", "b"]},
        },
    }
    fallback = {}

    text = '{"title": "text"}'
    result = _parse_llm_json_output(text, cfg, fallback)
    assert result["title"] == "text"
    assert result["items"] == ["a", "b"]


def test_parse_llm_json_output_invalid_returns_fallback():
    cfg = {"output_schema": {"x": {"type": "string", "default": ""}}}
    fallback = {"x": "fallback_value"}

    result = _parse_llm_json_output("broken json {{{", cfg, fallback)
    assert result["x"] == "fallback_value"


def test_parse_llm_output_raw():
    cfg = {
        "output_format": "raw",
        "output_fields": ["word"],
    }
    fallback = {"word": "text"}

    result = _parse_llm_output("text", cfg, fallback)
    assert result["word"] == "text"


def test_parse_llm_output_dispatches_text_split():
    cfg = {
        "output_format": "text_split",
        "output_separator": "|",
        "output_fields": ["a", "b"],
    }
    fallback = {"a": "", "b": ""}

    result = _parse_llm_output("hello|world", cfg, fallback)
    assert result["a"] == "hello"
    assert result["b"] == "world"


def test_parse_llm_output_dispatches_json():
    cfg = {
        "output_format": "json",
        "output_fields": ["name"],
    }
    fallback = {"name": "default"}

    result = _parse_llm_output('{"name": "test"}', cfg, fallback)
    assert result["name"] == "test"


def test_apply_post_process_first_char():
    cfg = {"post_process": {"word": "first_char"}}
    result = _apply_post_process({"word": "text"}, cfg)
    assert result["word"] == "text"


@pytest.mark.asyncio
async def test_generate_external_halo_f1_content():
    mode_def = {
        "mode_id": "HALO_F1",
        "display_name": "halo-f1",
        "content": {
            "type": "external_data",
            "provider": "halo_f1",
            "fallback": {
                "race_name": "Fallback GP",
                "driver_rows": [],
                "constructor_rows": [],
            },
        },
        "layout": {
            "body": [
                {"type": "text", "field": "race_name"}
            ]
        },
    }
    config = {"timezone": "Europe/Zagreb", "mode_settings": {"top_n": 5, "standings_view": "drivers"}}

    with patch("core.f1.get_halo_f1_snapshot", new_callable=AsyncMock) as mock_snapshot:
        mock_snapshot.return_value = {
            "race_name": "Belgian Grand Prix",
            "next_session_label": "Qualifying",
            "next_session_time": "15:00",
            "driver_rows": [{"position": "1", "name": "M. Verstappen", "points": "100"}],
            "constructor_rows": [{"position": "1", "name": "Red Bull", "points": "180"}],
        }

        result = await generate_json_mode_content(
            mode_def,
            date_ctx={},
            date_str="2026-04-09",
            weather_str="18C",
            config=config,
            screen_w=400,
            screen_h=300,
            language="en",
        )

    mock_snapshot.assert_awaited_once_with(timezone_name="Europe/Zagreb", top_n=5, standings_view="drivers")
    assert result["race_name"] == "Belgian Grand Prix"
    assert result["next_session_label"] == "Qualifying"
    assert result["driver_rows"][0]["name"] == "M. Verstappen"
    assert result["constructor_rows"][0]["name"] == "Red Bull"


def test_apply_post_process_first_char_empty():
    cfg = {"post_process": {"word": "first_char"}}
    result = _apply_post_process({"word": ""}, cfg)
    assert result["word"] == ""


def test_apply_post_process_strip_quotes():
    cfg = {"post_process": {"text": "strip_quotes"}}
    result = _apply_post_process({"text": '"Hello World"'}, cfg)
    assert result["text"] == "Hello World"


def test_apply_post_process_no_rules():
    cfg = {}
    result = _apply_post_process({"text": "unchanged"}, cfg)
    assert result["text"] == "unchanged"


def test_apply_post_process_skips_non_string():
    cfg = {"post_process": {"items": "first_char"}}
    result = _apply_post_process({"items": [1, 2, 3]}, cfg)
    assert result["items"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_llm_key_missing_returns_fallback():
    """text LLM API key text，text fallback text"""
    mode_def = {
        "mode_id": "STOIC",
        "content": {
            "type": "llm_json",
            "prompt_template": "test {context}",
            "output_schema": {"quote": {"default": "fallback quote"}, "author": {"default": "fallback author"}},
            "fallback": {"quote": "fallback quote", "author": "fallback author"},
        },
        "layout": {"body": []},
    }
    with patch("core.json_content._call_llm", new_callable=AsyncMock, side_effect=LLMKeyMissingError("Missing API key")):
        result = await generate_json_mode_content(
            mode_def,
            date_str="2025-03-12",
            weather_str="sunny 15°C",
        )
    assert "quote" in result
    assert "author" in result
    assert result["quote"] == "fallback quote"
    assert result["author"] == "fallback author"


@pytest.mark.asyncio
async def test_weather_external_data_does_not_mark_llm_used():
    mode_def = {
        "mode_id": "WEATHER",
        "content": {
            "type": "external_data",
            "provider": "weather_forecast",
            "fallback": {
                "city": "",
                "today_temp": "--",
                "today_desc": "text",
                "today_code": -1,
                "today_low": "--",
                "today_high": "--",
                "today_range": "-- / --",
                "advice": "textweathertext",
                "forecast": [],
            },
        },
        "layout": {"body": []},
    }
    weather_payload = {
        "city": "Shanghai",
        "today_temp": 16,
        "today_desc": "cloudy",
        "today_code": 2,
        "today_low": 12,
        "today_high": 19,
        "today_range": "12°C / 19°C",
        "advice": "text，text",
        "forecast": [],
    }

    with patch("core.json_content._generate_external_data_content", new_callable=AsyncMock) as mock_external:
        mock_external.return_value = weather_payload
        result = await generate_json_mode_content(
            mode_def,
            date_str="2025-03-12",
            weather_str="cloudy 16°C",
        )

    assert result["city"] == "Shanghai"
    assert result["advice"] == "text，text"
    assert "_llm_used" not in result


@pytest.mark.asyncio
async def test_countdown_preview_override_keeps_message_and_event_in_sync():
    mode_def = {
        "mode_id": "COUNTDOWN",
        "content": {
            "type": "computed",
            "provider": "countdown",
            "fallback": {"events": []},
        },
        "layout": {"body": []},
    }

    result = await generate_json_mode_content(
        mode_def,
        config={
            "mode_overrides": {
                "COUNTDOWN": {
                    "events": [
                        {"name": "test1", "date": "2099-01-01", "type": "countdown", "days": 123},
                    ]
                }
            },
            "content_tone": "positive",
        },
        date_str="2025-03-12",
        weather_str="sunny 15°C",
    )

    assert result["events"][0]["name"] == "test1"
    assert "test1" in result["message"]


@pytest.mark.asyncio
async def test_habit_computed_content_ignores_stale_derived_override_fields():
    mode_def = {
        "mode_id": "HABIT",
        "content": {
            "type": "computed",
            "provider": "habit",
            "fallback": {"habits": [], "summary": "", "week_progress": 0, "week_total": 7},
        },
        "layout": {"body": []},
    }

    result = await generate_json_mode_content(
        mode_def,
        config={
            "mode_overrides": {
                "HABIT": {
                    "habitItems": [
                        {"name": "text", "done": True},
                        {"name": "text", "done": False},
                    ],
                    "habits": [{"name": "text", "done": False, "status": "○"}],
                    "summary": "text summary",
                    "week_progress": 99,
                    "week_total": 99,
                }
            }
        },
        date_str="2025-03-12",
        weather_str="sunny 15°C",
        language="zh",
    )

    assert result["habits"] == [
        {"name": "text", "done": True, "status": "●"},
        {"name": "text", "done": False, "status": "○"},
    ]
    assert "text summary" not in result["summary"]
    assert "text 1/2 text" in result["summary"]
    assert result["week_progress"] == 1
    assert result["week_total"] == 2


if __name__ == "__main__":
    test_parse_text_split_basic()
    test_parse_text_split_missing_fields()
    test_parse_text_split_strips_quotes()
    test_parse_json_output_basic()
    test_parse_json_output_with_markdown_fence()
    test_parse_json_output_missing_fields_use_fallback()
    test_parse_json_output_invalid_json_returns_fallback()
    test_parse_llm_json_output_with_schema()
    test_parse_llm_json_output_uses_schema_defaults()
    test_parse_llm_json_output_invalid_returns_fallback()
    test_parse_llm_output_raw()
    test_parse_llm_output_dispatches_text_split()
    test_parse_llm_output_dispatches_json()
    test_apply_post_process_first_char()
    test_apply_post_process_first_char_empty()
    test_apply_post_process_strip_quotes()
    test_apply_post_process_no_rules()
    test_apply_post_process_skips_non_string()
    print("✓ All JSON content tests passed")
