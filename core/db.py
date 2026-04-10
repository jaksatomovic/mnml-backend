"""Short-lived database connection helpers for Neon/Postgres."""
from __future__ import annotations

import asyncio
import logging
import re
import weakref
from typing import Any, Sequence

import aiosqlite

logger = logging.getLogger(__name__)

_live_connections: "weakref.WeakSet[_ManagedConnection]" = weakref.WeakSet()


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


async def _open_db(label: str) -> _ManagedConnection:
    conn = await aiosqlite.connect("")
    managed = _ManagedConnection(conn, label)
    _live_connections.add(managed)
    logger.debug("[DB] Opened %s connection", label)
    return managed


async def get_main_db() -> _ManagedConnection:
    return await _open_db("main")


async def get_cache_db() -> _ManagedConnection:
    return await _open_db("cache")


async def execute_insert_returning_id(
    db: _ManagedConnection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> Any:
    cursor = await db.execute(_with_returning_id(sql), params or ())
    row = await cursor.fetchone()
    return row[0] if row else None


async def close_all():
    pending = [conn.close() for conn in list(_live_connections)]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _live_connections.clear()
