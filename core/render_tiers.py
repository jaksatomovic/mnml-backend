"""Canvas / slot tier classification for mode rendering (full device vs mosaic slots).

JSON modes can define:

- ``layout_overrides`` — ``full`` (standalone), ``slot_lg`` … ``slot_xs`` (pixel-bucket tiers),
  and exact ``{w}x{h}`` keys.
- ``variants`` — **slot-shape** layouts: ``SMALL``, ``WIDE``, ``TALL``, ``FULL`` (iOS-style
  widget families). When a shape variant matches the render size, it is used **instead of**
  tier-based ``slot_*`` overrides (see :func:`merge_layout_for_screen`).

Exact pixel keys ``{w}x{h}`` still win over everything else.
"""

from __future__ import annotations

from .config import SCREEN_HEIGHT, SCREEN_WIDTH

SLOT_TIER_FULL = "full"
SLOT_TIER_LG = "slot_lg"
SLOT_TIER_MD = "slot_md"
SLOT_TIER_SM = "slot_sm"
SLOT_TIER_XS = "slot_xs"

SLOT_TIER_KEYS = frozenset(
    {
        SLOT_TIER_FULL,
        SLOT_TIER_LG,
        SLOT_TIER_MD,
        SLOT_TIER_SM,
        SLOT_TIER_XS,
    },
)

# When a tier key is missing in layout_overrides, merge the first present definition
# from this chain (narrower tiles inherit from roomier layouts).
_SLOT_TIER_FALLBACK: dict[str, tuple[str, ...]] = {
    SLOT_TIER_XS: (SLOT_TIER_XS, SLOT_TIER_SM, SLOT_TIER_MD, SLOT_TIER_LG),
    SLOT_TIER_SM: (SLOT_TIER_SM, SLOT_TIER_MD, SLOT_TIER_LG),
    SLOT_TIER_MD: (SLOT_TIER_MD, SLOT_TIER_LG),
    SLOT_TIER_LG: (SLOT_TIER_LG,),
}

# Slot family by geometry (mosaic / widget shape), not only pixel area.
SLOT_SHAPE_SMALL = "SMALL"
SLOT_SHAPE_WIDE = "WIDE"
SLOT_SHAPE_TALL = "TALL"
SLOT_SHAPE_LARGE = "LARGE"
SLOT_SHAPE_FULL = "FULL"

# Strict variant fallback when ``slot_type`` is known from the grid (spec):
# SMALL never falls back to FULL; WIDE/TALL may fall back to FULL for simplified layouts.
_STRICT_SLOT_TYPE_VARIANT_FALLBACK: dict[str, tuple[str, ...]] = {
    SLOT_SHAPE_SMALL: (SLOT_SHAPE_SMALL,),
    SLOT_SHAPE_WIDE: (SLOT_SHAPE_WIDE, SLOT_SHAPE_FULL),
    SLOT_SHAPE_TALL: (SLOT_SHAPE_TALL, SLOT_SHAPE_FULL),
    SLOT_SHAPE_FULL: (SLOT_SHAPE_FULL,),
}

# Legacy: infer shape from pixels when ``slot_type`` is not passed (standalone / old surfaces).
# ``SLOT_SHAPE_LARGE`` is still returned by :func:`classify_slot_shape` for squarish tiles; variant keys use ``FULL``.
_GEOMETRY_SHAPE_VARIANT_FALLBACK: dict[str, tuple[str, ...]] = {
    SLOT_SHAPE_SMALL: (SLOT_SHAPE_SMALL, SLOT_SHAPE_TALL, SLOT_SHAPE_WIDE),
    SLOT_SHAPE_WIDE: (SLOT_SHAPE_WIDE, SLOT_SHAPE_FULL, SLOT_SHAPE_TALL),
    SLOT_SHAPE_TALL: (SLOT_SHAPE_TALL, SLOT_SHAPE_FULL, SLOT_SHAPE_SMALL),
    SLOT_SHAPE_LARGE: (SLOT_SHAPE_FULL, SLOT_SHAPE_WIDE, SLOT_SHAPE_TALL, SLOT_SHAPE_SMALL),
}


