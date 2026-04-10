"""Canvas / slot tier classification for mode rendering (full device vs mosaic slots).

JSON modes can define ``layout_overrides`` under:

- ``full`` — default 400×300 standalone (legacy) look
- ``slot_lg``, ``slot_md``, ``slot_sm``, ``slot_xs`` — mosaic or small preview tiles

Exact pixel keys ``{w}x{h}`` still win over tier keys (see :func:`merge_layout_for_screen`).
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
    if m >= 72:
        return SLOT_TIER_SM
    return SLOT_TIER_XS


def merge_layout_for_screen(
    base_layout: dict,
    layout_overrides: dict | None,
    *,
    screen_w: int,
    screen_h: int,
) -> dict:
    """Merge ``layout`` with tier-based and optional exact-size overrides.

    Precedence (low → high): base layout → tier key → ``{w}x{h}`` exact key.
    """
    merged = dict(base_layout) if isinstance(base_layout, dict) else {}
    if not isinstance(layout_overrides, dict) or not layout_overrides:
        return merged
    tier = classify_slot_tier(screen_w, screen_h)
    tier_ov = layout_overrides.get(tier)
    if isinstance(tier_ov, dict):
        merged = {**merged, **tier_ov}
    size_key = f"{screen_w}x{screen_h}"
    exact_ov = layout_overrides.get(size_key)
    if isinstance(exact_ov, dict):
        merged = {**merged, **exact_ov}
    return merged
