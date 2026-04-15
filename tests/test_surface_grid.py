"""Tests for fixed grid surface layouts (MVP default 2×2)."""

from core.surface_grid import (
    DEFAULT_GRID_COLUMNS,
    DEFAULT_GRID_ROWS,
    body_slot_rects_px,
    grid_dimensions,
    infer_slot_type_from_span,
    sort_slots_reading_order,
    validate_layout,
    validate_layout_document,
    validate_slots_for_grid,
)


def test_default_grid_constants():
    assert DEFAULT_GRID_COLUMNS == 2
    assert DEFAULT_GRID_ROWS == 2


def test_validate_overlap_rejected():
    slots = [
        {"id": "a", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
        {"id": "b", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
    ]
    ok, err = validate_slots_for_grid(slots, columns=2, rows=2)
    assert not ok
    assert "overlap" in err.lower()


def test_validate_span_mismatch():
    slots = [{"id": "a", "x": 0, "y": 0, "w": 2, "h": 1, "slot_type": "SMALL"}]
    ok, err = validate_slots_for_grid(slots, columns=2, rows=2)
    assert not ok
    assert "match" in err.lower() or "span" in err.lower()


def test_user_example_layout_valid():
    """Spec example: two SMALL top row + WIDE bottom row on 2×2 grid."""
    slots = [
        {"id": "top_left", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
        {"id": "top_right", "x": 1, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
        {"id": "bottom_full", "x": 0, "y": 1, "w": 2, "h": 1, "slot_type": "WIDE"},
    ]
    ok, err = validate_slots_for_grid(slots, columns=2, rows=2)
    assert ok, err


def test_full_slot_must_span_entire_grid():
    slots = [{"id": "full", "x": 0, "y": 0, "w": 2, "h": 2, "slot_type": "FULL"}]
    ok, err = validate_slots_for_grid(slots, columns=2, rows=2)
    assert ok, err


def test_full_slot_wrong_span_rejected():
    slots = [{"id": "bad", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "FULL"}]
    ok, err = validate_slots_for_grid(slots, columns=2, rows=2)
    assert not ok
    assert "full" in err.lower() or "match" in err.lower() or "span" in err.lower()


def test_sort_slots_reading_order():
    slots = [
        {"id": "b", "x": 1, "y": 0, "w": 1, "h": 1},
        {"id": "a", "x": 0, "y": 0, "w": 1, "h": 1},
    ]
    s = sort_slots_reading_order(slots)
    assert [x["id"] for x in s] == ["a", "b"]


def test_body_slot_rects_three_slots():
    body = (8, 36, 392, 270)
    grid = {"columns": 2, "rows": 2, "gap": 6, "padding": 8}
    slots = [
        {"id": "slot_1", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
        {"id": "slot_2", "x": 1, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
        {"id": "bottom_full", "x": 0, "y": 1, "w": 2, "h": 1, "slot_type": "WIDE"},
    ]
    rects = body_slot_rects_px(body, grid, slots)
    assert len(rects) == 3
    # Bottom WIDE should be at least as wide as a single SMALL tile
    assert rects[2][2] - rects[2][0] >= rects[0][2] - rects[0][0]


def test_grid_dimensions_defaults():
    g = {}
    assert grid_dimensions(g) == (2, 2, 6, 8)


def test_infer_slot_type_from_span():
    assert infer_slot_type_from_span(1, 1) == "SMALL"
    assert infer_slot_type_from_span(3, 1) == "CUSTOM"


def test_validate_layout_document_ok():
    layout = {
        "id": "x",
        "grid": {"columns": 2, "rows": 3},
        "slots": [
            {"id": "a", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
            {"id": "b", "x": 1, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL"},
            {"id": "c", "x": 0, "y": 1, "w": 2, "h": 2, "slot_type": "CUSTOM"},
        ],
    }
    r = validate_layout_document(layout, get_mode_definition=lambda _m: None)
    assert r["valid"] is True
    assert r["errors"] == []


def test_validate_layout_document_custom_span():
    layout = {
        "grid": {"columns": 3, "rows": 3},
        "slots": [{"id": "x", "x": 0, "y": 0, "w": 3, "h": 1, "slot_type": "CUSTOM"}],
    }
    r = validate_layout_document(layout, get_mode_definition=lambda _m: None)
    assert r["valid"] is True


def test_validate_layout_document_grid_range():
    layout = {
        "grid": {"columns": 5, "rows": 3},
        "slots": [],
    }
    r = validate_layout_document(layout)
    assert r["valid"] is False
    assert any(e["code"] == "GRID_INVALID" for e in r["errors"])


def test_validate_layout_document_too_many_slots():
    slots = [
        {"id": f"s{i}", "x": i % 2, "y": i // 2, "w": 1, "h": 1, "slot_type": "SMALL"}
        for i in range(7)
    ]
    layout = {"grid": {"columns": 4, "rows": 6}, "slots": slots}
    r = validate_layout_document(layout)
    assert r["valid"] is False
    assert any(e["code"] == "TOO_MANY_SLOTS" for e in r["errors"])


def test_validate_layout_strict_slot_type_mismatch():
    layout = {
        "grid": {"columns": 2, "rows": 2},
        "slots": [
            {"id": "a", "x": 0, "y": 0, "w": 2, "h": 1, "slot_type": "SMALL"},
        ],
    }
    r = validate_layout(layout, modes=None, get_mode_definition=lambda _m: None)
    assert r["valid"] is False
    assert any(e["code"] == "INVALID_SLOT_TYPE" for e in r["errors"])


def test_validate_layout_with_modes_catalog():
    layout = {
        "grid": {"columns": 2, "rows": 2},
        "slots": [
            {"id": "a", "x": 0, "y": 0, "w": 1, "h": 1, "slot_type": "SMALL", "mode_id": "QUOTE"},
        ],
    }
    modes = [{"id": "QUOTE", "name": "Quote", "supported_slot_types": ["SMALL"]}]
    r = validate_layout(layout, modes=modes)
    assert r["valid"] is True
