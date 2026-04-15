"""Fixed grid layout for Surface mode (MVP default: 2×2 columns×rows).

Slots use cell coordinates ``(x, y)`` and span ``(w, h)`` in **grid cells**.

``slot_type`` spans (must match ``w`` × ``h`` unless noted):

- ``SMALL`` — 1×1
- ``WIDE`` — 2×1
- ``TALL`` — 1×2
- ``FULL`` — entire grid (``w`` = columns, ``h`` = rows), or the former ``LARGE`` 2×2 on a 2×2 grid
- ``CUSTOM`` — any other in-bounds rectangle (e.g. 2×2 on a 3×3 grid; variants use pixel geometry)
"""

from __future__ import annotations

from typing import Any, Callable

# Default MVP grid (override per surface via ``grid``)
DEFAULT_GRID_COLUMNS = 2
DEFAULT_GRID_ROWS = 2
DEFAULT_GRID_GAP_PX = 6
DEFAULT_GRID_PADDING_PX = 8

# Layout builder: discrete grid limits (surfaces may still store other sizes for legacy data)
MIN_GRID_COLUMNS = 2
MAX_GRID_COLUMNS = 4
MIN_GRID_ROWS = 2
MAX_GRID_ROWS = 6
MAX_SURFACE_SLOTS = 6

# Fixed slot types (excluding FULL — depends on grid size; CUSTOM is any in-bounds rectangle)
SLOT_TYPE_SPAN: dict[str, tuple[int, int]] = {
    "SMALL": (1, 1),
    "WIDE": (2, 1),
    "TALL": (1, 2),
}

KNOWN_SLOT_TYPES = frozenset({"SMALL", "WIDE", "TALL", "FULL", "CUSTOM"})


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def parse_surface_grid(surface: dict[str, Any] | None) -> tuple[dict[str, int], list[dict[str, Any]]] | tuple[None, None]:
    """Return ``(grid_spec, slots)`` if the surface uses grid layout, else ``(None, None)``."""
    if not isinstance(surface, dict):
        return None, None
    grid = surface.get("grid")
    slots = surface.get("slots")
    if not isinstance(grid, dict) or not isinstance(slots, list) or len(slots) == 0:
        return None, None
    return grid, [s for s in slots if isinstance(s, dict)]


def grid_dimensions(grid: dict[str, Any]) -> tuple[int, int, int, int]:
    cols = max(1, _as_int(grid.get("columns"), DEFAULT_GRID_COLUMNS))
    rows = max(1, _as_int(grid.get("rows"), DEFAULT_GRID_ROWS))
    gap = max(0, _as_int(grid.get("gap"), DEFAULT_GRID_GAP_PX))
    pad = max(0, _as_int(grid.get("padding"), DEFAULT_GRID_PADDING_PX))
    return cols, rows, gap, pad


def infer_slot_type_from_span(w: int, h: int) -> str:
    """Map cell span to the canonical type name without grid context; non-standard spans → ``CUSTOM``.

    A 2×2 block is ``CUSTOM`` here; use :func:`expected_slot_type_for_span` with grid size to get ``FULL``.
    """
    if w == 1 and h == 1:
        return "SMALL"
    if w == 2 and h == 1:
        return "WIDE"
    if w == 1 and h == 2:
        return "TALL"
    return "CUSTOM"


def expected_slot_type_for_span(w: int, h: int, columns: int, rows: int) -> str:
    """Derive the only valid ``slot_type`` for a rectangle (strict layout builder / API).

    ``FULL`` means the slot covers the entire grid. Other standard rectangles use SMALL/WIDE/TALL;
    everything else (including 2×2 on a grid larger than 2×2) is ``CUSTOM``.
    """
    if w == columns and h == rows:
        return "FULL"
    if w == 1 and h == 1:
        return "SMALL"
    if w == 2 and h == 1:
        return "WIDE"
    if w == 1 and h == 2:
        return "TALL"
    return "CUSTOM"


def normalize_legacy_slot_type(st: str, w: int, h: int, columns: int, rows: int) -> str:
    """Map deprecated ``LARGE`` to ``FULL`` or ``CUSTOM`` (same span rules as today)."""
    u = (st or "").strip().upper()
    if u == "LARGE":
        return expected_slot_type_for_span(w, h, columns, rows)
    return u


