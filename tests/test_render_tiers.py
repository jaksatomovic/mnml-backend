"""Tests for slot tier classification and layout merge."""

from core.render_tiers import (
    SLOT_SHAPE_FULL,
    SLOT_SHAPE_LARGE,
    SLOT_SHAPE_SMALL,
    SLOT_SHAPE_TALL,
    SLOT_SHAPE_WIDE,
    SLOT_TIER_FULL,
    SLOT_TIER_MD,
    SLOT_TIER_SM,
    SLOT_TIER_LG,
    SLOT_TIER_XS,
    classify_slot_shape,
    classify_slot_tier,
    merge_layout_for_screen,
    surface_mosaic_inner_rect,
)


def test_classify_full_canvas():
    assert classify_slot_tier(400, 300) == SLOT_TIER_FULL
    assert classify_slot_tier(390, 290) == SLOT_TIER_FULL


def test_classify_slot_shape_mosaic():
    assert classify_slot_shape(400, 300) is None
    assert classify_slot_shape(380, 77) == SLOT_SHAPE_WIDE
    assert classify_slot_shape(222, 140) == SLOT_SHAPE_LARGE
    assert classify_slot_shape(145, 68) == SLOT_SHAPE_SMALL
    assert classify_slot_shape(80, 180) == SLOT_SHAPE_TALL


def test_merge_layout_prefers_shape_variants_over_tier():
    base = {"body": [{"type": "text", "field": "base"}]}
    overrides = {"slot_md": {"body": [{"type": "text", "field": "tier"}]}}
    variants = {"WIDE": {"body": [{"type": "text", "field": "wide_shape"}]}}
    out = merge_layout_for_screen(
        base,
        overrides,
        screen_w=380,
        screen_h=77,
        shape_variants=variants,
    )
    assert out["body"] == [{"type": "text", "field": "wide_shape"}]


def test_surface_mosaic_inner_rect_below_status_above_footer():
    x0, y0, x1, y1 = surface_mosaic_inner_rect(400, 300)
    assert x0 > 0 and x1 < 400
    # Status band ~11% → tiles start below ~33px; footer band ~10% → y1 ~270
    assert y0 >= 30
    assert y1 <= 280
    assert y1 > y0 + 50


def test_classify_mosaic_tiles():
    assert classify_slot_tier(220, 170) == SLOT_TIER_LG
    assert classify_slot_tier(392, 102) == SLOT_TIER_MD
    assert classify_slot_tier(145, 81) == SLOT_TIER_SM
    # Work-surface strips (~70px tall) map to SM, not XS
    assert classify_slot_tier(152, 71) == SLOT_TIER_SM
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


def test_full_slot_type_uses_layout_overrides_full_like_standalone():
    """FULL surface cells are not 400×300 but must merge ``layout_overrides["full"]`` like legacy."""
    base = {"body": [{"type": "text", "field": "base"}]}
    overrides = {
        "full": {"body": [{"type": "text", "field": "from_full"}]},
        "slot_lg": {"body": [{"type": "text", "field": "from_lg"}]},
    }
    out = merge_layout_for_screen(
        base,
        overrides,
        screen_w=360,
        screen_h=200,
        slot_type=SLOT_SHAPE_FULL,
    )
    assert out["body"] == [{"type": "text", "field": "from_full"}]


def test_merge_layout_fallback_from_larger_slot_tier():
    """XS tile uses slot_sm/md/lg when slot_xs is absent (avoids full-screen layout in tiny bitmaps)."""
    base = {"body": [{"type": "text", "field": "full_only"}]}
    overrides = {
        "slot_md": {"body": [{"type": "text", "field": "from_md"}], "body_align": "top"},
    }
    out = merge_layout_for_screen(base, overrides, screen_w=96, screen_h=64)
    assert out["body"] == [{"type": "text", "field": "from_md"}]
    assert out.get("body_align") == "top"
