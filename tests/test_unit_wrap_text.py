"""Unit tests for wrap_text (Latin word wrap vs CJK character wrap)."""

from core.patterns.utils import load_font, wrap_text


def test_wrap_text_latin_respects_word_boundaries():
    f = load_font("noto_serif_regular", 14)
    text = "Waste no more time arguing what a good man should be. Be one."
    lines = wrap_text(text, f, 120)
    blob = "\n".join(lines)
    assert "w hat" not in blob
    assert "B e" not in blob


def test_wrap_text_cjk_uses_character_fitting():
    f = load_font("noto_serif_regular", 14)
    text = "墨水屏"
    lines = wrap_text(text, f, 8)
    assert len(lines) >= 1
    assert "".join(lines) == text.replace("\n", "")