def validate_slot_type_matches_span(
    slot_type: str, w: int, h: int, *, columns: int, rows: int
) -> bool:
    st = (slot_type or "").strip().upper()
    if st == "FULL":
        return w == columns and h == rows
    if st == "CUSTOM":
        return w >= 1 and h >= 1 and w <= columns and h <= rows
    if st not in SLOT_TYPE_SPAN:
        return False
    ew, eh = SLOT_TYPE_SPAN[st]
    return (ew, eh) == (w, h)


def validate_slots_for_grid(
    slots: list[dict[str, Any]],
    *,
    columns: int,
    rows: int,
) -> tuple[bool, str]:
    """Return ``(ok, error_message)``. Checks bounds, overlap, and span vs ``slot_type``."""
    occ: list[list[bool]] = [[False] * columns for _ in range(rows)]
    for raw in slots:
        x = _as_int(raw.get("x"), -1)
        y = _as_int(raw.get("y"), -1)
        w = _as_int(raw.get("w"), 0)
        h = _as_int(raw.get("h"), 0)
        st = normalize_legacy_slot_type(str(raw.get("slot_type") or ""), w, h, columns, rows).strip().upper()
        if x < 0 or y < 0 or w < 1 or h < 1:
            return False, "invalid slot x/y/w/h"
        if x + w > columns or y + h > rows:
            return False, f"slot {raw.get('id')} out of grid bounds"
        if st:
            if not validate_slot_type_matches_span(st, w, h, columns=columns, rows=rows):
                if st == "FULL":
                    return False, f"slot {raw.get('id')}: FULL must span entire grid ({columns}×{rows})"
                return False, f"slot {raw.get('id')} span {w}×{h} does not match slot_type {st}"
        for ry in range(y, y + h):
            for rx in range(x, x + w):
                if occ[ry][rx]:
                    return False, f"overlapping slots at cell ({rx},{ry})"
                occ[ry][rx] = True
    return True, ""


def _mode_catalog_lookup(modes: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in modes or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or m.get("mode_id") or "").strip().upper()
        if not mid:
            continue
        sst = m.get("supported_slot_types")
        types: list[str] | None = None
        if isinstance(sst, list):
            types = [str(x).strip().upper() for x in sst if isinstance(x, str) and str(x).strip()]
        out[mid] = {
            "name": str(m.get("name") or m.get("display_name") or mid),
            "supported_slot_types": types,
        }
    return out


def mode_definition_supports_expected_type(defn: dict | None, expected: str) -> bool:
    """Strict API check: ``expected`` must appear in ``supported_slot_types`` (no inferred CUSTOM fallbacks)."""
    if not defn or not isinstance(defn, dict):
        return False
    allowed = defn.get("supported_slot_types")
    if not isinstance(allowed, list) or len(allowed) == 0:
        return True
    exp = (expected or "").strip().upper()
    if exp == "LARGE":
        exp = "FULL"
    norm = {str(x).strip().upper() for x in allowed if isinstance(x, str)}
    if "LARGE" in norm:
        norm = norm | {"FULL"}
        norm.discard("LARGE")
    return exp in norm


