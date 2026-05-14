"""Tests for $/cancelRequest notification and session.cancel request."""

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


class _SlowEvent:
    def model_dump(self) -> dict[str, Any]:
        return {"kind": "tick"}


class _SlowRuntime:
    """Stream that emits one event every 50ms — long enough to be cancellable."""

    def __init__(self, store: MemorySessionStore) -> None:
        self._session_store = store

    async def create_session(self, **kwargs: Any) -> Session:
        sid = kwargs.get("session_id") or "s"
        s = Session(id=sid, created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s

    async def stream(
        self, session_id: str, message: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        for _ in range(100):
            await asyncio.sleep(0.05)
            yield _SlowEvent()


def _make_server() -> BridgeServer:
    store = MemorySessionStore()
    runtime = _SlowRuntime(store)
    return BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )


class _W:
    """Captures bytes written; mimics asyncio.StreamWriter surface used by server."""

    def __init__(self) -> None:
        self.buf: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.buf.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


async def _drive_with_delay(
    server: BridgeServer,
    initial_lines: list[dict[str, Any]],
    delayed: list[tuple[float, dict[str, Any]]],
) -> list[dict[str, Any]]:
    reader = asyncio.StreamReader()
    for ln in initial_lines:
        reader.feed_data(json.dumps(ln).encode() + b"\n")

    async def feeder() -> None:
        for delay, ln in delayed:
            await asyncio.sleep(delay)
            reader.feed_data(json.dumps(ln).encode() + b"\n")
        reader.feed_eof()

    writer = _W()
    feeder_task = asyncio.create_task(feeder())
    await server.serve(reader, writer)  # type: ignore[arg-type]
    await feeder_task
    return [json.loads(b) for b in b"".join(writer.buf).split(b"\n") if b]


@pytest.mark.asyncio
async def test_dollar_cancel_request_cancels_inflight_stream() -> None:
    """$/cancelRequest is a notification; it must cancel the matching in-flight
    request and the cancelled handler must produce a Cancelled error response
    (code -32002), NOT a 500 internal error."""
    server = _make_server()
    msgs = await _drive_with_delay(
        server,
        [{"jsonrpc": "2.0", "id": 1, "method": "session.create"}],
        [
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session.send_message",
                    "params": {
                        "session_id": "s",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "x"}],
                        },
                    },
                },
            ),
            (0.12, {"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": 2}}),
        ],
    )
    # The send_message request must receive an error response with the Cancelled
    # code, and the cancel notification itself must NOT have produced a response.
    send_resp = next((m for m in msgs if m.get("id") == 2), None)
    assert send_resp is not None
    assert "error" in send_resp
    assert send_resp["error"]["code"] == -32002
    # No response with method=$/cancelRequest in the output (notifications never
    # produce responses).
    cancel_resps = [m for m in msgs if m.get("method") == "$/cancelRequest"]
    assert cancel_resps == []


@pytest.mark.asyncio
async def test_session_cancel_request_returns_true_when_inflight() -> None:
    """session.cancel is a request; for an in-flight target it returns
    {"cancelled": true} and triggers cancellation of the underlying task."""
    server = _make_server()
    msgs = await _drive_with_delay(
        server,
        [{"jsonrpc": "2.0", "id": 1, "method": "session.create"}],
        [
            (
                0.0,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session.send_message",
                    "params": {
                        "session_id": "s",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "x"}],
                        },
                    },
                },
            ),
            (
                0.12,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "session.cancel",
                    "params": {"request_id": 2},
                },
            ),
        ],
    )
    cancel_resp = next((m for m in msgs if m.get("id") == 3), None)
    assert cancel_resp is not None
    assert cancel_resp.get("result") == {"cancelled": True}
    # And the cancelled send_message should ultimately resolve with a Cancelled
    # error so the parent doesn't hang waiting.
    send_resp = next((m for m in msgs if m.get("id") == 2), None)
    assert send_resp is not None
    assert send_resp.get("error", {}).get("code") == -32002


@pytest.mark.asyncio
async def test_session_cancel_unknown_id_returns_false() -> None:
    """Unknown request_id must return {"cancelled": false} (NOT an error)."""
    server = _make_server()
    reader = asyncio.StreamReader()
    reader.feed_data(
        b'{"jsonrpc":"2.0","id":1,"method":"session.cancel","params":{"request_id":999}}\n'
    )
    reader.feed_eof()
    writer = _W()
    await server.serve(reader, writer)  # type: ignore[arg-type]
    msgs = [json.loads(b) for b in b"".join(writer.buf).split(b"\n") if b]
    assert len(msgs) == 1
    assert "error" not in msgs[0]
    assert msgs[0]["result"] == {"cancelled": False}
