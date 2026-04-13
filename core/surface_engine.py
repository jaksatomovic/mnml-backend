from __future__ import annotations

import logging
from datetime import datetime
from threading import Lock
from typing import Optional

from .surface_grid import (
    build_legacy_layout_from_grid,
    grid_dimensions,
    parse_surface_grid,
    sort_slots_reading_order,
    validate_slots_for_grid,
    validate_surface_slot_modes,
)

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"critical": 3, "high": 2, "normal": 1}
_state_lock = Lock()
_device_overrides: dict[str, dict] = {}


def _priority_value(value: str) -> int:
    return _PRIORITY_ORDER.get(str(value or "normal").strip().lower(), 1)


def _normalize_event(event: dict) -> dict:
    if not isinstance(event, dict):
        return {"type": "", "priority": "normal", "timestamp": "", "data": {}}
    return {
        "type": str(event.get("type") or "").strip(),
        "priority": str(event.get("priority") or "normal").strip().lower(),
        "timestamp": event.get("timestamp") or datetime.now().isoformat(),
        "data": event.get("data") if isinstance(event.get("data"), dict) else {},
    }


def _matches_condition(condition: str, event: dict) -> bool:
    cond = str(condition or "").strip()
    if not cond:
        return False
    # Minimal safe parser for MVP; supports:
    # event.type == 'x' and event.priority == 'high'
    if "==" in cond:
        left, right = cond.split("==", 1)
        left = left.strip()
        right_value = right.strip().strip("'").strip('"')
        if left == "event.type":
            return str(event.get("type") or "") == right_value
        if left == "event.priority":
            return str(event.get("priority") or "") == right_value
    return False


def _pick_rule(rules: list[dict], event: dict) -> Optional[dict]:
    ordered = sorted(
        [r for r in rules if isinstance(r, dict)],
        key=lambda r: _priority_value(str(r.get("priority") or "normal")),
        reverse=True,
    )
    for rule in ordered:
        if _matches_condition(str(rule.get("if") or ""), event):
            return rule
    return None


_WEEKDAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _playlist_entries_from_nested(raw: list) -> list[dict]:
    out: list[dict] = []
    for i, p in enumerate(raw or []):
        if not isinstance(p, dict):
            continue
        sid = str(p.get("surface_id") or "").strip()
        if not sid:
            continue
        out.append(
            {
                "surface_id": sid,
                "enabled": True,
                "duration_sec": int(p.get("duration_sec") or 300),
                "order": i,
            }
        )
    return out


def resolve_playlist_surface(playlist: list[dict] | None, now: Optional[datetime] = None) -> Optional[str]:
    """Pick active surface_id from a rotation list using duration_sec windows (wall-clock modulo)."""
    if not playlist:
        return None
    items = [p for p in playlist if isinstance(p, dict)]
    items.sort(key=lambda x: int(x.get("order") or 0))
    enabled: list[dict] = []
    for p in items:
        if not p.get("enabled", True):
            continue
        sid = str(p.get("surface_id") or "").strip()
        if not sid:
            continue
        enabled.append(p)
    if not enabled:
        return None
    total = 0
    durations: list[int] = []
    for p in enabled:
        d = max(10, int(p.get("duration_sec") or 300))
        durations.append(d)
        total += d
    if total <= 0:
        return str(enabled[0].get("surface_id") or "").strip() or None
    ts = now or datetime.now()
    sec = int(ts.timestamp()) % total
    acc = 0
    for p, d in zip(enabled, durations):
        if sec < acc + d:
            return str(p.get("surface_id") or "").strip() or None
        acc += d
    return str(enabled[0].get("surface_id") or "").strip() or None