def validate_layout(
    layout: Any,
    modes: list[dict[str, Any]] | None = None,
    *,
    get_mode_definition: Callable[[str], dict | None] | None = None,
) -> dict[str, Any]:
    """Source-of-truth layout validation (grid editor + API contract).

    ``modes`` (optional): list of ``{ "id"|"mode_id", "name", "supported_slot_types": [...] }``.
    When provided, mode existence and compatibility use this list only.
    When omitted, ``get_mode_definition`` resolves JSON mode definitions from the registry.

    Returns ``{"valid": bool, "errors": [{"code", "message", "slot_id"?}]}``.
    """
    errors: list[dict[str, Any]] = []

    def _err(code: str, message: str, slot_id: str | None = None) -> None:
        e: dict[str, Any] = {"code": code, "message": message}
        if slot_id:
            e["slot_id"] = slot_id
        errors.append(e)

    if not isinstance(layout, dict):
        _err("INVALID_LAYOUT", "layout must be an object")
        return {"valid": False, "errors": errors}

    grid = layout.get("grid")
    slots = layout.get("slots")
    if not isinstance(grid, dict):
        _err("INVALID_LAYOUT", "layout.grid must be an object")
        return {"valid": False, "errors": errors}
    if not isinstance(slots, list):
        _err("INVALID_LAYOUT", "layout.slots must be an array")
        return {"valid": False, "errors": errors}

    columns = _as_int(grid.get("columns"), 0)
    rows = _as_int(grid.get("rows"), 0)
    if not (
        MIN_GRID_COLUMNS <= columns <= MAX_GRID_COLUMNS
        and MIN_GRID_ROWS <= rows <= MAX_GRID_ROWS
    ):
        _err(
            "GRID_INVALID",
            (
                f"grid columns must be {MIN_GRID_COLUMNS}-{MAX_GRID_COLUMNS} "
                f"and rows {MIN_GRID_ROWS}-{MAX_GRID_ROWS}"
            ),
        )
        return {"valid": False, "errors": errors}

    if len(slots) > MAX_SURFACE_SLOTS:
        _err("TOO_MANY_SLOTS", f"at most {MAX_SURFACE_SLOTS} slots allowed")
        return {"valid": False, "errors": errors}

    catalog = _mode_catalog_lookup(modes)
    use_catalog = modes is not None

    occ_owner: dict[tuple[int, int], str] = {}

    for i, raw in enumerate(slots):
        if not isinstance(raw, dict):
            _err("INVALID_SLOT_DATA", f"slots[{i}] must be an object")
            continue

        sid_raw = raw.get("id")
        if sid_raw is None or (isinstance(sid_raw, str) and not str(sid_raw).strip()):
            _err("MISSING_SLOT_ID", "each slot must have a non-empty id", None)
            continue
        sid = str(sid_raw).strip()

        bad_coord = False
        for nm, val in (("x", raw.get("x")), ("y", raw.get("y")), ("w", raw.get("w")), ("h", raw.get("h"))):
            if val is None:
                _err("INVALID_SLOT_DATA", f"slot {sid}: {nm} is required", sid)
                bad_coord = True
                break
            if isinstance(val, bool) or not isinstance(val, (int, float, str)):
                _err("INVALID_SLOT_DATA", f"slot {sid}: {nm} must be numeric", sid)
                bad_coord = True
                break
        if bad_coord:
            continue

        x = _as_int(raw.get("x"), -1)
        y = _as_int(raw.get("y"), -1)
        w = _as_int(raw.get("w"), 0)
        h = _as_int(raw.get("h"), 0)

        if x < 0 or y < 0 or w < 1 or h < 1:
            _err("INVALID_SLOT_DATA", f"slot {sid}: x,y must be ≥0 and w,h must be ≥1", sid)
            continue
        if w > columns or h > rows:
            _err("INVALID_SIZE", f"slot {sid}: span {w}×{h} exceeds grid {columns}×{rows}", sid)
            continue
        if x + w > columns or y + h > rows:
            _err("OUT_OF_BOUNDS", f"slot {sid} exceeds grid bounds", sid)
            continue

        st = normalize_legacy_slot_type(
            str(raw.get("slot_type") or ""),
            w,
            h,
            columns,
            rows,
        ).strip().upper()

        expected = expected_slot_type_for_span(w, h, columns, rows)
        if st != expected:
            _err(
                "INVALID_SLOT_TYPE",
                f"slot {sid}: slot_type must be {expected} for span {w}×{h} (got {st or 'missing'})",
                sid,
            )
            continue

        overlap_at: tuple[int, int] | None = None
        other_id: str | None = None
        for ry in range(y, y + h):
            for rx in range(x, x + w):
                key = (rx, ry)
                if key in occ_owner:
                    overlap_at = key
                    other_id = occ_owner[key]
                    break
            if overlap_at:
                break
        if overlap_at and other_id:
            _err(
                "SLOT_OVERLAP",
                f"Slots {other_id} and {sid} overlap at cell ({overlap_at[0]},{overlap_at[1]})",
                sid,
            )
            continue

        for ry in range(y, y + h):
            for rx in range(x, x + w):
                occ_owner[(rx, ry)] = sid

        mid = str(raw.get("mode_id") or raw.get("mode") or raw.get("persona") or "").strip().upper()
        if not mid:
            continue

        if use_catalog:
            entry = catalog.get(mid)
            if entry is None:
                _err("MODE_NOT_FOUND", f"mode {mid} is not in the available modes list", sid)
                continue
            sst = entry.get("supported_slot_types")
            if isinstance(sst, list) and len(sst) > 0:
                allowed_set = {str(x).strip().upper() for x in sst if isinstance(x, str)}
                if expected not in allowed_set:
                    _err(
                        "MODE_NOT_SUPPORTED",
                        f"mode {mid} does not support slot_type {expected}",
                        sid,
                    )
        elif get_mode_definition:
            defn = get_mode_definition(mid)
            if not defn:
                _err("MODE_NOT_FOUND", f"mode {mid} is unknown", sid)
                continue
            if not mode_definition_supports_expected_type(defn, expected):
                _err(
                    "MODE_NOT_SUPPORTED",
                    f"mode {mid} does not support slot_type {expected}",
                    sid,
                )

    return {"valid": len(errors) == 0, "errors": errors}


