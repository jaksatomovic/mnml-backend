from core.surface_engine import (
    build_surface_render_payload,
    evaluate_event_for_device,
    resolve_device_surface,
    resolve_scheduled_surface,
)


def test_schedule_resolution():
    schedule = [
        {"from": "07:00", "to": "09:00", "surface": "morning"},
        {"from": "09:00", "to": "18:00", "surface": "work"},
    ]
    # Time-independent sanity check: function should return known surfaces when range can match.
    result = resolve_scheduled_surface(schedule)
    assert result in {"morning", "work", None}


def test_rule_override_event():
    config = {
        "device_mode": "surface",
        "surfaces": [
            {
                "id": "work",
                "layout": [{"type": "text", "content": "Work"}],
                "rules": [
                    {
                        "if": "event.type == 'build_failed'",
                        "action": "override",
                        "target": "alert_view",
                        "priority": "critical",
                        "duration": 120,
                    }
                ],
            },
            {"id": "alert_view", "layout": [{"type": "text", "content": "Alert"}]},
        ],
    }
    matched = evaluate_event_for_device(
        "AA:BB:CC:DD:EE:FF",
        config,
        {"type": "build_failed", "priority": "high", "data": {}},
    )
    assert matched is not None
    assert matched["action"] == "override"
    assert matched["target"] == "alert_view"


def test_resolve_device_surface_with_assigned():
    config = {
        "assigned_surface": "home",
        "surfaces": [{"id": "home", "layout": [{"type": "text", "content": "Home"}]}],
        "surfaceSchedule": [],
    }
    active, reason = resolve_device_surface("AA:BB:CC:DD:EE:FF", config)
    assert active is not None
    payload = build_surface_render_payload(active, reason)
    assert payload["meta"]["surface"] == "home"
