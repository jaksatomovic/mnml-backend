"""
InkSight configuration file
Contains constants, mappings, and configuration items
"""

import logging

logger = logging.getLogger(__name__)

# ==================== Screen configuration ====================
SCREEN_WIDTH = 400   # Default; overridable per-request via w/h query params
SCREEN_HEIGHT = 300  # Default; overridable per-request via w/h query params

# Layout hints (status/footer bands in json_renderer / firmware partial-refresh region).
# Full-frame BMP from /api/render includes status bar + body + footer; w/h are panel size.
DEVICE_STATUS_BAR_HEIGHT_PX = 36
DEVICE_FOOTER_HEIGHT_PX = 30

# translated（1-bit translated）
EINK_BACKGROUND = 1  # white
EINK_FOREGROUND = 0  # black

EINK_4COLOR_PALETTE = [
    0, 0, 0,        # 0: black
    255, 255, 255,   # 1: white
    232, 176, 0,     # 2: yellow (golden, closer to e-ink appearance)
    200, 0, 0,       # 3: red (deeper, closer to e-ink appearance)
]

EINK_COLOR_NAME_MAP = {
    "black": 0,
    "white": 1,
    "yellow": 2,
    "red": 3,
}

EINK_COLOR_AVAILABILITY = {
    2: frozenset(),
    3: frozenset({"red"}),
    4: frozenset({"red", "yellow"}),
}


# ==================== Weather configuration ====================
# WMO (translated) translated → translated
# translated: https://open-meteo.com/en/docs
WEATHER_ICON_MAP = {
    0: "sunny",
    1: "sunny",
    2: "partly_cloudy",
    3: "cloud",
    45: "foggy",
    48: "foggy",
    51: "rainy",
    53: "rainy",
    55: "rainy",
    56: "rainy",
    57: "rainy",
    61: "rainy",
    63: "rainy",
    65: "rainy",
    66: "rainy",
    67: "rainy",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rainy",
    81: "rainy",
    82: "rainy",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


# ==================== Font configuration ====================
FONTS = {
    # translated
    "noto_serif_extralight": "NotoSerifSC-ExtraLight.ttf",
    "noto_serif_light": "NotoSerifSC-Light.ttf",
    "noto_serif_regular": "NotoSerifSC-Regular.ttf",
    "noto_serif_bold": "NotoSerifSC-Bold.ttf",
    # translated
    "lora_regular": "Lora-Regular.ttf",
    "lora_bold": "Lora-Bold.ttf",
    "inter_medium": "Inter_24pt-Medium.ttf",
}


# ==================== Date and time configuration ====================
WEEKDAY_CN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MONTH_CN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "translatedJanuary",
    "translatedFebruary",
]

# solarfestival（month, day）
SOLAR_FESTIVALS = {
    (1, 1): "New Year's Day",
    (2, 14): "Valentine's Day",
    (3, 8): "Women's Day",
    (4, 1): "April Fools' Day",
    (5, 1): "Labor Day",
    (6, 1): "Children's Day",
    (10, 1): "National Day",
    (12, 25): "Christmas",
}

# lunarfestival（month, day）
LUNAR_FESTIVALS = {
    (1, 1): "Spring Festival",
    (1, 15): "Lantern Festival",
    (5, 5): "Dragon Boat Festival",
    (7, 7): "Qixi Festival",
    (8, 15): "Mid-Autumn Festival",
    (9, 9): "Double Ninth Festival",
    (12, 8): "Laba Festival",
}

