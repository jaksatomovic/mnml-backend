from __future__ import annotations

import asyncio
from datetime import datetime
from html import unescape
import logging
import re
from typing import Any
import xml.etree.ElementTree as ET

import httpx

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


logger = logging.getLogger(__name__)

_JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
_F1_NEWS_RSS = "https://www.the-race.com/category/formula-1/rss/"
_OPENF1_RESULTS_URL = "https://api.openf1.org/v1/session_result?session_key=latest&position%3C=20"


async def _fetch_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _strip_html(value: str, *, max_len: int = 240) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len > 0 and len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _localize_session(utc_date: str, utc_time: str, timezone_name: str) -> tuple[datetime | None, str, str]:
    if not utc_date or not utc_time:
        return None, "", ""
    normalized_time = utc_time.rstrip("Z")
    try:
        utc_dt = datetime.fromisoformat(f"{utc_date}T{normalized_time}+00:00")
    except ValueError:
        return None, "", ""

    if timezone_name and ZoneInfo is not None:
        try:
            local_dt = utc_dt.astimezone(ZoneInfo(timezone_name))
        except Exception:
            local_dt = utc_dt
    else:
        local_dt = utc_dt

    return local_dt, local_dt.strftime("%a %d %b"), local_dt.strftime("%H:%M")


