"""Tests for session.create / session.list / session.load handlers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session.memory_store import MemorySessionStore


class _MinimalRuntime:
    """AgentRuntime stand-in that owns a real SessionStore."""

    def __init__(self, store: MemorySessionStore) -> None:
        self._session_store = store

    async def create_session(self, **kwargs: Any) -> Session:
        sid = kwargs.get("session_id") or "sess-fixed"
        s = Session(id=sid, created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s


def _make_server() -> tuple[BridgeServer, MemorySessionStore]:
    store = MemorySessionStore()
    runtime = _MinimalRuntime(store)
    server = BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )
    return server, store


async def _drive(server: BridgeServer, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reader = asyncio.StreamReader()
    for ln in lines:
        reader.feed_data(json.dumps(ln).encode() + b"\n")
    reader.feed_eof()

    write_buf: list[bytes] = []

    class _W:
        def write(self, data: bytes) -> None:
            write_buf.append(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    await server.serve(reader, _W())  # type: ignore[arg-type]
    return [json.loads(b) for b in b"".join(write_buf).split(b"\n") if b]


@pytest.mark.asyncio
async def test_session_create_returns_id() -> None:
    server, _ = _make_server()
    resps = await _drive(
        server,
        [{"jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {}}],
    )
    assert resps[0]["id"] == 1
    assert "id" in resps[0]["result"]
    assert "created_at" in resps[0]["result"]


@pytest.mark.asyncio
async def test_session_list_returns_summaries() -> None:
    server, store = _make_server()
    # Pre-seed two sessions
    now = datetime.now(timezone.utc)
    await store.save(Session(id="a", created_at=now))
    await store.save(
        Session(
            id="b",
            created_at=now,
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
        )
    )
    resps = await _drive(
        server, [{"jsonrpc": "2.0", "id": 1, "method": "session.list"}]
    )
    summaries = resps[0]["result"]
    ids = sorted(s["id"] for s in summaries)
    assert ids == ["a", "b"]
    for s in summaries:
        assert "message_count" in s and "created_at" in s


@pytest.mark.asyncio
async def test_session_load_returns_messages() -> None:
    server, store = _make_server()
    now = datetime.now(timezone.utc)
    await store.save(
        Session(
            id="x",
            created_at=now,
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
        )
    )
    resps = await _drive(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session.load",
                "params": {"session_id": "x"},
            }
        ],
    )
    result = resps[0]["result"]
    assert result["id"] == "x"
    assert isinstance(result["messages"], list)
    assert len(result["messages"]) == 1


@pytest.mark.asyncio
async def test_session_load_missing_returns_session_not_found() -> None:
    server, _ = _make_server()
    resps = await _drive(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session.load",
                "params": {"session_id": "nope"},
            }
        ],
    )
    assert resps[0]["error"]["code"] == -32000