def validate_layout_document(
    layout: Any,
    *,
    get_mode_definition: Callable[[str], dict | None] | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper: same as :func:`validate_layout` without a client ``modes`` list."""
    return validate_layout(layout, modes=None, get_mode_definition=get_mode_definition)


def sort_slots_reading_order(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top-to-bottom, left-to-right."""
    return sorted(slots, key=lambda s: (_as_int(s.get("y"), 0), _as_int(s.get("x"), 0)))


def body_slot_rects_px(
    body: tuple[int, int, int, int],
    grid: dict[str, Any],
    slots: list[dict[str, Any]],
) -> list[tuple[int, int, int, int]]:
    """Map each slot in *reading order* to pixel rect ``(x0,y0,x1,y1)`` (x1,y1 exclusive)."""
    x0, y0, x1, y1 = body
    bw, bh = x1 - x0, y1 - y0
    cols, rows, gap, pad = grid_dimensions(grid)
    usable_w = max(1, bw - 2 * pad)
    usable_h = max(1, bh - 2 * pad)
    cell_w = (usable_w - gap * (cols - 1)) // cols
    cell_h = (usable_h - gap * (rows - 1)) // rows
    cell_w = max(8, cell_w)
    cell_h = max(8, cell_h)

    ordered = sort_slots_reading_order(slots)
    rects: list[tuple[int, int, int, int]] = []
    for s in ordered:
        gx = _as_int(s.get("x"), 0)
        gy = _as_int(s.get("y"), 0)
        gw = _as_int(s.get("w"), 1)
        gh = _as_int(s.get("h"), 1)
        sx0 = x0 + pad + gx * (cell_w + gap)
        sy0 = y0 + pad + gy * (cell_h + gap)
        sx1 = sx0 + gw * cell_w + (gw - 1) * gap
        sy1 = sy0 + gh * cell_h + (gh - 1) * gap
        sx1 = min(x1, max(sx0 + 8, sx1))
        sy1 = min(y1, max(sy0 + 8, sy1))
        rects.append((sx0, sy0, sx1, sy1))
    return rects


def cell_rect_px(
    body: tuple[int, int, int, int],
    grid: dict[str, Any],
    rx: int,
    ry: int,
) -> tuple[int, int, int, int]:
    """Pixel rectangle of one discrete grid cell ``(rx, ry)`` (same geometry as ``body_slot_rects_px`` for 1×1)."""
    x0, y0, x1, y1 = body
    bw, bh = x1 - x0, y1 - y0
    cols, rows, gap, pad = grid_dimensions(grid)
    if rx < 0 or ry < 0 or rx >= cols or ry >= rows:
        return (x0, y0, x0, y0)
    usable_w = max(1, bw - 2 * pad)
    usable_h = max(1, bh - 2 * pad)
    cell_w = (usable_w - gap * (cols - 1)) // cols
    cell_h = (usable_h - gap * (rows - 1)) // rows
    cell_w = max(8, cell_w)
    cell_h = max(8, cell_h)
    sx0 = x0 + pad + rx * (cell_w + gap)
    sy0 = y0 + pad + ry * (cell_h + gap)
    sx1 = sx0 + cell_w
    sy1 = sy0 + cell_h
    sx1 = min(x1, max(sx0 + 8, sx1))
    sy1 = min(y1, max(sy0 + 8, sy1))
    return (sx0, sy0, sx1, sy1)


def cell_slot_occupy_ids(
    slots: list[dict[str, Any]],
    *,
    columns: int,
    rows: int,
) -> list[list[str | None]]:
    """Map each cell to owning slot ``id`` (invalid overlaps: last write wins)."""
    occ: list[list[str | None]] = [[None] * columns for _ in range(rows)]
    for s in slots:
        sx = _as_int(s.get("x"), 0)
        sy = _as_int(s.get("y"), 0)
        sw = _as_int(s.get("w"), 1)
        sh = _as_int(s.get("h"), 1)
        sid = str(s.get("id") or "").strip() or "?"
        for gy in range(sy, sy + sh):
            for gx in range(sx, sx + sw):
                if 0 <= gx < columns and 0 <= gy < rows:
                    occ[gy][gx] = sid
    return occ


def resolve_slot_widget_block(
    slot: dict[str, Any],
    layout_blocks: list[dict[str, Any]] | None,
    index: int,
) -> dict[str, Any] | None:
    """Mode assignment: per-slot ``mode`` / ``mode_id``, else ``layout_blocks[index]``."""
    mode = slot.get("mode") or slot.get("mode_id") or slot.get("persona")
    if isinstance(mode, str) and mode.strip():
        return {"mode": mode.strip().upper(), "slot_id": slot.get("id")}
    if layout_blocks and index < len(layout_blocks) and isinstance(layout_blocks[index], dict):
        return layout_blocks[index]
    return None


def build_legacy_layout_from_grid(
    slots_sorted: list[dict[str, Any]],
    layout_blocks: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Produce a flat ``layout`` list for APIs that expect ``layout[]`` with mode references."""
    out: list[dict[str, Any]] = []
    blocks = layout_blocks if isinstance(layout_blocks, list) else []
    for i, slot in enumerate(slots_sorted):
        sid = str(slot.get("id") or f"slot_{i}")
        block = resolve_slot_widget_block(slot, blocks, i)
        if not block:
            entry = {"slot_id": sid, "mode": "STOIC", "position": f"slot_{i}"}
        else:
            entry = dict(block)
            entry["slot_id"] = sid
            entry["position"] = entry.get("position") or f"slot_{i}"
        st = str(slot.get("slot_type") or "").strip().upper()
        if st:
            entry["slot_type"] = st
        out.append(entry)
    return out


def mode_supports_slot_type(
    mode_definition: dict | None,
    slot_type: str,
    *,
    slot_span: tuple[int, int] | None = None,
) -> bool:
    """If ``supported_slot_types`` is set, ``slot_type`` must be listed; else allow all (legacy).

    For ``CUSTOM`` slots, also allow a match when the canonical shape for ``(w,h)`` is listed
    (e.g. a 2×1 CUSTOM tile is OK if ``WIDE`` is supported).
    """
    if not mode_definition or not isinstance(mode_definition, dict):
        return True
    allowed = mode_definition.get("supported_slot_types")
    if not isinstance(allowed, list) or len(allowed) == 0:
        return True
    st = (slot_type or "").strip().upper()
    if st == "LARGE":
        st = "FULL"
    norm = {str(x).strip().upper() for x in allowed if isinstance(x, str)}
    if "LARGE" in norm:
        norm = norm | {"FULL"}
        norm.discard("LARGE")
    if st in norm:
        return True
    if st == "CUSTOM" and slot_span is not None:
        w, h = slot_span
        inferred = infer_slot_type_from_span(int(w), int(h))
        if inferred in norm:
            return True
    return False


def validate_surface_slot_modes(
    surface: dict[str, Any],
    get_mode_definition: Callable[[str], dict | None],
) -> tuple[bool, str]:
    """Ensure each slot's mode declares compatibility with that ``slot_type``."""
    _grid, slots = parse_surface_grid(surface)
    if not slots:
        return True, ""
    for slot in sort_slots_reading_order(slots):
        st = str(slot.get("slot_type") or "").strip().upper()
        mid = str(slot.get("mode_id") or slot.get("mode") or slot.get("persona") or "").strip().upper()
        if not mid or not st:
            continue
        defn = get_mode_definition(mid)
        w = _as_int(slot.get("w"), 1)
        h = _as_int(slot.get("h"), 1)
        if not mode_supports_slot_type(defn, st, slot_span=(w, h)):
            return False, f"mode {mid} does not list slot_type {st} in supported_slot_types"
    return True, ""
