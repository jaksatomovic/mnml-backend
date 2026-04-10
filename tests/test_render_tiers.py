"""Tests for slot tier classification and layout merge."""

from core.render_tiers import (
    SLOT_TIER_FULL,
    SLOT_TIER_MD,
    SLOT_TIER_SM,
    SLOT_TIER_LG,
    SLOT_TIER_XS,
    classify_slot_tier,
    merge_layout_for_screen,
)


def test_classify_full_canvas():
    assert classify_slot_tier(400, 300) == SLOT_TIER_FULL
    assert classify_slot_tier(390, 290) == SLOT_TIER_FULL


def test_classify_mosaic_tiles():
    assert classify_slot_tier(220, 170) == SLOT_TIER_LG
    assert classify_slot_tier(392, 102) == SLOT_TIER_MD
    assert classify_slot_tier(145, 81) == SLOT_TIER_SM
    assert classify_slot_tier(60, 60) == SLOT_TIER_XS


def test_merge_layout_precedence():
    base = {"body": [{"type": "text", "field": "x"}], "footer": {"height": 30}}
    overrides = {
        "slot_md": {"body": [{"type": "centered_text", "field": "quote"}]},
        "200x100": {"footer": {"height": 20}},
    }
    out = merge_layout_for_screen(base, overrides, screen_w=200, screen_h=100)
    assert out["body"] == [{"type": "centered_text", "field": "quote"}]
    assert out["footer"] == {"height": 20}

    # Exact key not present: tier only
    out2 = merge_layout_for_screen(base, overrides, screen_w=180, screen_h=120)
    assert out2["body"] == [{"type": "centered_text", "field": "quote"}]
    assert out2["footer"] == {"height": 30}


def test_merge_full_tier_skips_slot_only_when_full():
    base = {"body": [{"type": "text", "field": "a"}]}
    overrides = {"slot_sm": {"body": [{"type": "text", "field": "tiny"}]}}
    full = merge_layout_for_screen(base, overrides, screen_w=400, screen_h=300)
    assert full["body"] == [{"type": "text", "field": "a"}]
