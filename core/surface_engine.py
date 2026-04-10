from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Optional

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


def resolve_scheduled_surface(schedule: list[dict], now: Optional[datetime] = None) -> Optional[str]:
    ts = now or datetime.now()
    hhmm = ts.strftime("%H:%M")
    for item in schedule:
        if not isinstance(item, dict):
            continue
        start = str(item.get("from") or "").strip()
        end = str(item.get("to") or "").strip()
        target = str(item.get("surface") or "").strip()
        if start and end and target and start <= hhmm < end:
            return target
    return None


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
        if action == "override":
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
    scheduled_surface = resolve_scheduled_surface(schedule, now=now)
    active_id = scheduled_surface or assigned_surface
    return by_id.get(active_id), {"type": "schedule" if scheduled_surface else "assigned"}


def build_surface_render_payload(surface: Optional[dict], reason: Optional[dict] = None) -> dict:
    if not surface:
        return {
            "layout": [{"type": "text", "content": "No active surface", "size": "medium"}],
            "meta": {"surface": "", "reason": reason or {"type": "none"}},
        }
    layout = surface.get("layout") if isinstance(surface.get("layout"), list) else []
    return {
        "layout": layout,
        "meta": {
            "surface": str(surface.get("id") or ""),
            "refresh": surface.get("refresh") if isinstance(surface.get("refresh"), dict) else {"mode": "hybrid", "interval": 300},
            "reason": reason or {"type": "assigned"},
        },
    }