def resolve_scheduled_surface(
    schedule: list[dict],
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Time-of-day + optional weekday rules. Supports legacy ``surface`` or ``surface_id``."""
    ts = now or datetime.now()
    hhmm = ts.strftime("%H:%M")
    wd = _WEEKDAY_CODES[ts.weekday()]
    for item in schedule:
        if not isinstance(item, dict):
            continue
        days = item.get("days")
        if isinstance(days, list) and len(days) > 0:
            dayset = {str(d).strip().lower() for d in days if isinstance(d, str)}
            if dayset and wd not in dayset:
                continue
        start = str(item.get("from") or "").strip()
        end = str(item.get("to") or "").strip()
        if not start or not end:
            continue
        if not (start <= hhmm < end):
            continue
        typ = str(item.get("type") or "surface").strip().lower()
        if typ == "playlist":
            nested = item.get("playlist")
            if isinstance(nested, list) and nested:
                pl = _playlist_entries_from_nested(nested)
                picked = resolve_playlist_surface(pl, now=ts)
                if picked:
                    return picked
            continue
        target = str(item.get("surface_id") or item.get("surface") or "").strip()
        if target:
            return target
    return None


def _effective_surface_playback_mode(config: dict) -> str:
    explicit = str(
        config.get("surfacePlaybackMode") or config.get("surface_playback_mode") or ""
    ).strip().lower()
    if explicit in ("single", "rotate", "scheduled"):
        return explicit
    schedule = config.get("surfaceSchedule") if isinstance(config.get("surfaceSchedule"), list) else []
    if schedule and len(schedule) > 0:
        return "scheduled"
    playlist = config.get("surfacePlaylist") if isinstance(config.get("surfacePlaylist"), list) else []
    enabled = [
        p
        for p in playlist
        if isinstance(p, dict)
        and p.get("enabled", True)
        and str(p.get("surface_id") or "").strip()
    ]
    if len(enabled) > 1:
        return "rotate"
    return "single"


def evaluate_event_for_device(mac: str, config: dict, event_payload: dict) -> Optional[dict]:
    event = _normalize_event(event_payload)
    if str(config.get("device_mode") or config.get("deviceMode") or "mode").strip().lower() != "surface":
        return None
    surfaces = config.get("surfaces") if isinstance(config.get("surfaces"), list) else []
    by_id = {str(s.get("id") or "").strip(): s for s in surfaces if isinstance(s, dict)}
    for surface in by_id.values():
        rules = surface.get("rules") if isinstance(surface.get("rules"), list) else []
        matched = _pick_rule(rules, event)
        if not matched:
            continue
        action = str(matched.get("action") or "noop").strip().lower()
        if action == "noop":
            return None
        result = {
            "action": action,
            "target": str(matched.get("target") or "").strip(),
            "priority": str(matched.get("priority") or "normal").strip().lower(),
            "duration": int(matched.get("duration") or 300),
            "event": event,
            "surface_id": str(surface.get("id") or "").strip(),
        }
        if action in ("override", "switch_surface"):
            with _state_lock:
                _device_overrides[mac.upper()] = {
                    "target": result["target"],
                    "expires_at": datetime.now().timestamp() + max(1, result["duration"]),
                    "event": event,
                }
        return result
    return None


def resolve_device_surface(mac: str, config: dict) -> tuple[Optional[dict], Optional[dict]]:
    surfaces = config.get("surfaces") if isinstance(config.get("surfaces"), list) else []
    by_id = {str(s.get("id") or "").strip(): s for s in surfaces if isinstance(s, dict)}
    schedule = config.get("surfaceSchedule") if isinstance(config.get("surfaceSchedule"), list) else []
    now = datetime.now()

    override = None
    with _state_lock:
        existing = _device_overrides.get(mac.upper())
        if existing and float(existing.get("expires_at") or 0) > now.timestamp():
            override = existing
        elif existing:
            _device_overrides.pop(mac.upper(), None)

    if override:
        target = str(override.get("target") or "").strip()
        return by_id.get(target), {"type": "override", "event": override.get("event") or {}}

    assigned_surface = str(config.get("assigned_surface") or config.get("assignedSurface") or "").strip()
    playlist = config.get("surfacePlaylist") if isinstance(config.get("surfacePlaylist"), list) else []
    playback = _effective_surface_playback_mode(config)

    scheduled_surface: Optional[str] = None
    playlist_pick: Optional[str] = None

    if playback == "single":
        active_id = assigned_surface or None
        reason = {"type": "assigned"}
    elif playback == "rotate":
        playlist_pick = resolve_playlist_surface(playlist, now=now)
        active_id = playlist_pick or assigned_surface or None
        reason = {"type": "playlist", "playlist_surface": playlist_pick}
    elif playback == "scheduled":
        scheduled_surface = resolve_scheduled_surface(schedule, now=now)
        active_id = scheduled_surface or assigned_surface or None
        reason = {"type": "schedule" if scheduled_surface else "assigned", "scheduled_surface": scheduled_surface}
    else:
        active_id = assigned_surface or None
        reason = {"type": "assigned"}

    return by_id.get(active_id), reason


def build_surface_render_payload(surface: Optional[dict], reason: Optional[dict] = None) -> dict:
    if not surface:
        return {
            "layout": [{"type": "text", "content": "No active surface", "size": "medium"}],
            "meta": {"surface": "", "reason": reason or {"type": "none"}},
        }
    raw_layout = surface.get("layout") if isinstance(surface.get("layout"), list) else []
    grid, slot_defs = parse_surface_grid(surface)
    layout_out: list = list(raw_layout)
    grid_meta = None
    slots_meta = None
    slot_compatibility_error: str | None = None
    if grid and slot_defs:
        cols, rows, _, _ = grid_dimensions(grid)
        ok, err = validate_slots_for_grid(slot_defs, columns=cols, rows=rows)
        if ok:
            sorted_slots = sort_slots_reading_order(slot_defs)
            layout_out = build_legacy_layout_from_grid(sorted_slots, raw_layout)
            grid_meta = grid
            slots_meta = slot_defs
            try:
                from .mode_registry import get_registry

                reg = get_registry()

                def _mode_def(mid: str):
                    m = (mid or "").strip().upper()
                    if not m:
                        return None
                    jm = reg.get_json_mode(m, None, language="zh")
                    return jm.definition if jm else None

                cok, cerr = validate_surface_slot_modes(surface, _mode_def)
                if not cok:
                    slot_compatibility_error = cerr
                    logger.warning("[surface] slot/mode compatibility: %s", cerr)
            except Exception:
                logger.warning("[surface] slot/mode compatibility check failed", exc_info=True)
        else:
            logger.warning("[surface] grid/slots invalid (%s), using raw layout only", err)

    meta = {
        "surface": str(surface.get("id") or ""),
        "refresh": surface.get("refresh") if isinstance(surface.get("refresh"), dict) else {"mode": "hybrid", "interval": 300},
        "reason": reason or {"type": "assigned"},
        "title": surface.get("name") or surface.get("title"),
        "layout_id": str(surface.get("layout_id") or surface.get("layoutId") or "").strip() or None,
        "grid": grid_meta,
        "slots": slots_meta,
        "slot_compatibility_error": slot_compatibility_error,
    }
    # Drop None values for compact JSON (keep explicit False/0)
    meta = {k: v for k, v in meta.items() if v is not None}
    return {
        "layout": layout_out,
        "meta": meta,
    }