def _build_session_list(race: dict[str, Any], timezone_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session_keys = (
        ("FirstPractice", "FP1"),
        ("SecondPractice", "FP2"),
        ("ThirdPractice", "FP3"),
        ("SprintQualifying", "Sprint Quali"),
        ("Sprint", "Sprint"),
        ("Qualifying", "Qualifying"),
    )

    sessions: list[dict[str, Any]] = []
    if timezone_name and ZoneInfo is not None:
        try:
            now = datetime.now(ZoneInfo(timezone_name))
        except Exception:
            now = datetime.now(tz=None).astimezone()
    else:
        now = datetime.now(tz=None).astimezone()

    for api_key, label in session_keys:
        session = race.get(api_key)
        if not isinstance(session, dict):
            continue
        local_dt, date_label, time_label = _localize_session(
            str(session.get("date", "") or ""),
            str(session.get("time", "") or ""),
            timezone_name,
        )
        sessions.append(
            {
                "label": label,
                "date": date_label,
                "time": time_label,
                "utc_date": str(session.get("date", "") or ""),
                "utc_time": str(session.get("time", "") or ""),
                "sort_ts": local_dt.timestamp() if local_dt else 0,
                "is_upcoming": bool(local_dt and local_dt >= now),
            }
        )

    local_dt, date_label, time_label = _localize_session(
        str(race.get("date", "") or ""),
        str(race.get("time", "") or ""),
        timezone_name,
    )
    sessions.append(
        {
            "label": "Race",
            "date": date_label,
            "time": time_label,
            "utc_date": str(race.get("date", "") or ""),
            "utc_time": str(race.get("time", "") or ""),
            "sort_ts": local_dt.timestamp() if local_dt else 0,
            "is_upcoming": bool(local_dt and local_dt >= now),
        }
    )

    sessions.sort(key=lambda item: (item.get("sort_ts", 0), item.get("label", "")))
    next_session = next((item for item in sessions if item.get("is_upcoming")), sessions[-1] if sessions else {})
    return sessions, next_session


def _short_constructor_name(name: str, constructor_id: str) -> str:
    cid = (constructor_id or "").strip().lower()
    mapping = {
        "mclaren": "McL",
        "ferrari": "Fer",
        "mercedes": "Merc",
        "red_bull": "RB",
        "williams": "Wil",
        "haas": "Haas",
        "alpine": "Alp",
        "aston_martin": "AM",
        "rb": "RB",
        "racing_bulls": "RB",
        "sauber": "Sbr",
        "kick_sauber": "Sbr",
    }
    if cid in mapping:
        return mapping[cid]
    cleaned = (name or "").strip()
    if len(cleaned) <= 6:
        return cleaned
    return cleaned[:6]


def _split_rows(rows: list[dict[str, str]], left_count: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return rows[:left_count], rows[left_count:]


def _balanced_split(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not rows:
        return [], []
    left_count = (len(rows) + 1) // 2
    return _split_rows(rows, left_count)


def _build_driver_rows(standings: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in standings[:limit]:
        driver = item.get("Driver", {}) if isinstance(item.get("Driver"), dict) else {}
        constructors = item.get("Constructors", []) if isinstance(item.get("Constructors"), list) else []
        constructor = constructors[-1] if constructors and isinstance(constructors[-1], dict) else {}
        given = str(driver.get("givenName", "") or "").strip()
        family = str(driver.get("familyName", "") or "").strip()
        code = str(driver.get("code", "") or "").strip()
        short_name = code or (f"{given[:1]}. {family}".strip() if given else family) or "Driver"
        points = str(item.get("points", "0") or "0")
        position = str(item.get("position", "") or "")
        compact_name = code or family or short_name
        rows.append(
            {
                "name": short_name,
                "compact_name": compact_name,
                "team": str(constructor.get("name", "") or "").strip(),
                "points": points,
                "position": position,
                "line": f"{position}. {compact_name} {points}".strip(),
            }
        )
    return rows


def _build_constructor_rows(standings: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in standings[:limit]:
        constructor = item.get("Constructor", {}) if isinstance(item.get("Constructor"), dict) else {}
        name = str(constructor.get("name", "") or "").strip() or "Team"
        constructor_id = str(constructor.get("constructorId", "") or "")
        short_name = _short_constructor_name(name, constructor_id)
        points = str(item.get("points", "0") or "0")
        position = str(item.get("position", "") or "")
        rows.append(
            {
                "name": name,
                "short_name": short_name,
                "points": points,
                "position": position,
                "line": f"{position}. {short_name} {points}".strip(),
            }
        )
    return rows


def _format_gap(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if numeric <= 0:
        return ""
    return f"+{numeric:.3f}"


def _format_time_value(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if numeric <= 0:
        return ""
    minutes = int(numeric // 60)
    seconds = numeric - (minutes * 60)
    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    return f"{seconds:.3f}"


def _build_driver_lookup(standings: list[dict[str, Any]]) -> tuple[dict[str, dict[str, str]], str]:
    lookup: dict[str, dict[str, str]] = {}
    champion_number = ""
    for item in standings:
        driver = item.get("Driver", {}) if isinstance(item.get("Driver"), dict) else {}
        constructors = item.get("Constructors", []) if isinstance(item.get("Constructors"), list) else []
        constructor = constructors[-1] if constructors and isinstance(constructors[-1], dict) else {}
        permanent_number = str(driver.get("permanentNumber", "") or "").strip()
        if not champion_number and permanent_number:
            champion_number = permanent_number
        given = str(driver.get("givenName", "") or "").strip()
        family = str(driver.get("familyName", "") or "").strip()
        code = str(driver.get("code", "") or "").strip()
        if not permanent_number:
            continue
        lookup[permanent_number] = {
            "name": code or (f"{given[:1]}. {family}".strip() if given else family) or permanent_number,
            "surname": family or permanent_number,
            "team": str(constructor.get("name", "") or "").strip(),
            "constructor_id": str(constructor.get("constructorId", "") or "").strip(),
        }
    return lookup, champion_number


async def _fetch_race_weekend_weather(
    *,
    latitude: float,
    longitude: float,
    sessions: list[dict[str, Any]],
    language: str = "en",
) -> list[dict[str, str]]:
    from .context import _weather_code_to_desc

    if not sessions:
        return []

    start_date = str(sessions[0].get("utc_date", "") or "")
    end_date = str(sessions[-1].get("utc_date", "") or "")
    if not start_date or not end_date:
        return []

    try:
        today_utc = datetime.utcnow().date()
        start_dt = datetime.fromisoformat(start_date).date()
    except ValueError:
        return []

    # Open-Meteo forecast does not cover race weekends too far in the future.
    if (start_dt - today_utc).days > 15:
        return []

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "weather_code,temperature_2m",
        "timezone": "UTC",
        "start_date": start_date,
        "end_date": end_date,
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        if resp.status_code >= 400:
            logger.info(
                "[HaloF1] Weekend weather unavailable for %s..%s (status=%s)",
                start_date,
                end_date,
                resp.status_code,
            )
            return []
        payload = resp.json()

    hourly = payload.get("hourly", {}) if isinstance(payload, dict) else {}
    times = hourly.get("time", []) if isinstance(hourly, dict) else []
    codes = hourly.get("weather_code", []) if isinstance(hourly, dict) else []
    temps = hourly.get("temperature_2m", []) if isinstance(hourly, dict) else []
    if not isinstance(times, list) or not isinstance(codes, list) or not isinstance(temps, list):
        return []

    hourly_lookup: dict[str, tuple[int, Any]] = {}
    for idx, raw_time in enumerate(times):
        if idx >= len(codes) or idx >= len(temps):
            break
        key = str(raw_time or "")[:13]
        try:
            code = int(codes[idx])
        except (TypeError, ValueError):
            code = -1
        hourly_lookup[key] = (code, temps[idx])

    rows: list[dict[str, str]] = []
    for session in sessions:
        utc_date = str(session.get("utc_date", "") or "")
        utc_time = str(session.get("utc_time", "") or "").rstrip("Z")
        match_key = f"{utc_date}T{utc_time[:2]}" if utc_date and utc_time else ""
        code, temp = hourly_lookup.get(match_key, (-1, ""))
        try:
            temp_text = f"{round(float(temp))}C"
        except (TypeError, ValueError):
            temp_text = "--"
        desc = _weather_code_to_desc(code, language=language) if code >= 0 else ""
        weather_line = " ".join(part for part in [temp_text, desc] if part).strip()
        rows.append(
            {
                "name": str(session.get("label", "") or ""),
                "when": " ".join(part for part in [str(session.get("date", "") or ""), str(session.get("time", "") or "")] if part).strip(),
                "weather": weather_line,
                "line": "  ".join(part for part in [str(session.get("label", "") or ""), str(session.get("date", "") or ""), str(session.get("time", "") or ""), weather_line] if part).strip(),
            }
        )
    return rows


async def get_halo_f1_snapshot(
    *,
    timezone_name: str = "",
    top_n: int = 20,
    standings_view: str = "both",
) -> dict[str, Any]:
    next_race_data, driver_data, constructor_data = await asyncio.gather(
        _fetch_json(f"{_JOLPICA_BASE}/current/next/races/"),
        _fetch_json(f"{_JOLPICA_BASE}/current/driverstandings/"),
        _fetch_json(f"{_JOLPICA_BASE}/current/constructorstandings/"),
    )

    race_list = (
        next_race_data.get("MRData", {})
        .get("RaceTable", {})
        .get("Races", [])
    )
    race = race_list[0] if isinstance(race_list, list) and race_list else {}

    sessions, next_session = _build_session_list(race, timezone_name)

    driver_lists = (
        driver_data.get("MRData", {})
        .get("StandingsTable", {})
        .get("StandingsLists", [])
    )
    driver_standings = []
    season = ""
    round_name = ""
    if isinstance(driver_lists, list) and driver_lists:
        entry = driver_lists[0]
        season = str(entry.get("season", "") or "")
        round_name = str(entry.get("round", "") or "")
        driver_standings = entry.get("DriverStandings", []) if isinstance(entry.get("DriverStandings", []), list) else []

    constructor_lists = (
        constructor_data.get("MRData", {})
        .get("StandingsTable", {})
        .get("StandingsLists", [])
    )
    constructor_standings = []
    if isinstance(constructor_lists, list) and constructor_lists:
        entry = constructor_lists[0]
        if not season:
            season = str(entry.get("season", "") or "")
        if not round_name:
            round_name = str(entry.get("round", "") or "")
        constructor_standings = entry.get("ConstructorStandings", []) if isinstance(entry.get("ConstructorStandings", []), list) else []

    requested_top_n = max(1, min(_safe_int(top_n, 20), 30))
    driver_limit = len(driver_standings) if driver_standings else requested_top_n
    driver_rows = _build_driver_rows(driver_standings, driver_limit)
    constructor_rows = _build_constructor_rows(constructor_standings, max(10, len(constructor_standings)))
    driver_rows_left, driver_rows_right = _balanced_split(driver_rows)
    constructor_rows_left, constructor_rows_right = _balanced_split(constructor_rows)

    return {
        "season": season or str(datetime.utcnow().year),
        "round": round_name or "?",
        "standings_view": standings_view if standings_view in {"both", "drivers", "constructors"} else "both",
        "race_name": str(race.get("raceName", "") or "Next Grand Prix"),
        "circuit_name": str(((race.get("Circuit") or {}).get("circuitName", "") if isinstance(race.get("Circuit"), dict) else "") or ""),
        "country": str((((race.get("Circuit") or {}).get("Location") or {}).get("country", "") if isinstance((race.get("Circuit") or {}).get("Location"), dict) else "") or ""),
        "is_sprint_weekend": bool(race.get("Sprint")),
        "next_session_label": str(next_session.get("label", "") or "Race"),
        "next_session_date": str(next_session.get("date", "") or ""),
        "next_session_time": str(next_session.get("time", "") or ""),
        "session_summary": f"{next_session.get('label', 'Race')}  {next_session.get('date', '')}  {next_session.get('time', '')}".strip(),
        "driver_rows": driver_rows,
        "constructor_rows": constructor_rows,
        "driver_rows_left": driver_rows_left,
        "driver_rows_right": driver_rows_right,
        "constructor_rows_left": constructor_rows_left,
        "constructor_rows_right": constructor_rows_right,
        "driver_leader": driver_rows[0]["name"] if driver_rows else "",
        "constructor_leader": constructor_rows[0]["name"] if constructor_rows else "",
        "leader_summary": "Leaders: "
        + " · ".join(
            part
            for part in [
                (f"DRV {driver_rows[0]['name']}" if driver_rows else ""),
                (f"CON {constructor_rows[0]['name']}" if constructor_rows else ""),
            ]
            if part
        ),
        "sessions": [
            {
                "name": str(item.get("label", "") or ""),
                "when": " ".join(part for part in [str(item.get("date", "") or ""), str(item.get("time", "") or "")] if part).strip(),
            }
            for item in sessions[:5]
        ],
    }


async def get_halo_f1_news(*, limit: int = 5) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(_F1_NEWS_RSS)
        resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items = root.findall(".//item")
    parsed_items: list[dict[str, str]] = []

    for item in items[: max(1, min(limit, 8))]:
        title = item.findtext("title", default="") or ""
        link = item.findtext("link", default="") or ""
        description = item.findtext("description", default="") or ""
        pub_date = item.findtext("pubDate", default="") or ""
        parsed_items.append(
            {
                "title": _strip_html(title, max_len=120),
                "short_title": _strip_html(title, max_len=72),
                "description": _strip_html(description, max_len=220),
                "link": link.strip(),
                "pub_date": _strip_html(pub_date, max_len=40),
            }
        )

    if not parsed_items:
        return {
            "lead_title": "No F1 headlines available",
            "lead_desc": "Try again in a few minutes.",
            "lead_pub_date": "",
            "news_items": [],
        }

    lead = parsed_items[0]
    return {
        "lead_title": lead.get("title", ""),
        "lead_desc": lead.get("description", ""),
        "lead_pub_date": lead.get("pub_date", ""),
        "news_items": parsed_items[1:],
    }


async def get_halo_f1_results(*, limit: int = 10) -> dict[str, Any]:
    result_data, standings_data = await asyncio.gather(
        _fetch_json(_OPENF1_RESULTS_URL),
        _fetch_json(f"{_JOLPICA_BASE}/current/driverstandings/"),
    )

    result_items = result_data if isinstance(result_data, list) else []
    standings_lists = (
        standings_data.get("MRData", {})
        .get("StandingsTable", {})
        .get("StandingsLists", [])
    )
    driver_standings = []
    if isinstance(standings_lists, list) and standings_lists:
        driver_standings = standings_lists[0].get("DriverStandings", []) if isinstance(standings_lists[0].get("DriverStandings", []), list) else []

    lookup, champion_number = _build_driver_lookup(driver_standings)

    rows: list[dict[str, str]] = []
    is_qualifying = False
    for item in result_items[: max(1, min(limit, 20))]:
        if not isinstance(item, dict):
            continue
        position = str(item.get("position", "") or "").strip()
        driver_number = str(item.get("driver_number", "") or "").strip()
        lookup_key = champion_number if driver_number == "1" and champion_number else driver_number
        driver_info = lookup.get(lookup_key, {})
        display_name = str(driver_info.get("name", "") or driver_number or "Driver")
        detail = ""
        duration = item.get("duration")
        gap_to_leader = item.get("gap_to_leader")
        if isinstance(duration, list):
            is_qualifying = True
            q3 = duration[2] if len(duration) > 2 else duration[-1] if duration else None
            q3_gap = gap_to_leader[2] if isinstance(gap_to_leader, list) and len(gap_to_leader) > 2 else None
            detail = _format_time_value(q3) if position == "1" else _format_gap(q3_gap)
        else:
            detail = _format_time_value(duration) if position == "1" else _format_gap(gap_to_leader)

        rows.append(
            {
                "position": position,
                "driver_number": driver_number,
                "name": display_name,
                "team": str(driver_info.get("team", "") or "").strip(),
                "detail": detail or "",
                "line": " ".join(part for part in [f"{position}.", display_name, detail] if part).strip(),
            }
        )

    session_label = "Qualifying Results" if is_qualifying else "Race Results"
    lead = rows[0] if rows else {}
    result_rows_left, result_rows_right = _balanced_split(rows)
    return {
        "session_label": session_label,
        "leader_name": str(lead.get("name", "") or ""),
        "leader_detail": str(lead.get("detail", "") or ""),
        "result_rows": rows,
        "result_rows_left": result_rows_left,
        "result_rows_right": result_rows_right,
    }


async def get_halo_f1_weekend(*, timezone_name: str = "", language: str = "en") -> dict[str, Any]:
    next_race_data = await _fetch_json(f"{_JOLPICA_BASE}/current/next/races/")
    race_list = (
        next_race_data.get("MRData", {})
        .get("RaceTable", {})
        .get("Races", [])
    )
    race = race_list[0] if isinstance(race_list, list) and race_list else {}
    sessions, next_session = _build_session_list(race, timezone_name)

    circuit = race.get("Circuit", {}) if isinstance(race.get("Circuit"), dict) else {}
    location = circuit.get("Location", {}) if isinstance(circuit.get("Location"), dict) else {}
    try:
        latitude = float(location.get("lat"))
        longitude = float(location.get("long"))
    except (TypeError, ValueError):
        latitude = 0.0
        longitude = 0.0

    weather_rows = []
    if latitude or longitude:
        weather_rows = await _fetch_race_weekend_weather(
            latitude=latitude,
            longitude=longitude,
            sessions=sessions,
            language=language,
        )

    if not weather_rows:
        weather_rows = [
            {
                "name": str(item.get("label", "") or ""),
                "when": " ".join(part for part in [str(item.get("date", "") or ""), str(item.get("time", "") or "")] if part).strip(),
                "weather": "",
                "line": "  ".join(part for part in [str(item.get("label", "") or ""), str(item.get("date", "") or ""), str(item.get("time", "") or "")] if part).strip(),
            }
            for item in sessions
        ]

    return {
        "race_name": str(race.get("raceName", "") or "Formula 1 Weekend"),
        "circuit_name": str(circuit.get("circuitName", "") or ""),
        "country": str(location.get("country", "") or ""),
        "next_session_label": str(next_session.get("label", "") or ""),
        "next_session_time": str(next_session.get("time", "") or ""),
        "weekend_rows": weather_rows,
    }
