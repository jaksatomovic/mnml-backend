from __future__ import annotations

from typing import Any
import logging

import httpx

logger = logging.getLogger(__name__)

_BF6_PROFILE_URL = "https://api.gametools.network/bf6/profile/"
_SUPPORTED_PLATFORMS = {"pc", "xboxone", "ps4", "xboxseries", "ps5", "xbox", "psn"}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_hours(value: Any) -> str:
    seconds = _to_int(value, 0)
    hours = max(0.0, float(seconds) / 3600.0)
    return f"{hours:.1f}h"


def _extract_stats_map(profile: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    stats = profile.get("stats", [])
    if not isinstance(stats, list):
        return out
    for item in stats:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name or name in out:
            continue
        out[name] = item.get("value")
    return out


def _pick_stat(stats: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        k = key.lower()
        if k in stats and stats[k] is not None:
            return stats[k]
    return None


async def get_bf6_profile_snapshot(username: str, platform: str) -> dict[str, Any]:
    username = str(username or "").strip()
    if not username:
        raise ValueError("BF6 username is required")

    platform_norm = str(platform or "pc").strip().lower()
    if platform_norm not in _SUPPORTED_PLATFORMS:
        platform_norm = "pc"

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        resp = await client.get(
            _BF6_PROFILE_URL,
            params={"name": username, "platform": platform_norm, "skip_battlelog": "true"},
        )
        resp.raise_for_status()
        payload = resp.json()

    profiles = payload.get("playerProfiles", []) if isinstance(payload, dict) else []
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Player profile not found")

    profile = profiles[0] if isinstance(profiles[0], dict) else {}
    player_card = profile.get("playerCard", {}) if isinstance(profile.get("playerCard"), dict) else {}
    rank_image = player_card.get("rankImage", {}) if isinstance(player_card.get("rankImage"), dict) else {}
    response_username = str((payload or {}).get("userName") or "").strip() if isinstance(payload, dict) else ""
    response_avatar = str((payload or {}).get("avatar") or "").strip() if isinstance(payload, dict) else ""
    stats = _extract_stats_map(profile)

    kills = _to_int(_pick_stat(stats, "kills_total", "human_kills_total"), 0)
    deaths = _to_int(_pick_stat(stats, "deaths_total"), 0)
    score_total = _to_int(_pick_stat(stats, "score_total"), 0)
    assists = _to_int(_pick_stat(stats, "assist_total"), 0)
    revives = _to_int(_pick_stat(stats, "revives_teammates_total"), 0)
    headshots = _to_int(_pick_stat(stats, "kills_headshots_total"), 0)
    obj_time = _fmt_hours(_pick_stat(stats, "obj_time_total", "obj_conttime_total"))
    vehicle_time = _fmt_hours(_to_int(_pick_stat(stats, "driving_time_total"), 0) + _to_int(_pick_stat(stats, "flying_time_total"), 0))
    kd_raw = _pick_stat(stats, "kill_death_ratio")

    if kd_raw is None:
        kd = (kills / deaths) if deaths > 0 else float(kills)
    else:
        kd = _to_float(kd_raw, (kills / deaths) if deaths > 0 else float(kills))

    kd_text = f"{kd:.2f}"
    hs_rate = (headshots / kills * 100.0) if kills > 0 else 0.0
    hs_rate_text = f"{hs_rate:.1f}%"

    return {
        "title": "BF6 Profile",
        "username": response_username or username,
        "platform": platform_norm.upper(),
        "rank": str(_to_int(player_card.get("rank"), 0)),
        "avatar_url": response_avatar or str(rank_image.get("large") or rank_image.get("small") or ""),
        "badges": _fmt_int(_to_int(player_card.get("badges"), 0)),
        "score_total": _fmt_int(score_total),
        "kills": _fmt_int(kills),
        "deaths": _fmt_int(deaths),
        "kd": kd_text,
        "assists": _fmt_int(assists),
        "revives": _fmt_int(revives),
        "headshots": _fmt_int(headshots),
        "headshot_rate": hs_rate_text,
        "summary_left": [
            {"line": f"Kills   {_fmt_int(kills)}"},
            {"line": f"Deaths  {_fmt_int(deaths)}"},
            {"line": f"K/D     {kd_text}"},
            {"line": f"Assists {_fmt_int(assists)}"},
            {"line": f"ObjTime {obj_time}"},
        ],
        "summary_right": [
            {"line": f"Headshots {_fmt_int(headshots)}"},
            {"line": f"HS Rate   {hs_rate_text}"},
            {"line": f"Revives   {_fmt_int(revives)}"},
            {"line": f"Badges    {_fmt_int(_to_int(player_card.get('badges'), 0))}"},
            {"line": f"Veh Time  {vehicle_time}"},
        ],
    }
