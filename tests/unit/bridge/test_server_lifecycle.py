"""Tests for BridgeServer lifecycle methods (initialize/shutdown/exit)."""

from __future__ import annotations

import asyncio
import json

import pytest

from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer


class _FakeRuntime:
    """Bare-minimum stand-in for AgentRuntime."""


async def _drive_one(server: BridgeServer, request: dict) -> dict:
    """Feed one request through the server, return parsed response."""
    reader = asyncio.StreamReader()
    payload = json.dumps(request).encode() + b"\n"
    reader.feed_data(payload)
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
    lines = [ln for ln in b"".join(write_buf).split(b"\n") if ln]
    assert len(lines) == 1
    return json.loads(lines[0])


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    server = BridgeServer(
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test-bridge", "version": "0.0.1"},
    )
    resp = await _drive_one(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"client_info": {"name": "test-client"}, "protocol_version": 1},
        },
    )
    assert resp["id"] == 1
    assert "result" in resp
    assert resp["result"]["server_info"]["name"] == "test-bridge"


@pytest.mark.asyncio
async def test_unknown_method_returns_method_not_found() -> None:
    server = BridgeServer(
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "x", "version": "0"},
    )
    resp = await _drive_one(
        server, {"jsonrpc": "2.0", "id": 2, "method": "totally_made_up"}
    )
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_shutdown_then_exit_terminates_loop() -> None:
    server = BridgeServer(
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "x", "version": "0"},
    )
    reader = asyncio.StreamReader()
    reader.feed_data(
        b'{"jsonrpc":"2.0","id":1,"method":"shutdown"}\n'
        b'{"jsonrpc":"2.0","method":"exit"}\n'
    )
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
    lines = [ln for ln in b"".join(write_buf).split(b"\n") if ln]
    # shutdown gets a response; exit is a notification (no response)
    assert len(lines) == 1
    assert json.loads(lines[0])["result"] is None


@pytest.mark.asyncio
async def test_request_after_shutdown_returns_error() -> None:
    server = BridgeServer(
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "x", "version": "0"},
    )
    reader = asyncio.StreamReader()
    reader.feed_data(
        b'{"jsonrpc":"2.0","id":1,"method":"shutdown"}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"initialize"}\n'
        b'{"jsonrpc":"2.0","method":"exit"}\n'
    )
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
    lines = [json.loads(ln) for ln in b"".join(write_buf).split(b"\n") if ln]
    # shutdown response (id=1) and shutting-down error for initialize (id=2)
    assert len(lines) == 2
    assert lines[0]["id"] == 1 and lines[0]["result"] is None
    assert lines[1]["id"] == 2 and lines[1]["error"]["code"] == -32003
