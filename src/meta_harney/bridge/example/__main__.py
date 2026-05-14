"""Runnable bridge example with a hand-rolled mini runtime.

Usage::

    python -m meta_harney.bridge.example

The runtime stub is intentionally minimal — just enough surface area for the
subprocess integration test to drive the full JSON-RPC lifecycle without
pulling in a real LLM provider or tool stack. Each emitted "stream event" is
a tiny duck-typed object exposing ``model_dump()``, which is all
``BridgeServer._serialize_event`` requires.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session.memory_store import MemorySessionStore


class _FakeEvent:
    """Duck-typed StreamEvent: only ``model_dump()`` is needed for JSON wire."""

    def __init__(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        self.kind = kind
        self.payload: dict[str, Any] = payload or {}

    def model_dump(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.payload}


class _MiniRuntime:
    """Hand-rolled runtime stub.

    Implements only what the bridge actually touches:
      - ``create_session`` (saves to MemorySessionStore, returns the Session)
      - ``stream`` (async generator yielding a few fake events)
      - ``_session_store`` (used by ``session.list`` / ``session.load`` handlers)
      - ``_tools`` (used by ``tools.list`` handler)
    """

    def __init__(self) -> None:
        self._session_store: MemorySessionStore = MemorySessionStore()
        self._tools: dict[str, Any] = {}

    async def create_session(
        self,
        *,
        session_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        sid = session_id or "sess-bridge-example"
        s = Session(
            id=sid,
            tenant_id=tenant_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            attributes=dict(attributes) if attributes else {},
            metadata=dict(metadata) if metadata else {},
        )
        await self._session_store.save(s)
        return s

    async def stream(
        self,
        session_id: str,
        message: Any,
        **kwargs: Any,
    ) -> AsyncGenerator[_FakeEvent, None]:
        # Emit a small, deterministic event sequence so the integration test
        # can count notifications without flakiness.
        yield _FakeEvent("text_delta", {"text": "hello"})
        yield _FakeEvent("text_delta", {"text": " from bridge example"})
        yield _FakeEvent("turn_completed", {"total_iterations": 1})


async def _amain() -> None:
    runtime = _MiniRuntime()
    server = BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "meta-harney-bridge-example", "version": "0.1.0"},
    )
    await server.serve_stdio()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
