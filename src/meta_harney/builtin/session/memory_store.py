"""MemorySessionStore — in-process dict-backed store.

Suitable for tests, single-process demos, and as the default when no
persistent store is configured. NOT suitable for production: all state
lost on process exit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from meta_harney.abstractions.session import Session
from meta_harney.errors import SessionConflictError


class MemorySessionStore:
    """In-memory SessionStore with optimistic locking and tenant filtering."""

    def __init__(self) -> None:
        self._data: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None:
        async with self._lock:
            s = self._data.get(session_id)
            if s is None:
                return None
            if tenant_id is not None and s.tenant_id != tenant_id:
                return None
            return s.model_copy(deep=True)

    async def save(self, session: Session) -> None:
        async with self._lock:
            existing = self._data.get(session.id)
            if existing is not None and existing.version != session.version:
                raise SessionConflictError(
                    session_id=session.id,
                    expected_version=session.version,
                    found_version=existing.version,
                )
            session.version += 1
            self._data[session.id] = session.model_copy(deep=True)

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]:
        async with self._lock:
            results = list(self._data.values())
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        if filter:
            for k, v in filter.items():
                results = [s for s in results if s.attributes.get(k) == v]
        return [s.model_copy(deep=True) for s in results]

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._data.pop(session_id, None)