# translated (year, month, day) -> name
# Pre-computed for 2024-2030; solar terms drift by <=1 day across years.
SOLAR_TERMS: dict[tuple[int, int, int], str] = {}
_SOLAR_TERMS_RAW: dict[int, list[tuple[int, int, str]]] = {
    2024: [
        (1,6,"Minor Cold"),(1,20,"Major Cold"),(2,4,"Start of Spring"),(2,19,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,4,"Clear and Bright"),(4,19,"Grain Rain"),
        (5,5,"Start of Summer"),(5,20,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,6,"Minor Heat"),(7,22,"Major Heat"),(8,7,"Start of Autumn"),(8,22,"End of Heat"),
        (9,7,"White Dew"),(9,22,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,6,"Major Snow"),(12,21,"Winter Solstice"),
    ],
    2025: [
        (1,5,"Minor Cold"),(1,20,"Major Cold"),(2,3,"Start of Spring"),(2,18,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,4,"Clear and Bright"),(4,20,"Grain Rain"),
        (5,5,"Start of Summer"),(5,21,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,7,"Minor Heat"),(7,22,"Major Heat"),(8,7,"Start of Autumn"),(8,23,"End of Heat"),
        (9,7,"White Dew"),(9,22,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,7,"Major Snow"),(12,21,"Winter Solstice"),
    ],
    2026: [
        (1,5,"Minor Cold"),(1,20,"Major Cold"),(2,4,"Start of Spring"),(2,18,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,5,"Clear and Bright"),(4,20,"Grain Rain"),
        (5,5,"Start of Summer"),(5,21,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,7,"Minor Heat"),(7,23,"Major Heat"),(8,7,"Start of Autumn"),(8,23,"End of Heat"),
        (9,7,"White Dew"),(9,23,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,7,"Major Snow"),(12,22,"Winter Solstice"),
    ],
    2027: [
        (1,5,"Minor Cold"),(1,20,"Major Cold"),(2,4,"Start of Spring"),(2,19,"Rain Water"),
        (3,6,"Awakening of Insects"),(3,21,"Spring Equinox"),(4,5,"Clear and Bright"),(4,20,"Grain Rain"),
        (5,6,"Start of Summer"),(5,21,"Grain Full"),(6,6,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,7,"Minor Heat"),(7,23,"Major Heat"),(8,7,"Start of Autumn"),(8,23,"End of Heat"),
        (9,8,"White Dew"),(9,23,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,7,"Major Snow"),(12,22,"Winter Solstice"),
    ],
    2028: [
        (1,6,"Minor Cold"),(1,21,"Major Cold"),(2,4,"Start of Spring"),(2,19,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,4,"Clear and Bright"),(4,19,"Grain Rain"),
        (5,5,"Start of Summer"),(5,20,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,6,"Minor Heat"),(7,22,"Major Heat"),(8,7,"Start of Autumn"),(8,22,"End of Heat"),
        (9,7,"White Dew"),(9,22,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,6,"Major Snow"),(12,21,"Winter Solstice"),
    ],
    2029: [
        (1,5,"Minor Cold"),(1,20,"Major Cold"),(2,3,"Start of Spring"),(2,18,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,4,"Clear and Bright"),(4,20,"Grain Rain"),
        (5,5,"Start of Summer"),(5,21,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,7,"Minor Heat"),(7,22,"Major Heat"),(8,7,"Start of Autumn"),(8,23,"End of Heat"),
        (9,7,"White Dew"),(9,22,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,7,"Major Snow"),(12,21,"Winter Solstice"),
    ],
    2030: [
        (1,5,"Minor Cold"),(1,20,"Major Cold"),(2,4,"Start of Spring"),(2,18,"Rain Water"),
        (3,5,"Awakening of Insects"),(3,20,"Spring Equinox"),(4,5,"Clear and Bright"),(4,20,"Grain Rain"),
        (5,5,"Start of Summer"),(5,21,"Grain Full"),(6,5,"Grain in Ear"),(6,21,"Summer Solstice"),
        (7,7,"Minor Heat"),(7,22,"Major Heat"),(8,7,"Start of Autumn"),(8,23,"End of Heat"),
        (9,7,"White Dew"),(9,23,"Autumn Equinox"),(10,8,"Cold Dew"),(10,23,"Frost Descent"),
        (11,7,"Start of Winter"),(11,22,"Minor Snow"),(12,7,"Major Snow"),(12,22,"Winter Solstice"),
    ],
}
for _yr, _terms in _SOLAR_TERMS_RAW.items():
    for _m, _d, _name in _terms:
        SOLAR_TERMS[(_yr, _m, _d)] = _name


# ==================== Literary phrases ====================
IDIOMS = [
    "Time flies in a day",
    "Gentle spring rain",
    "Crisp autumn air",
    "Warm winter sun",
    "Scorching summer",
    "Morning flowers at dusk",
    "Years pass quickly",
    "Time slips by",
    "Like a fleeting horse",
    "Time flies like an arrow",
    "Morning bells, evening drums",
    "Changing every day",
    "Stars shift with time",
    "Seasons come and go",
    "Flowers bloom and fade",
    "Clouds gather and drift",
    "Tides rise and fall",
    "Moon waxes and wanes",
    "Winds and clouds surge",
    "Clear sky after rain",
]

POEMS = [
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated",
    "translated，translated，translated",
]


# ==================== translated ====================
DEFAULT_LATITUDE = 45.81
DEFAULT_LONGITUDE = 15.98

