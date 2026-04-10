"""Short-lived database connection helpers for SQLite or Neon/Postgres."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import weakref
from typing import Any, Sequence

import aiosqlite

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(__file__), "..")
_MAIN_DB_PATH = os.path.join(_DB_DIR, os.getenv("DB_PATH", "inksight.db"))
_CACHE_DB_PATH = os.path.join(_DB_DIR, os.getenv("CACHE_DB_PATH", "cache.db"))
_live_connections: "weakref.WeakSet[_ManagedConnection]" = weakref.WeakSet()


def get_db_backend() -> str:
    backend = (os.getenv("INKSIGHT_DB_BACKEND", "") or os.getenv("DB_BACKEND", "sqlite")).strip().lower()
    if backend == "neon":
        return "postgres"
    if backend == "postgres":
        return "postgres"
    return "sqlite"


def is_postgres_backend() -> bool:
    return get_db_backend() == "postgres"


def _with_returning_id(sql: str) -> str:
    if re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
        return sql
    return f"{sql.rstrip().rstrip(';')} RETURNING id"


class _ManagedConnection:
    """Proxy that closes the underlying database connection when released."""

    def __init__(self, conn, label: str):
        self._conn = conn
        self._label = label
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        await self._conn.close()

    def __del__(self):  # pragma: no cover - best-effort cleanup
        if self._closed:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.close())


async def _open_db(path: str, label: str) -> _ManagedConnection:
    conn = await aiosqlite.connect(path)
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass
    managed = _ManagedConnection(conn, label)
    _live_connections.add(managed)
    logger.debug("[DB] Opened %s connection", label)
    return managed


async def get_main_db() -> _ManagedConnection:
    return await _open_db(_MAIN_DB_PATH, "main")


async def get_cache_db() -> _ManagedConnection:
    return await _open_db(_CACHE_DB_PATH, "cache")


async def execute_insert_returning_id(
    db: _ManagedConnection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> Any:
    cursor = await db.execute(_with_returning_id(sql) if is_postgres_backend() else sql, params or ())
    if is_postgres_backend():
        row = await cursor.fetchone()
        return row[0] if row else None
    return cursor.lastrowid


async def close_all():
    pending = [conn.close() for conn in list(_live_connections)]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _live_connections.clear()
