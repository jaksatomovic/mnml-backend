"""
test JSON text
text 1-bit e-ink text
"""
import json
import os
import sys
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image
from core.json_renderer import render_json_mode, RenderContext, _localized_footer_label, _localized_footer_attribution
from core.config import SCREEN_WIDTH as SCREEN_W, SCREEN_HEIGHT as SCREEN_H


def _make_mode_def(body_blocks, content_type="static", footer=None):
    return {
        "mode_id": "TEST",
        "display_name": "Test",
        "content": {"type": content_type},
        "layout": {
            "status_bar": {"line_width": 1, "dashed": False},
            "body": body_blocks,
            "footer": footer or {"label": "TEST", "attribution_template": ""},
        },
    }


def test_render_produces_correct_size_image():
    mode_def = _make_mode_def([
        {"type": "centered_text", "field": "text", "font_size": 16, "vertical_center": True}
    ])
    content = {"text": "Hello World"}
    img = render_json_mode(
        mode_def, content,
        date_str="1/1", weather_str="sunny 20°C", battery_pct=85,
    )
    assert isinstance(img, Image.Image)
    assert img.size == (SCREEN_W, SCREEN_H)
    assert img.mode == "1"


def test_render_centered_text():
    mode_def = _make_mode_def([
        {"type": "centered_text", "field": "quote", "font_size": 14, "vertical_center": True}
    ])
    content = {"quote": "testtextChinesetext"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="cloudy 15°C", battery_pct=90,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_text_block():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 20},
        {"type": "text", "field": "title", "font_size": 16, "align": "center"},
        {"type": "text", "template": "text: {author}", "font_size": 12, "align": "center"},
    ])
    content = {"title": "Quiet Night Thought", "author": "Li Bai"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=75,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_separator():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 50},
        {"type": "separator", "style": "solid", "margin_x": 24},
        {"type": "spacer", "height": 10},
        {"type": "separator", "style": "dashed", "margin_x": 24},
        {"type": "spacer", "height": 10},
        {"type": "separator", "style": "short", "width": 60},
    ])
    img = render_json_mode(
        _make_mode_def([
            {"type": "spacer", "height": 50},
            {"type": "separator", "style": "solid"},
            {"type": "separator", "style": "dashed"},
            {"type": "separator", "style": "short", "width": 60},
        ]), {},
        date_str="1/1", weather_str="sunny", battery_pct=100,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_list_with_dicts():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 14},
        {
            "type": "list",
            "field": "exercises",
            "max_items": 5,
            "item_template": "{name}",
            "right_field": "reps",
            "font_size": 13,
            "margin_x": 32,
            "numbered": True,
            "item_spacing": 16,
        },
    ])
    content = {
        "exercises": [
            {"name": "squat", "reps": "20 reps"},
            {"name": "push-up", "reps": "15 reps"},
            {"name": "plank", "reps": "30text"},
        ]
    }
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_list_with_strings():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 14},
        {
            "type": "list",
            "field": "lines",
            "max_items": 4,
            "item_template": "{_value}",
            "font_size": 16,
            "item_spacing": 24,
            "margin_x": 30,
            "align": "center",
        },
    ])
    content = {"lines": ["Moonlight before my bed", "Like frost upon the ground", "I raise my head to the moon", "I lower my head and think of home"]}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_section_with_icon():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 14},
        {
            "type": "section",
            "title": "text",
            "icon": "exercise",
            "children": [
                {"type": "text", "field": "tip", "font_size": 13, "align": "left", "margin_x": 40},
            ],
        },
    ])
    content = {"tip": "text"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_vertical_stack():
    mode_def = _make_mode_def([
        {
            "type": "vertical_stack",
            "spacing": 4,
            "children": [
                {"type": "spacer", "height": 14},
                {"type": "text", "field": "a", "font_size": 14, "align": "center"},
                {"type": "separator", "style": "solid"},
                {"type": "text", "field": "b", "font_size": 14, "align": "center"},
            ],
        },
    ])
    content = {"a": "text", "b": "text"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_conditional():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 14},
        {
            "type": "conditional",
            "field": "count",
            "conditions": [
                {
                    "op": "gt",
                    "value": 5,
                    "children": [
                        {"type": "text", "template": "text: {count}", "font_size": 14, "align": "center"},
                    ],
                },
            ],
            "fallback_children": [
                {"type": "text", "template": "text: {count}", "font_size": 14, "align": "center"},
            ],
        },
    ])

    # count = 10 -> "text"
    img1 = render_json_mode(
        mode_def, {"count": 10},
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img1.size == (SCREEN_W, SCREEN_H)

    # count = 3 -> fallback "text"
    img2 = render_json_mode(
        mode_def, {"count": 3},
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img2.size == (SCREEN_W, SCREEN_H)


def test_render_icon_text():
    mode_def = _make_mode_def([
        {"type": "spacer", "height": 40},
        {"type": "icon_text", "icon": "book", "text": "recommended reading", "font_size": 14, "margin_x": 24},
    ])
    img = render_json_mode(
        mode_def, {},
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_with_footer_template():
    mode_def = _make_mode_def(
        [{"type": "centered_text", "field": "quote", "font_size": 16}],
        footer={"label": "CUSTOM", "attribution_template": "— {author}", "dashed": True},
    )
    content = {"quote": "Test", "author": "Author"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_image_block_preserves_palette_colors():
    src = Image.new("RGB", (4, 2), "white")
    src.putpixel((0, 0), (200, 0, 0))
    src.putpixel((1, 0), (232, 176, 0))
    src.putpixel((2, 0), (0, 0, 0))
    buf = BytesIO()
    src.save(buf, format="PNG")
    mode_def = _make_mode_def([
        {"type": "image", "field": "image_url", "width": 40, "height": 20, "x": 100, "y": 80}
    ])
    content = {
        "image_url": "prefetched://artwall",
        "_prefetched_image_url": buf.getvalue(),
    }
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
        colors=4,
    )
    assert img.mode == "P"
    palette_indexes = set(img.crop((100, 80, 140, 100)).getdata())
    assert 3 in palette_indexes
    assert 2 in palette_indexes


def test_builtin_footer_localization():
    assert _localized_footer_label("COUNTDOWN", "COUNTDOWN", "zh") == "countdown"
    assert _localized_footer_label("COUNTDOWN", "Countdown", "en") == "Countdown"
    assert _localized_footer_attribution("COUNTDOWN", "— Remember", "zh") == "— wait for that day"
    assert _localized_footer_attribution("COUNTDOWN", "— Remember", "en") == "— Remember"


def test_render_with_dashed_status_bar():
    mode_def = {
        "mode_id": "ZEN_TEST",
        "display_name": "Zen Test",
        "content": {"type": "static"},
        "layout": {
            "status_bar": {"line_width": 1, "dashed": True},
            "body": [
                {"type": "centered_text", "field": "word", "font": "noto_serif_regular", "font_size": 48, "vertical_center": True}
            ],
            "footer": {"label": "ZEN", "attribution_template": "— ...", "dashed": True},
        },
    }
    content = {"word": "text"}
    img = render_json_mode(
        mode_def, content,
        date_str="2/18", weather_str="sunny", battery_pct=80,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_context_resolve():
    """Test RenderContext.resolve template substitution."""
    from PIL import ImageDraw
    img = Image.new("1", (100, 100), 1)
    draw = ImageDraw.Draw(img)
    ctx = RenderContext(draw=draw, img=img, content={"name": "Alice", "count": 42})

    assert ctx.resolve("Hello {name}!") == "Hello Alice!"
    assert ctx.resolve("{count} items") == "42 items"
    assert ctx.resolve("no placeholders") == "no placeholders"
    assert ctx.resolve("{missing}") == ""


def test_render_stoic_json():
    """End-to-end: render using the builtin STOIC JSON definition."""
    stoic_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "modes", "builtin", "stoic.json"
    )
    with open(stoic_path, "r", encoding="utf-8") as f:
        mode_def = json.load(f)

    content = {
        "quote": "The impediment to action advances action.",
        "author": "Marcus Aurelius",
    }
    img = render_json_mode(
        mode_def, content,
        date_str="2/18 Tue", weather_str="sunny 15°C", battery_pct=85,
        weather_code=0, time_str="14:30",
    )
    assert img.size == (SCREEN_W, SCREEN_H)
    assert img.mode == "1"


def test_render_fitness_json():
    """End-to-end: render using the builtin FITNESS JSON definition."""
    fitness_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "modes", "builtin", "fitness.json"
    )
    with open(fitness_path, "r", encoding="utf-8") as f:
        mode_def = json.load(f)

    content = {
        "workout_name": "morning stretch",
        "duration": "15 min",
        "exercises": [
            {"name": "neck stretch", "reps": "10 reps"},
            {"name": "shoulder circles", "reps": "15 reps"},
            {"name": "waist twist", "reps": "20 reps"},
        ],
        "tip": "Warm up fully before exercise to avoid injury.",
    }
    img = render_json_mode(
        mode_def, content,
        date_str="2/18 Tue", weather_str="cloudy 12°C", battery_pct=70,
        weather_code=3, time_str="07:00",
    )
    assert img.size == (SCREEN_W, SCREEN_H)


def test_render_poetry_json():
    """End-to-end: render using the builtin POETRY JSON definition."""
    poetry_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "modes", "builtin", "poetry.json"
    )
    with open(poetry_path, "r", encoding="utf-8") as f:
        mode_def = json.load(f)

    content = {
        "title": "Quiet Night Thought",
        "author": "Tang · Li Bai",
        "lines": ["Moonlight before my bed", "Like frost upon the ground", "I raise my head to the moon", "I lower my head and think of home"],
        "note": "classic poem of homesickness",
    }
    img = render_json_mode(
        mode_def, content,
        date_str="2/18 Tue", weather_str="sunny", battery_pct=90,
    )
    assert img.size == (SCREEN_W, SCREEN_H)


if __name__ == "__main__":
    test_render_produces_correct_size_image()
    test_render_centered_text()
    test_render_text_block()
    test_render_separator()
    test_render_list_with_dicts()
    test_render_list_with_strings()
    test_render_section_with_icon()
    test_render_vertical_stack()
    test_render_conditional()
    test_render_icon_text()
    test_render_with_footer_template()
    test_render_with_dashed_status_bar()
    test_render_context_resolve()
    test_render_stoic_json()
    test_render_fitness_json()
    test_render_poetry_json()
    print("✓ All JSON renderer tests passed")
