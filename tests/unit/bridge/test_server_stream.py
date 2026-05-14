"""Tests for session.send_message + stream/event notifications."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import pytest

from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session.memory_store import MemorySessionStore


class _FakeStreamEvent:
    """Stand-in for a StreamEvent — only model_dump matters for serialization."""

    def __init__(self, kind: str, data: dict[str, Any]) -> None:
        self.kind = kind
        self.data = data

    def model_dump(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}


class _StreamingRuntime:
    """Runtime that emits N fake stream events."""

    def __init__(self, store: MemorySessionStore, events: list[Any]) -> None:
        self._session_store = store
        self._events = events
        self.received_messages: list[Any] = []

    async def create_session(self, **kwargs: Any) -> Session:
        sid = kwargs.get("session_id") or "s"
        s = Session(id=sid, created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s

    async def stream(
        self, session_id: str, message: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        self.received_messages.append(message)
        for ev in self._events:
            yield ev


def _make_server(events: list[Any]) -> tuple[BridgeServer, _StreamingRuntime]:
    store = MemorySessionStore()
    runtime = _StreamingRuntime(store, events)
    server = BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )
    return server, runtime


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
async def test_send_message_emits_stream_events_then_final_response() -> None:
    events = [
        _FakeStreamEvent("text_delta", {"text": "hello"}),
        _FakeStreamEvent("text_delta", {"text": " world"}),
        _FakeStreamEvent("turn_completed", {"total_iterations": 1}),
    ]
    server, _runtime = _make_server(events)
    msgs = await _drive(
        server,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "session.create"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session.send_message",
                "params": {
                    "session_id": "s",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hi"}],
                    },
                },
            },
        ],
    )
    # Expected: create response (id=1), 3 stream/event notifications (no id),
    # then final send_message response (id=2)
    create_resps = [m for m in msgs if m.get("id") == 1]
    send_resps = [m for m in msgs if m.get("id") == 2]
    stream_notes = [m for m in msgs if m.get("method") == "stream/event"]
    assert len(create_resps) == 1
    assert len(send_resps) == 1
    assert len(stream_notes) == 3
    # Each notification embeds the originating request id (=2)
    assert all(n["params"]["request_id"] == 2 for n in stream_notes)
    # Stream events arrive BEFORE the final send_message response in wire order.
    send_idx = next(i for i, m in enumerate(msgs) if m.get("id") == 2)
    stream_indices = [i for i, m in enumerate(msgs) if m.get("method") == "stream/event"]
    assert all(i < send_idx for i in stream_indices)
    # The final response carries stopped_reason
    assert send_resps[0]["result"] is not None
    assert send_resps[0]["result"].get("stopped_reason") == "completed"
    # Stream event payload preserves the kind/data via model_dump
    kinds = [n["params"]["event"]["kind"] for n in stream_notes]
    assert kinds == ["text_delta", "text_delta", "turn_completed"]


@pytest.mark.asyncio
async def test_send_message_invalid_params_returns_error() -> None:
    server, _runtime = _make_server([])
    msgs = await _drive(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session.send_message",
                "params": {"session_id": "s"},  # missing message
            }
        ],
    )
    assert len(msgs) == 1
    # InvalidParams is JSON-RPC -32602
    assert msgs[0]["error"]["code"] == -32602
