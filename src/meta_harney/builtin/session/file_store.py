"""FileSessionStore — one JSON file per session.

Per-session asyncio.Lock prevents intra-process concurrent writes from
corrupting the same file. Cross-process safety is NOT guaranteed —
use a real database for that.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any

from meta_harney.abstractions.session import Session
from meta_harney.errors import SessionConflictError, SessionStoreError


class FileSessionStore:
    """File-backed SessionStore: one JSON file per session under `root`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _path(self, session_id: str) -> Path:
        # Defensive: prevent traversal via session_id
        if "/" in session_id or ".." in session_id:
            raise SessionStoreError(f"invalid session_id: {session_id!r}")
        return self.root / f"{session_id}.json"

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            raise SessionStoreError(f"failed to read {path}: {e}") from e
        s = Session.model_validate_json(raw)
        if tenant_id is not None and s.tenant_id != tenant_id:
            return None
        return s

    async def save(self, session: Session) -> None:
        path = self._path(session.id)
        async with self._locks[session.id]:
            if path.exists():
                existing = Session.model_validate_json(path.read_text(encoding="utf-8"))
                if existing.version != session.version:
                    raise SessionConflictError(
                        session_id=session.id,
                        expected_version=session.version,
                        found_version=existing.version,
                    )
            session.version += 1
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(session.model_dump_json(), encoding="utf-8")
            tmp.replace(path)  # atomic on POSIX

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]:
        results: list[Session] = []
        for p in self.root.glob("*.json"):
            try:
                s = Session.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                continue  # skip corrupt
            if tenant_id is not None and s.tenant_id != tenant_id:
                continue
            if filter:
                if not all(s.attributes.get(k) == v for k, v in filter.items()):
                    continue
            results.append(s)
        return results

    async def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