def surface_mosaic_inner_rect(screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
    """Pixel rect ``(x0, y0, x1, y1)`` for pasting surface tiles between global chrome.

    Uses a compact top inset (status bar only) and extends close to the bottom edge
    because surface tiles now draw their own local footer chrome.
    ``y1`` is exclusive (tile rows use ``y < y1``).
    """
    w = max(1, int(screen_w))
    h = max(1, int(screen_h))
    status_line_y = int(h * 0.11)
    # Match status bar horizontal insets exactly:
    # - left starts at date text x
    # - right ends where battery percentage text ends
    pad_pct = 0.02 if h < 200 else 0.03
    pad_x = int(w * pad_pct)
    # Surface tiles keep a small vertical inset:
    # - top inset (below top bar) is half horizontal padding
    # - bottom inset matches left/right edge padding
    top_pad = max(1, pad_x // 4)
    y0 = status_line_y + top_pad
    y1 = h - pad_x
    x0 = pad_x
    x1 = w - pad_x
    if y1 <= y0 + 16:
        y0 = max(0, h // 10)
        y1 = max(y0 + 24, (h * 9) // 10)
    return (x0, y0, x1, y1)


def classify_slot_tier(screen_w: int, screen_h: int) -> str:
    """Bucket the render target for layout / prompt selection.

    Thresholds are tuned for 400×300 surfaces: large tiles (~half panel), medium
    strips, and minimum tile sizes used in surface preview (~96×72).
    """
    w = max(1, int(screen_w))
    h = max(1, int(screen_h))
    # Standalone mode on the default canvas (legacy full-screen look)
    if w >= SCREEN_WIDTH - 24 and h >= SCREEN_HEIGHT - 24:
        return SLOT_TIER_FULL
    m = min(w, h)
    if m >= 150:
        return SLOT_TIER_LG
    if m >= 100:
        return SLOT_TIER_MD
    # Short strips in work/home mosaics are often ~70px tall; treat as SM so layouts apply
    if m >= 68:
        return SLOT_TIER_SM
    return SLOT_TIER_XS


def classify_slot_shape(screen_w: int, screen_h: int) -> str | None:
    """Classify widget slot by **shape** for ``variants`` (SMALL / WIDE / TALL / LARGE).

    Returns ``None`` on the default full device canvas (use base + ``layout_overrides["full"]``).
    """
    w, h = max(1, int(screen_w)), max(1, int(screen_h))
    if w >= SCREEN_WIDTH - 24 and h >= SCREEN_HEIGHT - 24:
        return None
    m = min(w, h)
    M = max(w, h)
    R = M / m
    ar_wh = w / h

    # Full-width horizontal strips (bottom weather row) — before "small pocket" so
    # ~380×77 is WIDE, not SMALL.
    if ar_wh >= 2.4 and w >= 160 and h <= 92:
        return SLOT_SHAPE_WIDE
    # Tall narrow column
    if ar_wh <= 0.52 and w <= max(96, h // 4):
        return SLOT_SHAPE_TALL

    if m < 78:
        return SLOT_SHAPE_SMALL

    # Large squarish panel (~2×2 grid cell)
    if m >= 108 and R <= 1.75:
        return SLOT_SHAPE_LARGE

    if ar_wh >= 1.35:
        return SLOT_SHAPE_WIDE
    if ar_wh <= 0.75:
        return SLOT_SHAPE_TALL

    return SLOT_SHAPE_SMALL


def _get_shape_variant_block(variants: dict, shape_key: str) -> dict | None:
    for k in (shape_key, shape_key.upper(), shape_key.lower()):
        block = variants.get(k)
        if isinstance(block, dict) and block:
            return block
    return None


def merge_shape_variant_layout(
    shape_variants: dict | None,
    screen_w: int,
    screen_h: int,
    *,
    slot_type: str | None = None,
) -> dict | None:
    """Return the first matching layout dict from ``variants``, or ``None``.

    When ``slot_type`` is set (grid cell type), use strict fallback rules only.
    Otherwise classify by pixel geometry (legacy).
    """
    if not isinstance(shape_variants, dict) or not shape_variants:
        return None
    st = str(slot_type or "").strip().upper()
    # CUSTOM rectangles: pick variant by pixel geometry (same as legacy path).
    if st == "CUSTOM":
        st = ""
    if st:
        chain = _STRICT_SLOT_TYPE_VARIANT_FALLBACK.get(st, (st,))
        for key in chain:
            block = _get_shape_variant_block(shape_variants, key)
            if block is not None:
                return block
        return None
    shape = classify_slot_shape(screen_w, screen_h)
    if shape is None:
        return None
    for key in _GEOMETRY_SHAPE_VARIANT_FALLBACK.get(shape, (shape,)):
        block = _get_shape_variant_block(shape_variants, key)
        if block is not None:
            return block
    return None


def _merge_tier_layout_overrides(
    merged: dict,
    layout_overrides: dict | None,
    screen_w: int,
    screen_h: int,
    *,
    slot_type: str | None = None,
) -> dict:
    """Apply ``slot_*`` / ``full`` entries from ``layout_overrides``."""
    if not isinstance(layout_overrides, dict) or not layout_overrides:
        return merged
    out = dict(merged)
    tier = classify_slot_tier(screen_w, screen_h)
    # FULL grid cells use nearly the whole mosaic but not 400×300; still apply the same
    # ``layout_overrides["full"]`` as legacy standalone so visuals match.
    if str(slot_type or "").strip().upper() == SLOT_SHAPE_FULL:
        tier = SLOT_TIER_FULL
    if tier != SLOT_TIER_FULL:
        for key in _SLOT_TIER_FALLBACK.get(tier, ()):
            tier_ov = layout_overrides.get(key)
            if isinstance(tier_ov, dict):
                out = {**out, **tier_ov}
                break
    else:
        tier_ov = layout_overrides.get(tier)
        if isinstance(tier_ov, dict):
            out = {**out, **tier_ov}
    return out


def merge_layout_for_screen(
    base_layout: dict,
    layout_overrides: dict | None,
    *,
    screen_w: int,
    screen_h: int,
    shape_variants: dict | None = None,
    slot_type: str | None = None,
) -> dict:
    """Merge layout for the target bitmap size.

    Precedence (low → high):

    - Base ``layout``
    - If ``variants`` defines a matching slot shape → that variant (**replaces** tier
      ``slot_*`` overrides for body/footer keys present in the variant)
    - Else → ``layout_overrides`` tier merge (``slot_lg`` … with fallback chain)
    - Always last → exact ``{w}x{h}`` key in ``layout_overrides``

    ``slot_type`` (``SMALL`` / ``WIDE`` / …) should be set when rendering a surface grid cell
    so variants match the spec; otherwise pixel geometry is used.
    """
    merged = dict(base_layout) if isinstance(base_layout, dict) else {}
    shape_layout = merge_shape_variant_layout(
        shape_variants, screen_w, screen_h, slot_type=slot_type
    )
    if shape_layout:
        merged = {**merged, **shape_layout}
    else:
        merged = _merge_tier_layout_overrides(
            merged, layout_overrides, screen_w, screen_h, slot_type=slot_type
        )

    if isinstance(layout_overrides, dict):
        size_key = f"{screen_w}x{screen_h}"
        exact_ov = layout_overrides.get(size_key)
        if isinstance(exact_ov, dict):
            merged = {**merged, **exact_ov}
    return merged
