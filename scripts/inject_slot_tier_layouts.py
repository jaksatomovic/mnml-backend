#!/usr/bin/env python3
"""Merge slot_lg / slot_md / slot_sm / slot_xs into builtin mode JSON files.

Run from repo root: python backend/scripts/inject_slot_tier_layouts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
BUILTIN = BACKEND / "core/modes/builtin"
EN = BUILTIN / "en"

TIER_KEYS = ("slot_lg", "slot_md", "slot_sm", "slot_xs")


def _stoic() -> dict[str, dict]:
    foot = {"label": "???", "attribution_template": "— {author}"}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 18,
                    "max_width_ratio": 0.88,
                    "vertical_center": True,
                }
            ],
            "footer": foot,
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 16,
                    "max_width_ratio": 0.9,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 24},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 14,
                    "max_width_ratio": 0.92,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 20},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 11,
                    "max_width_ratio": 0.94,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 16},
        },
    }


def _memo() -> dict[str, dict]:
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "memo_text",
                    "font_name": "NotoSerifSC-Light.ttf",
                    "font_size": 15,
                    "vertical_center": True,
                    "max_width_ratio": 0.86,
                }
            ],
            "footer": {"label": "MEMO"},
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "memo_text",
                    "font_name": "NotoSerifSC-Light.ttf",
                    "font_size": 14,
                    "vertical_center": True,
                    "max_width_ratio": 0.9,
                }
            ],
            "footer": {"label": "MEMO", "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "memo_text",
                    "font_name": "NotoSerifSC-Light.ttf",
                    "font_size": 13,
                    "vertical_center": True,
                    "max_width_ratio": 0.92,
                }
            ],
            "footer": {"label": "MEMO", "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "memo_text",
                    "font_name": "NotoSerifSC-Light.ttf",
                    "font_size": 10,
                    "vertical_center": True,
                    "max_width_ratio": 0.95,
                }
            ],
            "footer": {"label": "MEMO", "height": 16},
        },
    }


def _habit() -> dict[str, dict]:
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "summary",
                    "font": "noto_serif_regular",
                    "font_size": 15,
                    "max_width_ratio": 0.86,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": "HABIT"},
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "summary",
                    "font": "noto_serif_regular",
                    "font_size": 14,
                    "max_width_ratio": 0.88,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": "HABIT", "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "summary",
                    "font": "noto_serif_regular",
                    "font_size": 12,
                    "max_width_ratio": 0.92,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": "HABIT", "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "summary",
                    "font": "noto_serif_regular",
                    "font_size": 10,
                    "max_width_ratio": 0.95,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": "HABIT", "height": 16},
        },
    }


def _zen() -> dict[str, dict]:
    ft = {"label": "??", "attribution_template": "— ...", "dashed": True}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_regular",
                    "font_size": 72,
                    "max_width_ratio": 0.72,
                    "vertical_center": True,
                },
                {"type": "spacer", "height": 6},
                {
                    "type": "text",
                    "field": "source",
                    "font": "noto_serif_light",
                    "font_size": 9,
                    "align": "center",
                    "max_lines": 1,
                },
            ],
            "footer": ft,
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_regular",
                    "font_size": 56,
                    "max_width_ratio": 0.72,
                    "vertical_center": True,
                }
            ],
            "footer": {**ft, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_regular",
                    "font_size": 44,
                    "max_width_ratio": 0.75,
                    "vertical_center": True,
                }
            ],
            "footer": {**ft, "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_regular",
                    "font_size": 32,
                    "max_width_ratio": 0.78,
                    "vertical_center": True,
                }
            ],
            "footer": {**ft, "height": 16},
        },
    }


def _weather() -> dict[str, dict]:
    wf = {"label": "WEATHER", "attribution_template": "— Open-Meteo"}
    return {
        "slot_lg": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "city", "font_size": 13, "align": "left", "margin_x": 14, "max_lines": 1},
                {"type": "spacer", "height": 4},
                {
                    "type": "two_column",
                    "left_width": 130,
                    "gap": 6,
                    "left_x": 12,
                    "left": [
                        {
                            "type": "big_number",
                            "field": "today_temp",
                            "font_size": 40,
                            "align": "left",
                            "margin_x": 0,
                            "unit": "°C",
                        },
                        {"type": "spacer", "height": 2},
                        {
                            "type": "weather_icon_text",
                            "code_field": "today_code",
                            "field": "today_desc",
                            "font_size": 13,
                            "icon_size": 20,
                            "align": "left",
                            "margin_x": 0,
                        },
                    ],
                    "right": [
                        {
                            "type": "forecast_cards",
                            "field": "forecast",
                            "max_items": 2,
                            "margin_x": 0,
                            "gap": 4,
                            "icon_size": 26,
                        }
                    ],
                },
                {"type": "spacer", "height": 4},
                {
                    "type": "text",
                    "field": "advice",
                    "font_size": 11,
                    "align": "center",
                    "max_lines": 2,
                    "margin_x": 12,
                },
            ],
            "footer": wf,
        },
        "slot_md": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "city", "font_size": 11, "align": "left", "margin_x": 10, "max_lines": 1},
                {"type": "spacer", "height": 3},
                {
                    "type": "two_column",
                    "left_width": 100,
                    "gap": 4,
                    "left_x": 10,
                    "left": [
                        {
                            "type": "big_number",
                            "field": "today_temp",
                            "font_size": 32,
                            "align": "left",
                            "margin_x": 0,
                            "unit": "°C",
                        },
                        {
                            "type": "weather_icon_text",
                            "code_field": "today_code",
                            "field": "today_desc",
                            "font_size": 11,
                            "icon_size": 18,
                            "align": "left",
                            "margin_x": 0,
                        },
                    ],
                    "right": [
                        {
                            "type": "forecast_cards",
                            "field": "forecast",
                            "max_items": 1,
                            "margin_x": 0,
                            "gap": 3,
                            "icon_size": 22,
                        }
                    ],
                },
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "city", "font_size": 10, "align": "left", "margin_x": 8, "max_lines": 1},
                {"type": "spacer", "height": 2},
                {
                    "type": "big_number",
                    "field": "today_temp",
                    "font_size": 26,
                    "align": "left",
                    "margin_x": 8,
                    "unit": "°C",
                },
                {
                    "type": "weather_icon_text",
                    "code_field": "today_code",
                    "field": "today_desc",
                    "font_size": 10,
                    "icon_size": 16,
                    "align": "left",
                    "margin_x": 8,
                },
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "city", "font_size": 9, "align": "center", "margin_x": 6, "max_lines": 1},
                {
                    "type": "big_number",
                    "field": "today_temp",
                    "font_size": 22,
                    "align": "center",
                    "margin_x": 8,
                    "unit": "°C",
                },
                {
                    "type": "text",
                    "field": "today_desc",
                    "font_size": 9,
                    "align": "center",
                    "margin_x": 6,
                    "max_lines": 1,
                },
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _calendar() -> dict[str, dict]:
    wf = {"label": "CALENDAR", "attribution_template": "— InkSight"}
    return {
        "slot_lg": {
            "body_align": "top",
            "body": [
                {
                    "type": "calendar_grid",
                    "font_size": 14,
                    "header_font_size": 10,
                    "sub_font_size": 7,
                    "margin_x": 8,
                    "cell_height": 26,
                },
                {"type": "spacer", "height": 2},
                {"type": "separator", "style": "dashed", "margin_x": 8},
                {"type": "text", "field": "text", "font_size": 11, "align": "center", "max_lines": 2, "margin_x": 8},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body_align": "top",
            "body": [
                {
                    "type": "calendar_grid",
                    "font_size": 12,
                    "header_font_size": 9,
                    "sub_font_size": 7,
                    "margin_x": 6,
                    "cell_height": 22,
                },
                {"type": "text", "field": "text", "font_size": 10, "align": "center", "max_lines": 1, "margin_x": 6},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body_align": "top",
            "body": [
                {
                    "type": "calendar_grid",
                    "font_size": 10,
                    "header_font_size": 8,
                    "sub_font_size": 6,
                    "margin_x": 4,
                    "cell_height": 18,
                },
                {"type": "text", "field": "text", "font_size": 9, "align": "center", "max_lines": 1, "margin_x": 4},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "calendar_title", "font_size": 10, "align": "center", "max_lines": 1, "margin_x": 6},
                {"type": "text", "field": "text", "font_size": 9, "align": "center", "max_lines": 2, "margin_x": 6},
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _timetable() -> dict[str, dict]:
    wf = {"label": "TIMETABLE", "attribution_template": "— InkSight"}
    return {
        "slot_lg": {
            "body_align": "top",
            "body": [
                {
                    "type": "timetable_grid",
                    "field": "slots",
                    "font_size": 11,
                    "margin_x": 5,
                    "row_height": 26,
                }
            ],
            "footer": wf,
        },
        "slot_md": {
            "body_align": "top",
            "body": [
                {
                    "type": "timetable_grid",
                    "field": "slots",
                    "font_size": 10,
                    "margin_x": 4,
                    "row_height": 24,
                }
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "timetable_title", "font_size": 11, "align": "center", "max_lines": 1, "margin_x": 6},
                {"type": "spacer", "height": 4},
                {
                    "type": "timetable_grid",
                    "field": "slots",
                    "font_size": 9,
                    "margin_x": 4,
                    "row_height": 20,
                },
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "timetable_title", "font_size": 10, "align": "center", "max_lines": 2, "margin_x": 6}
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _my_adaptive() -> dict[str, dict]:
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "image",
                    "field": "image_url",
                    "width": 320,
                    "height": 216,
                    "x": 0,
                    "y": 0,
                    "margin_bottom": 0,
                }
            ],
            "footer": {"line_width": 0},
        },
        "slot_md": {
            "body": [
                {
                    "type": "image",
                    "field": "image_url",
                    "width": 260,
                    "height": 176,
                    "x": 0,
                    "y": 0,
                    "margin_bottom": 0,
                }
            ],
            "footer": {"line_width": 0},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "image",
                    "field": "image_url",
                    "width": 200,
                    "height": 136,
                    "x": 0,
                    "y": 0,
                    "margin_bottom": 0,
                }
            ],
            "footer": {"line_width": 0},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "image",
                    "field": "image_url",
                    "width": 160,
                    "height": 108,
                    "x": 0,
                    "y": 0,
                    "margin_bottom": 0,
                }
            ],
            "footer": {"line_width": 0},
        },
    }


def _artwall() -> dict[str, dict]:
    wf = {"label": "ARTWALL", "attribution_template": "— Ink Art"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "artwork_title", "font_size": 12, "align": "center", "max_lines": 1},
                {"type": "image", "field": "image_url", "width": 220, "height": 148},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "artwork_title", "font_size": 11, "align": "center", "max_lines": 1},
                {"type": "image", "field": "image_url", "width": 180, "height": 120},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [{"type": "image", "field": "image_url", "width": 148, "height": 98}],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "image", "field": "image_url", "width": 120, "height": 80}],
            "footer": {**wf, "height": 16},
        },
    }


def _word_of_the_day() -> dict[str, dict]:
    wf = {"label": "WORD", "attribution_template": "— Daily Learning"}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_bold",
                    "font_size": 48,
                    "max_width_ratio": 0.88,
                    "vertical_center": False,
                },
                {"type": "spacer", "height": 4},
                {"type": "text", "field": "phonetic", "font": "noto_serif_light", "font_size": 10, "align": "center", "max_lines": 1},
                {"type": "text", "field": "definition", "font": "noto_serif_regular", "font_size": 13, "align": "center", "max_lines": 2, "margin_x": 8},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_bold",
                    "font_size": 36,
                    "max_width_ratio": 0.9,
                    "vertical_center": True,
                },
                {"type": "text", "field": "definition", "font": "noto_serif_regular", "font_size": 11, "align": "center", "max_lines": 2, "margin_x": 8},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_bold",
                    "font_size": 28,
                    "max_width_ratio": 0.92,
                    "vertical_center": True,
                },
                {"type": "text", "field": "definition", "font": "noto_serif_regular", "font_size": 10, "align": "center", "max_lines": 2, "margin_x": 6},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "word",
                    "font": "noto_serif_bold",
                    "font_size": 22,
                    "max_width_ratio": 0.94,
                    "vertical_center": True,
                }
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _briefing() -> dict[str, dict]:
    wf = {"label": "BRIEFING", "attribution_template": "— AI Brief"}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "section",
                    "title": "HN",
                    "icon": "global",
                    "title_font_size": 12,
                    "children": [
                        {
                            "type": "list",
                            "field": "hn_items",
                            "max_items": 2,
                            "item_template": "{title}",
                            "right_field": "score",
                            "font_size": 11,
                            "item_spacing": 16,
                            "margin_x": 28,
                        }
                    ],
                },
                {"type": "separator", "style": "dashed", "margin_x": 16},
                {"type": "text", "field": "insight", "font_size": 11, "align": "left", "margin_x": 16, "max_lines": 3},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {
                    "type": "list",
                    "field": "hn_items",
                    "max_items": 2,
                    "item_template": "{title}",
                    "font_size": 10,
                    "item_spacing": 14,
                    "margin_x": 12,
                },
                {"type": "text", "field": "insight", "font_size": 10, "align": "left", "margin_x": 12, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "list",
                    "field": "hn_items",
                    "max_items": 2,
                    "item_template": "{title}",
                    "font_size": 10,
                    "item_spacing": 12,
                    "margin_x": 8,
                },
                {"type": "text", "field": "insight", "font_size": 9, "align": "left", "margin_x": 8, "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [
                {"type": "text", "template": "{ph_name}", "font_size": 10, "align": "center", "margin_x": 6, "max_lines": 1},
                {"type": "text", "field": "insight", "font_size": 9, "align": "left", "margin_x": 6, "max_lines": 3},
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _daily() -> dict[str, dict]:
    wf = {"label": "DAILY", "attribution_template": "— Carpe Diem"}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "two_column",
                    "left_width": 100,
                    "gap": 8,
                    "left": [
                        {"type": "text", "field": "year", "font_size": 11, "align": "center", "margin_x": 6},
                        {"type": "big_number", "field": "day", "font_size": 40, "align": "center"},
                        {"type": "text", "field": "month_cn", "font_size": 12, "align": "center", "margin_x": 6},
                    ],
                    "right": [
                        {"type": "text", "field": "quote", "font_size": 12, "align": "left", "margin_x": 4, "max_lines": 3},
                        {"type": "text", "template": "— {author}", "font_size": 10, "align": "right", "margin_x": 4, "max_lines": 1},
                    ],
                }
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "big_number", "field": "day", "font_size": 34, "align": "left", "margin_x": 8},
                {"type": "text", "template": "{month_cn} · {weekday_cn}", "font_size": 10, "align": "left", "margin_x": 8, "max_lines": 1},
                {"type": "text", "field": "quote", "font_size": 11, "align": "left", "margin_x": 8, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "big_number", "field": "day", "font_size": 30, "align": "left", "margin_x": 8},
                {"type": "text", "field": "quote", "font_size": 10, "align": "left", "margin_x": 8, "max_lines": 2},
                {"type": "text", "template": "— {author}", "font_size": 9, "align": "right", "margin_x": 8, "max_lines": 1},
            ],
            "footer": {**wf, "height": 20},
        },
        "slot_xs": {
            "body": [
                {"type": "big_number", "field": "day", "font_size": 26, "align": "center", "margin_x": 8},
                {"type": "text", "field": "quote", "font_size": 9, "align": "center", "margin_x": 6, "max_lines": 2},
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _lifebar() -> dict[str, dict]:
    wf = {"label": "LIFEBAR", "attribution_template": "— Time Flies"}
    return {
        "slot_lg": {
            "body": [
                {"type": "spacer", "height": 6},
                {"type": "text", "field": "year_label", "font_size": 11, "align": "left", "margin_x": 16},
                {"type": "text", "template": "{year_pct}%", "font": "lora_bold", "font_size": 22, "align": "left", "margin_x": 16},
                {"type": "progress_bar", "field": "day_of_year", "max_field": "days_in_year", "width": 260, "height": 6, "margin_x": 16},
                {"type": "spacer", "height": 6},
                {"type": "text", "field": "life_label", "font_size": 10, "align": "left", "margin_x": 16},
                {"type": "text", "template": "{life_pct}%", "font": "lora_bold", "font_size": 18, "align": "left", "margin_x": 16},
                {"type": "progress_bar", "field": "age", "max_field": "life_expect", "width": 260, "height": 6, "margin_x": 16},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "year_label", "font_size": 10, "align": "left", "margin_x": 10},
                {"type": "text", "template": "{year_pct}%", "font": "lora_bold", "font_size": 18, "align": "left", "margin_x": 10},
                {"type": "progress_bar", "field": "day_of_year", "max_field": "days_in_year", "width": 220, "height": 6, "margin_x": 10},
                {"type": "text", "field": "life_label", "font_size": 9, "align": "left", "margin_x": 10},
                {"type": "progress_bar", "field": "age", "max_field": "life_expect", "width": 220, "height": 5, "margin_x": 10},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "text", "template": "{year_pct}% · {life_pct}%", "font": "lora_bold", "font_size": 14, "align": "center", "margin_x": 8, "max_lines": 1},
                {"type": "progress_bar", "field": "age", "max_field": "life_expect", "width": 200, "height": 5, "margin_x": 8},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [
                {"type": "text", "template": "{life_pct}%", "font": "lora_bold", "font_size": 16, "align": "center", "margin_x": 6, "max_lines": 1}
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _countdown() -> dict[str, dict]:
    wf = {"label": "translated", "attribution_template": "— translated"}
    return {
        "slot_lg": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "message", "font": "noto_serif_regular", "font_size": 14, "align": "center", "margin_x": 20, "max_lines": 2},
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{name}",
                    "font_size": 12,
                    "align": "center",
                },
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{days} translated",
                    "font_size": 40,
                    "align": "center",
                },
            ],
            "footer": wf,
        },
        "slot_md": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "message", "font": "noto_serif_regular", "font_size": 12, "align": "center", "margin_x": 14, "max_lines": 1},
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{days} translated",
                    "font_size": 32,
                    "align": "center",
                },
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body_align": "center",
            "body": [
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{name}",
                    "font_size": 10,
                    "align": "center",
                },
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{days} translated",
                    "font_size": 28,
                    "align": "center",
                },
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body_align": "center",
            "body": [
                {
                    "type": "list",
                    "field": "events",
                    "max_items": 1,
                    "item_template": "{days} translated",
                    "font_size": 22,
                    "align": "center",
                }
            ],
            "footer": {**wf, "height": 16},
        },
    }


PRESETS: dict[str, dict[str, dict]] = {
    "STOIC": _stoic(),
    "MEMO": _memo(),
    "HABIT": _habit(),
    "ZEN": _zen(),
    "WEATHER": _weather(),
    "CALENDAR": _calendar(),
    "TIMETABLE": _timetable(),
    "MY_ADAPTIVE": _my_adaptive(),
    "ARTWALL": _artwall(),
    "WORD_OF_THE_DAY": _word_of_the_day(),
    "BRIEFING": _briefing(),
    "DAILY": _daily(),
    "LIFEBAR": _lifebar(),
    "COUNTDOWN": _countdown(),
}


def _generic_centered(field: str, font: str, label: str) -> dict[str, dict]:
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": field,
                    "font": font,
                    "font_size": 15,
                    "max_width_ratio": 0.86,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": label},
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": field,
                    "font": font,
                    "font_size": 13,
                    "max_width_ratio": 0.9,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": label, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": field,
                    "font": font,
                    "font_size": 11,
                    "max_width_ratio": 0.93,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": label, "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": field,
                    "font": font,
                    "font_size": 9,
                    "max_width_ratio": 0.95,
                    "vertical_center": True,
                }
            ],
            "footer": {"label": label, "height": 16},
        },
    }


def _roast() -> dict[str, dict]:
    return _generic_centered("quote", "noto_serif_regular", "ROAST")


def _my_quote() -> dict[str, dict]:
    foot = {"label": "QUOTE", "attribution_template": "— {author}"}
    return {
        "slot_lg": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 16,
                    "max_width_ratio": 0.86,
                    "vertical_center": True,
                }
            ],
            "footer": foot,
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 14,
                    "max_width_ratio": 0.9,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 12,
                    "max_width_ratio": 0.93,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "quote",
                    "font_name": "Lora-Regular.ttf",
                    "font_size": 10,
                    "max_width_ratio": 0.95,
                    "vertical_center": True,
                }
            ],
            "footer": {**foot, "height": 16},
        },
    }


def _letter() -> dict[str, dict]:
    return _generic_centered("body", "noto_serif_regular", "LETTER")


def _bias() -> dict[str, dict]:
    wf = {"label": "BIAS"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "name_cn", "font": "noto_serif_bold", "font_size": 15, "align": "center"},
                {"type": "text", "field": "name_en", "font_size": 10, "align": "center"},
                {"type": "text", "field": "definition", "font_size": 12, "align": "center", "margin_x": 14, "max_lines": 3},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "name_cn", "font": "noto_serif_bold", "font_size": 13, "align": "center"},
                {"type": "text", "field": "definition", "font_size": 11, "align": "center", "margin_x": 12, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "text", "field": "name_cn", "font": "noto_serif_bold", "font_size": 12, "align": "center"},
                {"type": "text", "field": "definition", "font_size": 10, "align": "left", "margin_x": 8, "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "name_cn", "font": "noto_serif_bold", "font_size": 11, "align": "center", "max_lines": 2}],
            "footer": {**wf, "height": 16},
        },
    }


def _riddle() -> dict[str, dict]:
    wf = {"label": "RIDDLE"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "category", "font_size": 9, "align": "center"},
                {
                    "type": "centered_text",
                    "field": "question",
                    "font": "noto_serif_regular",
                    "font_size": 12,
                    "max_width_ratio": 0.9,
                    "vertical_center": False,
                },
                {"type": "text", "field": "answer", "font_size": 10, "align": "center", "max_lines": 1},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "question",
                    "font": "noto_serif_regular",
                    "font_size": 11,
                    "max_width_ratio": 0.92,
                    "vertical_center": True,
                },
                {"type": "text", "field": "answer", "font_size": 9, "align": "center", "max_lines": 1},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "question",
                    "font": "noto_serif_regular",
                    "font_size": 10,
                    "max_width_ratio": 0.94,
                    "vertical_center": True,
                }
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [
                {
                    "type": "centered_text",
                    "field": "question",
                    "font": "noto_serif_regular",
                    "font_size": 9,
                    "max_width_ratio": 0.95,
                    "vertical_center": True,
                }
            ],
            "footer": {**wf, "height": 16},
        },
    }


def _recipe() -> dict[str, dict]:
    wf = {"label": "RECIPE"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "season", "font": "noto_serif_bold", "font_size": 13, "align": "center"},
                {"type": "text", "field": "breakfast", "font_size": 11, "align": "left", "margin_x": 12, "max_lines": 1},
                {"type": "text", "field": "tip", "font": "noto_serif_light", "font_size": 10, "align": "center", "max_lines": 2},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "season", "font": "noto_serif_bold", "font_size": 12, "align": "center"},
                {"type": "text", "field": "tip", "font": "noto_serif_light", "font_size": 10, "align": "left", "margin_x": 10, "max_lines": 3},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "text", "field": "season", "font": "noto_serif_bold", "font_size": 11, "align": "center"},
                {"type": "text", "field": "tip", "font_size": 9, "align": "center", "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "season", "font": "noto_serif_bold", "font_size": 10, "align": "center", "max_lines": 2}],
            "footer": {**wf, "height": 16},
        },
    }


def _thisday() -> dict[str, dict]:
    wf = {"label": "THISDAY"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "event_title", "font": "noto_serif_bold", "font_size": 14, "align": "center"},
                {"type": "text", "field": "event_desc", "font_size": 11, "align": "left", "margin_x": 12, "max_lines": 3},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "event_title", "font": "noto_serif_bold", "font_size": 12, "align": "center"},
                {"type": "text", "field": "event_desc", "font_size": 10, "align": "left", "margin_x": 10, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "big_number", "field": "year", "font_size": 26, "align": "center"},
                {"type": "text", "field": "event_title", "font_size": 10, "align": "center", "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "event_title", "font_size": 10, "align": "center", "max_lines": 2}],
            "footer": {**wf, "height": 16},
        },
    }


def _question() -> dict[str, dict]:
    return _generic_centered("question", "noto_serif_regular", "QUESTION")


def _challenge() -> dict[str, dict]:
    return _generic_centered("challenge", "noto_serif_regular", "CHALLENGE")


def _story() -> dict[str, dict]:
    wf = {"label": "STORY"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 14, "align": "center"},
                {"type": "text", "field": "opening", "font_size": 11, "align": "left", "margin_x": 12, "max_lines": 3},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 12, "align": "center"},
                {"type": "text", "field": "opening", "font_size": 10, "align": "left", "margin_x": 10, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 11, "align": "center", "max_lines": 2},
                {"type": "text", "field": "twist", "font_size": 9, "align": "left", "margin_x": 8, "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 10, "align": "center", "max_lines": 2}],
            "footer": {**wf, "height": 16},
        },
    }


def _almanac() -> dict[str, dict]:
    wf = {"label": "ALMANAC"}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "lunar_date", "font_size": 11, "align": "center"},
                {"type": "text", "field": "solar_term", "font_size": 13, "align": "center"},
                {"type": "text", "field": "health_tip", "font_size": 10, "align": "left", "margin_x": 12, "max_lines": 2},
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {"type": "text", "field": "solar_term", "font_size": 12, "align": "center"},
                {"type": "text", "field": "health_tip", "font_size": 10, "align": "left", "margin_x": 10, "max_lines": 2},
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {"type": "text", "field": "lunar_date", "font_size": 10, "align": "center"},
                {"type": "text", "field": "health_tip", "font_size": 9, "align": "left", "margin_x": 8, "max_lines": 2},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "health_tip", "font_size": 9, "align": "center", "max_lines": 3}],
            "footer": {**wf, "height": 16},
        },
    }


def _poetry() -> dict[str, dict]:
    wf = {"label": "??", "attribution_template": "— {author}", "dashed": True}
    return {
        "slot_lg": {
            "body": [
                {"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 12, "align": "center"},
                {
                    "type": "list",
                    "field": "lines",
                    "max_items": 5,
                    "item_template": "{_value}",
                    "font": "noto_serif_regular",
                    "font_size": 13,
                    "item_spacing": 14,
                    "margin_x": 16,
                    "align": "center",
                },
            ],
            "footer": wf,
        },
        "slot_md": {
            "body": [
                {
                    "type": "list",
                    "field": "lines",
                    "max_items": 4,
                    "item_template": "{_value}",
                    "font": "noto_serif_regular",
                    "font_size": 11,
                    "item_spacing": 12,
                    "margin_x": 12,
                    "align": "center",
                }
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body": [
                {
                    "type": "list",
                    "field": "lines",
                    "max_items": 3,
                    "item_template": "{_value}",
                    "font": "noto_serif_regular",
                    "font_size": 10,
                    "item_spacing": 10,
                    "margin_x": 8,
                    "align": "center",
                }
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body": [{"type": "text", "field": "title", "font": "noto_serif_bold", "font_size": 10, "align": "center", "max_lines": 2}],
            "footer": {**wf, "height": 16},
        },
    }


PRESETS.update(
    {
        "ROAST": _roast(),
        "MY_QUOTE": _my_quote(),
        "LETTER": _letter(),
        "BIAS": _bias(),
        "RIDDLE": _riddle(),
        "RECIPE": _recipe(),
        "THISDAY": _thisday(),
        "QUESTION": _question(),
        "CHALLENGE": _challenge(),
        "STORY": _story(),
        "ALMANAC": _almanac(),
        "POETRY": _poetry(),
    }
)


def _fitness() -> dict[str, dict]:
    wf = {"label": "FITNESS", "attribution_template": "Stay Healthy"}
    return {
        "slot_lg": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "workout_name", "font_size": 13, "align": "center", "max_lines": 2, "margin_x": 12},
                {"type": "text", "field": "duration", "font_size": 11, "align": "center", "max_lines": 1, "margin_x": 12},
                {"type": "spacer", "height": 4},
                {
                    "type": "list",
                    "field": "exercises",
                    "max_items": 4,
                    "item_template": "{name} · {reps}",
                    "font_size": 10,
                    "item_spacing": 10,
                    "margin_x": 12,
                },
            ],
            "footer": wf,
        },
        "slot_md": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "workout_name", "font_size": 12, "align": "center", "max_lines": 1, "margin_x": 10},
                {
                    "type": "list",
                    "field": "exercises",
                    "max_items": 3,
                    "item_template": "{name}",
                    "font_size": 10,
                    "item_spacing": 8,
                    "margin_x": 10,
                },
            ],
            "footer": {**wf, "height": 22},
        },
        "slot_sm": {
            "body_align": "top",
            "body": [
                {"type": "text", "field": "workout_name", "font_size": 11, "align": "center", "max_lines": 2, "margin_x": 8},
                {"type": "text", "field": "tip", "font_size": 9, "align": "left", "max_lines": 3, "margin_x": 8},
            ],
            "footer": {**wf, "height": 18},
        },
        "slot_xs": {
            "body_align": "center",
            "body": [
                {"type": "text", "field": "workout_name", "font_size": 10, "align": "center", "max_lines": 2, "margin_x": 6},
                {"type": "text", "field": "duration", "font_size": 9, "align": "center", "max_lines": 1, "margin_x": 6},
            ],
            "footer": {**wf, "height": 16},
        },
    }


PRESETS["FITNESS"] = _fitness()


def merge_tiers(data: dict, tiers: dict[str, dict]) -> bool:
    lo = data.setdefault("layout_overrides", {})
    if not isinstance(lo, dict):
        lo = {}
        data["layout_overrides"] = lo
    changed = False
    for k, v in tiers.items():
        if k not in TIER_KEYS:
            continue
        if k not in lo:
            lo[k] = v
            changed = True
    return changed


def main() -> int:
    if not BUILTIN.is_dir():
        print("Builtin modes dir not found", file=sys.stderr)
        return 1

    for path in sorted(BUILTIN.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        mid = str(data.get("mode_id", "")).upper()
        if not mid or mid not in PRESETS:
            print(f"skip (no preset): {path.name}")
            continue
        if merge_tiers(data, PRESETS[mid]):
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"updated: {path.name}")
        else:
            print(f"unchanged: {path.name}")

    for path in sorted(EN.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        mid = str(data.get("mode_id", "")).upper()
        if not mid or mid not in PRESETS:
            continue
        if merge_tiers(data, PRESETS[mid]):
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"updated en: {path.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