CITY_COORDINATES = {
    "Beijing": (39.90, 116.40),
    "Shanghai": (31.23, 121.47),
    "Guangzhou": (23.13, 113.26),
    "Shenzhen": (22.54, 114.06),
    "Hangzhou": (30.27, 120.15),
    "Nanjing": (32.06, 118.80),
    "Chengdu": (30.57, 104.07),
    "Chongqing": (29.56, 106.55),
    "Wuhan": (30.59, 114.31),
    "Xi'an": (34.26, 108.94),
    "Suzhou": (31.30, 120.62),
    "Tianjin": (39.13, 117.20),
    "Changsha": (28.23, 112.94),
    "Zhengzhou": (34.75, 113.65),
    "Qingdao": (36.07, 120.38),
    "Dalian": (38.91, 121.60),
    "Xiamen": (24.48, 118.09),
    "Kunming": (25.04, 102.68),
    "Hefei": (31.82, 117.23),
    "Fuzhou": (26.07, 119.30),
    "Harbin": (45.75, 126.65),
    "Shenyang": (41.80, 123.43),
    "Jinan": (36.65, 116.99),
    "Shijiazhuang": (38.04, 114.51),
    "Changchun": (43.88, 125.32),
    "Nanchang": (28.68, 115.86),
    "Guiyang": (26.65, 106.63),
    "Nanning": (22.82, 108.32),
    "Taiyuan": (37.87, 112.55),
    "Lanzhou": (36.06, 103.83),
    "Haikou": (20.04, 110.35),
    "Yinchuan": (38.49, 106.23),
    "Xining": (36.62, 101.78),
    "Hohhot": (40.84, 111.75),
    "Urumqi": (43.83, 87.62),
    "Lhasa": (29.65, 91.13),
    "Hong Kong": (22.32, 114.17),
    "Macau": (22.20, 113.55),
    "Taipei": (25.03, 121.57),
    "Tokyo": (35.68, 139.69),
    "Seoul": (37.57, 126.98),
    "Singapore": (1.35, 103.82),
    "New York": (40.71, -74.01),
    "London": (51.51, -0.13),
    "Paris": (48.86, 2.35),
    "Sydney": (-33.87, 151.21),
    "Vancouver": (49.28, -123.12),
    "San Francisco": (37.77, -122.42),
    "Zagreb": (45.81, 15.98),
}


# ==================== API config ====================
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
HOLIDAY_WORK_API_URL = "https://date.appworlds.cn/work"
HOLIDAY_NEXT_API_URL = "https://date.appworlds.cn/next"


# ==================== translated ====================
# DAILY modetranslated
DAILY_LAYOUT = {
    "left_column_width": 116,
    "gaps": {
        "year_to_day": 2,
        "day_to_month": 24,
        "month_to_weekday": 2,
        "weekday_to_progress": 10,
        "bar_to_text": 3,
    },
    "progress_bar_width": 80,
    "right_column_padding": 14,
}

# translated (translated + translated Python modetranslated)
# STOIC/ROAST/ZEN/FITNESS/POETRY translated JSON，Font configurationtranslated modes/builtin/*.json translated
FONT_SIZES = {
    "status_bar": {"cn": 11, "en": 11},
    "footer": {"label": 10, "attribution": 12},
    "daily": {
        "year": 12,
        "day": 53,
        "month": 14,
        "weekday": 12,
        "progress": 10,
        "section_title": 11,
        "quote": 14,
        "author": 12,
        "book_title": 14,
        "book_info": 12,
        "tip": 12,
    },
}

# translated
ICON_SIZES = {
    "weather": (16, 16),
    "mode": (12, 12),
}


# ==================== translateddefaulttranslated ====================
DEFAULT_CITY = "Zagreb"
DEFAULT_LLM_PROVIDER = "deepseek"
DEFAULT_LLM_MODEL = "deepseek-chat"
DEFAULT_IMAGE_PROVIDER = "deepseek"
DEFAULT_IMAGE_MODEL = ""
DEFAULT_LANGUAGE = "en"
DEFAULT_MODE_LANGUAGE = ""  # empty = follow webapp language setting
DEFAULT_CONTENT_TONE = "neutral"
DEFAULT_MODES = ["STOIC"]
DEFAULT_REFRESH_STRATEGY = "random"
DEFAULT_REFRESH_INTERVAL = 60  # minutes

# translatedmodetranslated fallback，translated mode_registry Get 
_BUILTIN_MODE_IDS = {
    "STOIC", "ROAST", "ZEN", "DAILY",
    "BRIEFING", "ARTWALL", "RECIPE", "FITNESS",
    "POETRY", "COUNTDOWN",
    "ALMANAC", "LETTER", "THISDAY", "RIDDLE",
    "QUESTION", "BIAS", "STORY", "LIFEBAR", "CHALLENGE",
}


def get_supported_modes() -> set[str]:
    """Get all supported mode IDs from the registry (with fallback)."""
    try:
        from .mode_registry import get_registry
        return get_registry().get_supported_ids()
    except (ImportError, AttributeError, RuntimeError):
        logger.warning("[Config] Falling back to builtin supported modes", exc_info=True)
        return _BUILTIN_MODE_IDS


def get_cacheable_modes() -> set[str]:
    """Get cacheable mode IDs from the registry (with fallback)."""
    try:
        from .mode_registry import get_registry
        return get_registry().get_cacheable_ids()
    except (ImportError, AttributeError, RuntimeError):
        logger.warning("[Config] Falling back to builtin cacheable modes", exc_info=True)
        return {"STOIC", "ROAST", "ZEN", "DAILY"}


from typing import Optional


def get_default_llm_model_for_provider(provider: Optional[str]) -> str:
    """Get by translateddefaulttranslated。

    - DeepSeek：default deepseek-chat
    - OpenAI：default gpt-4o-mini
    - translated/translated：translated DEFAULT_LLM_MODEL
    """
    p = (provider or "").strip().lower() or DEFAULT_LLM_PROVIDER
    if p == "deepseek":
        return "deepseek-chat"
    if p == "openai":
        return "gpt-4o-mini"
    return DEFAULT_LLM_MODEL
