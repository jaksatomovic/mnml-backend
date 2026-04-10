"""Smoke tests for surface PNG preview rendering."""

from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from core.surface_preview_render import render_surface_preview_image


def _fake_tile(*_a, **_k):
    return Image.new("L", (100, 80), 200), {}, {}


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
