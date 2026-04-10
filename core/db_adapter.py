from __future__ import annotations

import logging
import os
import re
from typing import Any, Sequence

logger = logging.getLogger(__name__)
_BACKEND = "postgres"

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg = None


class Error(Exception):
    pass


class IntegrityError(Error):
    pass


class OperationalError(Error):
    pass


def _translate_qmark_placeholders(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _convert_legacy_ddl_to_postgres(sql: str) -> str:
    converted = sql
    converted = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(r"\bBLOB\b", "BYTEA", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bBOOLEAN\s+DEFAULT\s+1\b", "BOOLEAN DEFAULT TRUE", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bBOOLEAN\s+DEFAULT\s+0\b", "BOOLEAN DEFAULT FALSE", converted, flags=re.IGNORECASE)
    return converted


def _extract_insert_table(sql: str) -> str | None:
    match = re.search(r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
    return match.group(1).lower() if match else None


_SERIAL_ID_TABLES = {
    "configs",
    "users",
    "invitation_codes",
    "user_devices",
    "device_memberships",
    "device_access_requests",
    "push_tokens",
    "shared_modes",
    "custom_modes",
    "render_logs",
    "device_heartbeats",
    "content_history",
    "habit_records",
}


class _PostgresCursor:
    def __init__(self, cursor: Any, *, lastrowid: Any = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    async def fetchone(self):
        return await self._cursor.fetchone()

    async def fetchall(self):
        return await self._cursor.fetchall()


class _PostgresConnection:
    def __init__(self, conn: Any):
        self._conn = conn

    async def execute(self, sql: str, params: Sequence[Any] | None = None):
        params = tuple(params or ())
        stripped = sql.strip()
        upper = stripped.upper()

        insert_or_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", stripped, re.IGNORECASE))
        translated = _translate_qmark_placeholders(_convert_legacy_ddl_to_postgres(sql))
        if insert_or_ignore:
            translated = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", translated, flags=re.IGNORECASE)
            translated = f"{translated.rstrip()} ON CONFLICT DO NOTHING"

        table = _extract_insert_table(stripped)
        should_return_id = (
            table in _SERIAL_ID_TABLES
            and stripped.upper().startswith("INSERT")
            and "RETURNING" not in upper
        )
        if should_return_id:
            translated = f"{translated.rstrip()} RETURNING id"

        try:
            cursor = await self._conn.execute(translated, params)
            if should_return_id:
                row = await cursor.fetchone()
                return _PostgresCursor(cursor, lastrowid=(row[0] if row else None))
            return _PostgresCursor(cursor)
        except Exception as exc:  # pragma: no cover - mapped for runtime compatibility
            if psycopg is not None:
                if isinstance(exc, psycopg.IntegrityError):
                    raise IntegrityError(str(exc)) from exc
                if isinstance(exc, psycopg.OperationalError):
                    raise OperationalError(str(exc)) from exc
                if isinstance(exc, psycopg.Error):
                    raise Error(str(exc)) from exc
            raise

    async def commit(self):
        await self._conn.commit()

    async def rollback(self):
        await self._conn.rollback()

    async def close(self):
        await self._conn.close()


async def connect(database: str, *args, **kwargs):
    if psycopg is None:
        raise OperationalError(
            "psycopg is not installed. Add psycopg[binary] to requirements."
        )

    dsn = os.getenv("DATABASE_URL", "").strip() or os.getenv("NEON_DATABASE_URL", "").strip() or database
    if not dsn:
        raise OperationalError("DATABASE_URL is required for database connectivity.")

    try:
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=False)
    except Exception as exc:  # pragma: no cover - runtime connectivity
        raise OperationalError(str(exc)) from exc
    return _PostgresConnection(conn)


Connection = Any
