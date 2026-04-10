from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogText:
    name: str
    tip: str = ""


@dataclass(frozen=True)
class CatalogItem:
    mode_id: str
    category: str  # "core" | "more" | "custom"
    zh: CatalogText
    en: CatalogText


# Single source of truth for builtin mode grouping + UI copy.
# - Builtin (including builtin_json): define here to keep preview/config in sync.
# - Custom modes: generated dynamically by backend and forced into category="custom".
BUILTIN_CATALOG: list[CatalogItem] = [
    # ── Core (recommended) ─────────────────────────────────────
    CatalogItem(
        mode_id="DAILY",
        category="core",
        zh=CatalogText(name="translated", tip="translated、translated、translated"),
        en=CatalogText(name="Daily", tip="A daily digest: quotes, book picks, and fun facts"),
    ),
    CatalogItem(
        mode_id="WEATHER",
        category="core",
        zh=CatalogText(name="weather", tip="translated"),
        en=CatalogText(name="Weather", tip="Current weather and forecast dashboard"),
    ),
    CatalogItem(
        mode_id="ZEN",
        category="core",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Zen", tip="A single character to reflect your mood"),
    ),
    CatalogItem(
        mode_id="BRIEFING",
        category="core",
        zh=CatalogText(name="translated", tip="translated + AI translated"),
        en=CatalogText(name="Briefing", tip="Tech trends + AI insights briefing"),
    ),
    CatalogItem(
        mode_id="STOIC",
        category="core",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Stoic", tip="A daily stoic quote"),
    ),
    CatalogItem(
        mode_id="POETRY",
        category="core",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Poetry", tip="Classical poetry with a short note"),
    ),
    CatalogItem(
        mode_id="ARTWALL",
        category="core",
        zh=CatalogText(name="translated", tip="Get by translated"),
        en=CatalogText(name="Art Wall", tip="Seasonal black & white generative art"),
    ),
    CatalogItem(
        mode_id="ALMANAC",
        category="core",
        zh=CatalogText(name="translated", tip="lunar、translated、translated"),
        en=CatalogText(name="Almanac", tip="Lunar calendar, solar terms, and daily luck"),
    ),
    CatalogItem(
        mode_id="RECIPE",
        category="core",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Recipe", tip="Meal ideas based on time of day"),
    ),
    CatalogItem(
        mode_id="COUNTDOWN",
        category="core",
        zh=CatalogText(name="translated", tip="Importanttranslated/translated"),
        en=CatalogText(name="Countdown", tip="Countdown / count-up for important events"),
    ),
    # ── More (everything else builtin) ─────────────────────────
    CatalogItem(
        mode_id="MEMO",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Memo", tip="Show your custom memo text"),
    ),
    CatalogItem(
        mode_id="HABIT",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Habits", tip="Daily habit progress"),
    ),
    CatalogItem(
        mode_id="ROAST",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Roast", tip="Lighthearted, sarcastic daily roast"),
    ),
    CatalogItem(
        mode_id="FITNESS",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Fitness", tip="At-home workout tips"),
    ),
    CatalogItem(
        mode_id="LETTER",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Letter", tip="A slow letter from another time"),
    ),
    CatalogItem(
        mode_id="THISDAY",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="On This Day", tip="Major events in history today"),
    ),
    CatalogItem(
        mode_id="RIDDLE",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Riddle", tip="Riddles and brain teasers"),
    ),
    CatalogItem(
        mode_id="QUESTION",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Daily Question", tip="A thought-provoking open question"),
    ),
    CatalogItem(
        mode_id="BIAS",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Bias", tip="A cognitive bias or psychological effect"),
    ),
    CatalogItem(
        mode_id="STORY",
        category="more",
        zh=CatalogText(name="translated", tip="translated 30 translated"),
        en=CatalogText(name="Story", tip="A complete micro fiction in three parts"),
    ),
    CatalogItem(
        mode_id="LIFEBAR",
        category="more",
        zh=CatalogText(name="translated", tip="year/month/translated/translated"),
        en=CatalogText(name="Life Bar", tip="Progress bars for year / month / week / life"),
    ),
    CatalogItem(
        mode_id="CHALLENGE",
        category="more",
        zh=CatalogText(name="translated", tip="translated 5 translated"),
        en=CatalogText(name="Challenge", tip="A 5-minute daily micro challenge"),
    ),
    CatalogItem(
        mode_id="WORD_OF_THE_DAY",
        category="more",
        zh=CatalogText(name="translated", tip="translated，translated"),
        en=CatalogText(name="Word of the Day", tip="One English word with a short explanation"),
    ),
    CatalogItem(
        mode_id="MY_QUOTE",
        category="more",
        zh=CatalogText(name="translated", tip="translated，translated"),
        en=CatalogText(name="Custom Quote", tip="Supports custom input or random generation"),
    ),
    CatalogItem(
        mode_id="CALENDAR",
        category="more",
        zh=CatalogText(name="translated", tip="translated，translated"),
        en=CatalogText(name="Calendar", tip="Monthly calendar with lunar dates and festivals"),
    ),
    CatalogItem(
        mode_id="TIMETABLE",
        category="more",
        zh=CatalogText(name="translated", tip="translated"),
        en=CatalogText(name="Timetable", tip="Weekly class schedule display"),
    ),
    CatalogItem(
        mode_id="MY_ADAPTIVE",
        category="custom",
        zh=CatalogText(name="translated", tip="translated，translated"),
        en=CatalogText(name="Photo Frame", tip="Upload a local photo and auto-fit it to the e-ink screen"),
    ),
]


def builtin_catalog_map() -> dict[str, CatalogItem]:
    return {item.mode_id.upper(): item for item in BUILTIN_CATALOG}

