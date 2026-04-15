"""Smoke tests for surface PNG preview rendering."""

from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from core.surface_preview_render import render_surface_preview_image


def _fake_tile(*_a, **_k):
    return Image.new("L", (100, 80), 200), {}


@pytest.mark.asyncio
async def test_render_surface_preview_uses_generate_and_render():
    with patch("core.surface_preview_render.generate_and_render", new_callable=AsyncMock) as gr:
        gr.side_effect = _fake_tile
        img = await render_surface_preview_image(
            {
                "id": "morning",
                "layout": [
                    {"mode": "WEATHER", "position": "top"},
                    {"mode": "CALENDAR", "position": "middle"},
                    {"mode": "DAILY", "position": "bottom"},
                ],
            },
            screen_w=400,
            screen_h=300,
            device_config=None,
            mac="",
        )
    assert img.size == (400, 300)
    assert img.mode == "1"
    assert gr.await_count == 3


@pytest.mark.asyncio
async def test_single_full_grid_slot_renders_standalone_full_frame():
    """FULL surface covering the entire grid uses one full-frame render (like inksight-main / widget FULL)."""
    with patch("core.surface_preview_render.generate_and_render", new_callable=AsyncMock) as gr:
        gr.side_effect = lambda *_a, **_k: (Image.new("L", (400, 300), 200), {})
        await render_surface_preview_image(
            {
                "id": "solo_full",
                "grid": {"columns": 2, "rows": 2, "gap": 6, "padding": 8},
                "slots": [
                    {
                        "id": "full",
                        "x": 0,
                        "y": 0,
                        "w": 2,
                        "h": 2,
                        "slot_type": "FULL",
                        "mode_id": "WEATHER",
                    },
                ],
                "layout": [{"mode": "WEATHER"}],
            },
            screen_w=400,
            screen_h=300,
            device_config=None,
            mac="",
        )
    assert gr.await_count == 1
    assert gr.call_args.kwargs["omit_chrome"] is False
    assert gr.call_args.kwargs["screen_w"] == 400
    assert gr.call_args.kwargs["screen_h"] == 300


@pytest.mark.asyncio
async def test_legacy_type_maps_to_mode():
    with patch("core.surface_preview_render.generate_and_render", new_callable=AsyncMock) as gr:
        gr.side_effect = _fake_tile
        await render_surface_preview_image(
            {
                "id": "x",
                "layout": [{"type": "weather", "position": "top"}],
            },
            screen_w=400,
            screen_h=300,
            device_config=None,
            mac="",
        )
    assert gr.call_args_list[0][0][0] == "WEATHER"
