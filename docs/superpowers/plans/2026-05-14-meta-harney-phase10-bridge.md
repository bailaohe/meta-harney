# Phase 10 Implementation Plan — `meta_harney.bridge`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `meta_harney.bridge` — a JSON-RPC 2.0 server that exposes `AgentRuntime` to non-Python parent processes over stdio. Full scope: framing × 2, lifecycle, sessions, streaming, cancel, permissions, telemetry.

**Architecture:** Parent spawns Python child; bidirectional JSON-RPC over stdin/stdout. Two framings (newline / content-length). `BridgeServer` owns dispatch, lifecycle, and writer queue. `BridgePermissionResolver` + `BridgeTraceSink` plug into the runtime to forward upstream.

**Tech Stack:** Python 3.10+, asyncio, pydantic v2, json stdlib, pytest, mypy strict, ruff.

**Spec:** `docs/superpowers/specs/2026-05-14-meta-harney-phase10-bridge-design.md`

**Repo:** `/Users/baihe/Projects/study/meta-harney` (branch `main`)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/meta_harney/bridge/__init__.py` | Create | Public exports |
| `src/meta_harney/bridge/errors.py` | Create | JSON-RPC error codes + BridgeError hierarchy |
| `src/meta_harney/bridge/framing.py` | Create | `Framing` Protocol + `NewlineFraming` + `ContentLengthFraming` |
| `src/meta_harney/bridge/protocol.py` | Create | JSON-RPC 2.0 pydantic models |
| `src/meta_harney/bridge/permission.py` | Create | `BridgePermissionResolver` |
| `src/meta_harney/bridge/trace.py` | Create | `BridgeTraceSink` |
| `src/meta_harney/bridge/server.py` | Create | `BridgeServer` orchestrator |
| `src/meta_harney/bridge/example/__main__.py` | Create | Runnable bridge with FakeLLMProvider — for subprocess test |
| `src/meta_harney/__init__.py` | Modify | Bump version to `0.1.0`; export bridge surface |
| `pyproject.toml` | Modify | `version = "0.1.0"` |
| `tests/unit/bridge/test_framing.py` | Create | Framing round-trip |
| `tests/unit/bridge/test_protocol.py` | Create | Protocol model round-trip |
| `tests/unit/bridge/test_server_lifecycle.py` | Create | initialize / shutdown / exit |
| `tests/unit/bridge/test_server_sessions.py` | Create | session.create / list / load |
| `tests/unit/bridge/test_server_stream.py` | Create | session.send_message stream events |
| `tests/unit/bridge/test_server_cancel.py` | Create | $/cancelRequest + session.cancel |
| `tests/unit/bridge/test_permission.py` | Create | BridgePermissionResolver |
| `tests/unit/bridge/test_trace.py` | Create | BridgeTraceSink subscribe |
| `tests/integration/bridge/test_subprocess.py` | Create | Real subprocess full lifecycle |

---

### Task 1: Framing layer (newline + content-length)

**Files:**
- Create: `src/meta_harney/bridge/__init__.py` (empty for now)
- Create: `src/meta_harney/bridge/framing.py`
- Create: `tests/unit/bridge/__init__.py` (empty)
- Test: `tests/unit/bridge/test_framing.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_framing.py`:

```python
"""Tests for newline and content-length framings."""

from __future__ import annotations

import asyncio
import io

import pytest

from meta_harney.bridge.framing import ContentLengthFraming, NewlineFraming


async def _drain_to_bytes(coros) -> bytes:
    """Helper: pump a list of writes through a pipe and collect bytes."""
    rd, wr = io.BytesIO(), io.BytesIO()
    for c in coros:
        await c
    return wr.getvalue()


@pytest.mark.asyncio
async def test_newline_framing_writes_one_line(tmp_path) -> None:
    framing = NewlineFraming()
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"a":1}\n')
    reader.feed_eof()
    msg = await framing.read_message(reader)
    assert msg == b'{"a":1}'


@pytest.mark.asyncio
async def test_newline_framing_round_trip() -> None:
    framing = NewlineFraming()
    payload = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    # write side
    transport_buf = io.BytesIO()
    # use a simple writer shim that records into transport_buf
    class _Writer:
        def write(self, data: bytes) -> None:
            transport_buf.write(data)
        async def drain(self) -> None:
            return None
    await framing.write_message(_Writer(), payload)  # type: ignore[arg-type]
    written = transport_buf.getvalue()
    assert written == payload + b"\n"

    reader = asyncio.StreamReader()
    reader.feed_data(written)
    reader.feed_eof()
    out = await framing.read_message(reader)
    assert out == payload


@pytest.mark.asyncio
async def test_newline_framing_eof_returns_none() -> None:
    framing = NewlineFraming()
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await framing.read_message(reader) is None


@pytest.mark.asyncio
async def test_content_length_framing_round_trip() -> None:
    framing = ContentLengthFraming()
    payload = b'{"large":"' + b"x" * 1024 + b'"}'
    transport_buf = io.BytesIO()
    class _Writer:
        def write(self, data: bytes) -> None:
            transport_buf.write(data)
        async def drain(self) -> None:
            return None
    await framing.write_message(_Writer(), payload)  # type: ignore[arg-type]
    written = transport_buf.getvalue()
    assert written.startswith(b"Content-Length: ")
    assert payload in written

    reader = asyncio.StreamReader()
    reader.feed_data(written)
    reader.feed_eof()
    out = await framing.read_message(reader)
    assert out == payload


@pytest.mark.asyncio
async def test_content_length_framing_handles_multi_message_stream() -> None:
    framing = ContentLengthFraming()
    bufs = []
    class _Writer:
        def write(self, data: bytes) -> None:
            bufs.append(data)
        async def drain(self) -> None:
            return None
    w = _Writer()
    await framing.write_message(w, b'{"a":1}')  # type: ignore[arg-type]
    await framing.write_message(w, b'{"b":2}')  # type: ignore[arg-type]

    reader = asyncio.StreamReader()
    reader.feed_data(b"".join(bufs))
    reader.feed_eof()
    a = await framing.read_message(reader)
    b = await framing.read_message(reader)
    assert a == b'{"a":1}'
    assert b == b'{"b":2}'


@pytest.mark.asyncio
async def test_content_length_framing_eof_returns_none() -> None:
    framing = ContentLengthFraming()
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await framing.read_message(reader) is None
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/pytest tests/unit/bridge/test_framing.py -v`
Expected: ImportError — `meta_harney.bridge.framing` does not exist.

- [ ] **Step 3: Implement framing**

Create `src/meta_harney/bridge/__init__.py` (empty, will populate at the end):

```python
"""meta_harney.bridge — JSON-RPC over stdio for AgentRuntime."""
```

Create `src/meta_harney/bridge/framing.py`:

```python
"""Framing strategies for the bridge transport.

Two framings are supported. Callers pick one when constructing BridgeServer.

- NewlineFraming: one JSON object per `\n`-terminated line. Debuggable with cat.
- ContentLengthFraming: LSP-style `Content-Length: N\r\n\r\n<bytes>`.
"""

from __future__ import annotations

import asyncio
from typing import Protocol


class Framing(Protocol):
    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        """Read one complete message. Return None on EOF before any bytes."""
        ...

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        """Frame and write one message. Caller is responsible for flushing if needed."""
        ...


class NewlineFraming:
    """Newline-delimited JSON. One message per line, terminated by '\\n'."""

    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        line = await reader.readline()
        if not line:
            return None
        # Strip the trailing newline (always exactly one '\n', no '\r')
        return line.rstrip(b"\r\n")

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        writer.write(payload + b"\n")
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()


class ContentLengthFraming:
    """LSP-style framing: `Content-Length: N\\r\\n\\r\\n<N bytes>`."""

    _HEADER_TERMINATOR = b"\r\n\r\n"

    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        # Read header lines until blank line
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line:
                return None
            if line == b"\r\n" or line == b"\n":
                break
            try:
                k, _, v = line.decode("ascii", errors="replace").partition(":")
            except Exception:
                continue
            headers[k.strip().lower()] = v.strip()

        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"missing or invalid Content-Length header: {headers!r}") from exc

        body = await reader.readexactly(length)
        return body

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        writer.write(header + payload)
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()
```

Also create empty `tests/unit/bridge/__init__.py`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/test_framing.py -v`
Expected: 6 pass.

Run: `.venv/bin/mypy src/meta_harney/bridge tests/unit/bridge`
Expected: clean.

Run: `.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/__init__.py src/meta_harney/bridge/framing.py tests/unit/bridge/
git commit -m "feat(bridge): NewlineFraming + ContentLengthFraming"
```

---

### Task 2: JSON-RPC protocol models + errors

**Files:**
- Create: `src/meta_harney/bridge/errors.py`
- Create: `src/meta_harney/bridge/protocol.py`
- Test: `tests/unit/bridge/test_protocol.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_protocol.py`:

```python
"""Tests for JSON-RPC 2.0 protocol models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from meta_harney.bridge.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_incoming,
)


def test_request_roundtrip() -> None:
    r = JsonRpcRequest(id=1, method="ping", params={"x": 1})
    raw = r.model_dump_json()
    parsed = JsonRpcRequest.model_validate_json(raw)
    assert parsed == r
    assert parsed.jsonrpc == "2.0"


def test_response_success_roundtrip() -> None:
    r = JsonRpcResponse(id=1, result={"pong": True})
    raw = r.model_dump_json()
    parsed = JsonRpcResponse.model_validate_json(raw)
    assert parsed.result == {"pong": True}
    assert parsed.error is None


def test_response_error_roundtrip() -> None:
    err = JsonRpcError(code=-32601, message="method not found")
    r = JsonRpcResponse(id=1, error=err)
    parsed = JsonRpcResponse.model_validate_json(r.model_dump_json())
    assert parsed.error is not None
    assert parsed.error.code == -32601


def test_notification_has_no_id() -> None:
    n = JsonRpcNotification(method="$/cancelRequest", params={"id": 7})
    raw = json.loads(n.model_dump_json())
    assert "id" not in raw
    assert raw["method"] == "$/cancelRequest"


def test_parse_incoming_dispatches_by_shape() -> None:
    # request
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"method":"ping"}')
    assert isinstance(msg, JsonRpcRequest)
    # response with result
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"result":42}')
    assert isinstance(msg, JsonRpcResponse)
    # response with error
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"x"}}')
    assert isinstance(msg, JsonRpcResponse)
    # notification (no id)
    msg = parse_incoming(b'{"jsonrpc":"2.0","method":"hello"}')
    assert isinstance(msg, JsonRpcNotification)


def test_parse_incoming_rejects_non_jsonrpc() -> None:
    with pytest.raises(ValueError):
        parse_incoming(b"not json")


def test_parse_incoming_rejects_missing_jsonrpc_field() -> None:
    with pytest.raises(ValueError):
        parse_incoming(b'{"id":1,"method":"ping"}')
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/pytest tests/unit/bridge/test_protocol.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement errors + protocol**

Create `src/meta_harney/bridge/errors.py`:

```python
"""JSON-RPC error codes + bridge-specific exception hierarchy."""

from __future__ import annotations

# Standard JSON-RPC 2.0 codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Bridge-specific codes (in the implementation-defined server-error range)
SESSION_NOT_FOUND = -32000
PERMISSION_DENIED = -32001
CANCELLED = -32002
SHUTDOWN = -32003


class BridgeError(Exception):
    """Base for bridge-specific exceptions. Carries a JSON-RPC error code."""

    code: int = INTERNAL_ERROR

    def __init__(self, message: str = "", *, data: object | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.data = data


class ParseError(BridgeError):
    code = PARSE_ERROR


class InvalidRequest(BridgeError):
    code = INVALID_REQUEST


class MethodNotFound(BridgeError):
    code = METHOD_NOT_FOUND


class InvalidParams(BridgeError):
    code = INVALID_PARAMS


class InternalError(BridgeError):
    code = INTERNAL_ERROR


class SessionNotFound(BridgeError):
    code = SESSION_NOT_FOUND


class PermissionDenied(BridgeError):
    code = PERMISSION_DENIED


class Cancelled(BridgeError):
    code = CANCELLED


class ShuttingDown(BridgeError):
    code = SHUTDOWN
```

Create `src/meta_harney/bridge/protocol.py`:

```python
"""JSON-RPC 2.0 message models."""

from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class JsonRpcError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    message: str
    data: Any = None


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JsonRpcError | None = None


class JsonRpcNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None


IncomingMessage = Union[JsonRpcRequest, JsonRpcResponse, JsonRpcNotification]


def parse_incoming(raw: bytes) -> IncomingMessage:
    """Parse a JSON-RPC frame into the right typed model.

    Dispatch by shape:
    - Has `id` AND `method` -> Request
    - Has `id` AND (`result` OR `error`) -> Response
    - Has `method` AND no `id` -> Notification
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON-RPC message must be an object")
    if data.get("jsonrpc") != "2.0":
        raise ValueError("missing or invalid 'jsonrpc' field (must be '2.0')")

    has_id = "id" in data
    has_method = "method" in data
    has_result_or_error = "result" in data or "error" in data

    if has_method and has_id:
        return JsonRpcRequest.model_validate(data)
    if has_method and not has_id:
        return JsonRpcNotification.model_validate(data)
    if has_id and has_result_or_error:
        return JsonRpcResponse.model_validate(data)
    raise ValueError(f"cannot classify JSON-RPC message: keys={sorted(data.keys())}")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 13 pass (6 framing + 7 protocol).

Run mypy + ruff: clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/errors.py src/meta_harney/bridge/protocol.py tests/unit/bridge/test_protocol.py
git commit -m "feat(bridge): JSON-RPC 2.0 protocol models + error codes"
```

---

### Task 3: BridgeServer skeleton + lifecycle (initialize/shutdown/exit)

**Files:**
- Create: `src/meta_harney/bridge/server.py`
- Test: `tests/unit/bridge/test_server_lifecycle.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_server_lifecycle.py`:

```python
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
    framing = NewlineFraming()
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
    framing = NewlineFraming()
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
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/pytest tests/unit/bridge/test_server_lifecycle.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement BridgeServer skeleton**

Create `src/meta_harney/bridge/server.py`:

```python
"""BridgeServer — orchestrates dispatch, lifecycle, and writer queue."""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.bridge.errors import (
    BridgeError,
    InternalError,
    InvalidRequest,
    MethodNotFound,
    ShuttingDown,
)
from meta_harney.bridge.framing import Framing
from meta_harney.bridge.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_incoming,
)
from meta_harney.runtime import AgentRuntime

logger = logging.getLogger("meta_harney.bridge")

HandlerResult = Any  # serialized as JSON
Handler = Callable[[Any], Awaitable[HandlerResult]]


class BridgeServer:
    """JSON-RPC 2.0 server wrapping an AgentRuntime.

    Construct with an AgentRuntime + Framing + server_info, then call
    `serve(reader, writer)` or `serve_stdio()` to start the loop.
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        framing: Framing,
        server_info: dict[str, str],
    ) -> None:
        self._runtime = runtime
        self._framing = framing
        self._server_info = dict(server_info)
        self._shutting_down = False
        self._exited = False
        self._handlers: dict[str, Handler] = {}
        self._notification_handlers: dict[str, Callable[[Any], Awaitable[None]]] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._register_lifecycle_handlers()

    # ---- handler registration ----

    def _register_lifecycle_handlers(self) -> None:
        self._handlers["initialize"] = self._handle_initialize
        self._handlers["shutdown"] = self._handle_shutdown
        self._notification_handlers["exit"] = self._handle_exit

    # ---- public entry point ----

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Run the read-dispatch loop until EOF or exit."""
        self._writer = writer
        try:
            while not self._exited:
                try:
                    raw = await self._framing.read_message(reader)
                except asyncio.IncompleteReadError:
                    break
                if raw is None:
                    break
                try:
                    msg = parse_incoming(raw)
                except ValueError as exc:
                    logger.warning("dropping malformed message: %s", exc)
                    continue
                if isinstance(msg, JsonRpcRequest):
                    asyncio.create_task(self._dispatch_request(msg))
                elif isinstance(msg, JsonRpcNotification):
                    asyncio.create_task(self._dispatch_notification(msg))
                else:
                    # JsonRpcResponse: bridge doesn't currently send outbound
                    # requests in this skeleton — Task 7 will add a pending-table
                    logger.debug("response received but no pending request table yet")
        finally:
            try:
                close = getattr(writer, "close", None)
                if callable(close):
                    close()
                wait_closed = getattr(writer, "wait_closed", None)
                if callable(wait_closed):
                    await wait_closed()
            except Exception:
                pass

    async def serve_stdio(self) -> None:
        """Convenience: serve over sys.stdin/sys.stdout."""
        import sys

        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        wt, wp = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
        writer = asyncio.StreamWriter(wt, wp, reader, loop)
        await self.serve(reader, writer)

    # ---- dispatch ----

    async def _dispatch_request(self, req: JsonRpcRequest) -> None:
        if self._shutting_down and req.method not in ("exit",):
            await self._send_error(req.id, ShuttingDown("server is shutting down"))
            return
        handler = self._handlers.get(req.method)
        if handler is None:
            await self._send_error(req.id, MethodNotFound(req.method))
            return
        try:
            result = await handler(req.params)
        except BridgeError as exc:
            await self._send_error(req.id, exc)
        except Exception as exc:
            logger.exception("internal error in handler %s", req.method)
            err = InternalError(str(exc), data={"traceback": traceback.format_exc()})
            await self._send_error(req.id, err)
        else:
            await self._send_response(req.id, result)

    async def _dispatch_notification(self, note: JsonRpcNotification) -> None:
        handler = self._notification_handlers.get(note.method)
        if handler is None:
            logger.debug("ignoring unknown notification: %s", note.method)
            return
        try:
            await handler(note.params)
        except Exception:
            logger.exception("error in notification handler %s", note.method)

    # ---- writer ----

    async def _send_raw(self, obj: Any) -> None:
        if self._writer is None:
            return
        payload = json.dumps(obj, default=_json_default).encode("utf-8")
        async with self._write_lock:
            await self._framing.write_message(self._writer, payload)

    async def _send_response(self, req_id: Any, result: Any) -> None:
        resp = JsonRpcResponse(id=req_id, result=result)
        await self._send_raw(resp.model_dump(exclude_none=False, exclude={"error"}))

    async def _send_error(self, req_id: Any, err: BridgeError) -> None:
        resp = JsonRpcResponse(
            id=req_id,
            error=JsonRpcError(code=err.code, message=err.message, data=err.data),
        )
        await self._send_raw(resp.model_dump(exclude_none=False, exclude={"result"}))

    async def _send_notification(self, method: str, params: Any) -> None:
        note = JsonRpcNotification(method=method, params=params)
        await self._send_raw(note.model_dump(exclude_none=True))

    # ---- lifecycle handlers ----

    async def _handle_initialize(self, params: Any) -> Any:
        return {
            "server_info": dict(self._server_info),
            "protocol_version": 1,
            "capabilities": {
                "streaming": True,
                "permissions": True,
                "cancel": True,
                "telemetry": True,
                "session_list": True,
                "session_load": True,
                "tools_list": True,
            },
        }

    async def _handle_shutdown(self, params: Any) -> Any:
        self._shutting_down = True
        return None

    async def _handle_exit(self, params: Any) -> None:
        self._exited = True


def _json_default(o: Any) -> Any:
    """Fallback JSON serializer for non-JSON-native types."""
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 17 pass (6 framing + 7 protocol + 4 lifecycle).

mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/server.py tests/unit/bridge/test_server_lifecycle.py
git commit -m "feat(bridge): BridgeServer skeleton with initialize/shutdown/exit"
```

---

### Task 4: Session methods (create / list / load)

**Files:**
- Modify: `src/meta_harney/bridge/server.py`
- Test: `tests/unit/bridge/test_server_sessions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_server_sessions.py`:

```python
"""Tests for session.create / session.list / session.load handlers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session import InMemorySessionStore


class _MinimalRuntime:
    """AgentRuntime stand-in that owns a real SessionStore."""

    def __init__(self, store: InMemorySessionStore) -> None:
        self._session_store = store

    async def create_session(self, **kwargs):
        sid = kwargs.get("session_id") or "sess-fixed"
        s = Session(id=sid, created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s


def _make_server() -> tuple[BridgeServer, InMemorySessionStore]:
    store = InMemorySessionStore()
    runtime = _MinimalRuntime(store)
    server = BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )
    return server, store


async def _drive(server: BridgeServer, lines: list[dict]) -> list[dict]:
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
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/pytest tests/unit/bridge/test_server_sessions.py -v`
Expected: MethodNotFound errors (handlers not registered yet).

- [ ] **Step 3: Implement session handlers**

In `src/meta_harney/bridge/server.py`, extend `_register_lifecycle_handlers` (or add a new `_register_session_handlers`):

Add to `__init__` after `_register_lifecycle_handlers()`:

```python
        self._register_session_handlers()
```

Add new methods to `BridgeServer`:

```python
    def _register_session_handlers(self) -> None:
        self._handlers["session.create"] = self._handle_session_create
        self._handlers["session.list"] = self._handle_session_list
        self._handlers["session.load"] = self._handle_session_load

    async def _handle_session_create(self, params: Any) -> Any:
        p = params or {}
        sess = await self._runtime.create_session(
            session_id=p.get("session_id"),
            tenant_id=p.get("tenant_id"),
            user_id=p.get("user_id"),
            attributes=p.get("attributes"),
            metadata=p.get("metadata"),
        )
        return {"id": sess.id, "created_at": sess.created_at.isoformat()}

    async def _handle_session_list(self, params: Any) -> Any:
        store = getattr(self._runtime, "_session_store", None)
        if store is None:
            from meta_harney.bridge.errors import MethodNotFound
            raise MethodNotFound("runtime has no session store")
        p = params or {}
        sessions = await store.list(tenant_id=p.get("tenant_id"))
        return [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "message_count": len(s.messages),
                "last_message_at": (
                    s.messages[-1].timestamp.isoformat()
                    if s.messages and hasattr(s.messages[-1], "timestamp")
                    else None
                ),
            }
            for s in sessions
        ]

    async def _handle_session_load(self, params: Any) -> Any:
        from meta_harney.bridge.errors import InvalidParams, SessionNotFound

        p = params or {}
        sid = p.get("session_id")
        if not isinstance(sid, str) or not sid:
            raise InvalidParams("session_id required (string)")
        store = getattr(self._runtime, "_session_store", None)
        if store is None:
            raise SessionNotFound(sid)
        sess = await store.load(sid, tenant_id=p.get("tenant_id"))
        if sess is None:
            raise SessionNotFound(sid)
        return {
            "id": sess.id,
            "created_at": sess.created_at.isoformat(),
            "messages": [m.model_dump() for m in sess.messages],
        }
```

Note: `last_message_at` uses `m.timestamp` only if it exists — `Message` in current meta-harney may not have this; leave as None when absent. The test only asserts `message_count` and `created_at` exist, so this is safe.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 21 pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/server.py tests/unit/bridge/test_server_sessions.py
git commit -m "feat(bridge): session.create/list/load handlers"
```

---

### Task 5: Streaming — `session.send_message` + `stream/event` notifications

**Files:**
- Modify: `src/meta_harney/bridge/server.py`
- Test: `tests/unit/bridge/test_server_stream.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_server_stream.py`:

```python
"""Tests for session.send_message + stream/event notifications."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session import InMemorySessionStore


class _FakeStreamEvent:
    """Stand-in for a StreamEvent — only model_dump matters for serialization."""

    def __init__(self, kind: str, data: dict) -> None:
        self.kind = kind
        self.data = data

    def model_dump(self) -> dict:
        return {"kind": self.kind, **self.data}


class _StreamingRuntime:
    """Runtime that emits N fake stream events."""

    def __init__(self, store: InMemorySessionStore, events: list) -> None:
        self._session_store = store
        self._events = events

    async def create_session(self, **kwargs):
        sid = kwargs.get("session_id") or "s"
        s = Session(id=sid, created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s

    async def stream(self, session_id, message, **kwargs):
        for ev in self._events:
            yield ev


def _make_server(events: list) -> BridgeServer:
    store = InMemorySessionStore()
    runtime = _StreamingRuntime(store, events)
    return BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )


async def _drive(server: BridgeServer, lines: list[dict]) -> list[dict]:
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
        _FakeStreamEvent("turn_end", {}),
    ]
    server = _make_server(events)
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
    assert all(n["params"]["request_id"] == 2 for n in stream_notes)
    assert send_resps[0]["result"] is not None
```

- [ ] **Step 2: Verify tests fail**

Expected: MethodNotFound for `session.send_message`.

- [ ] **Step 3: Implement streaming handler**

In `BridgeServer.__init__`, also call:

```python
        self._register_stream_handlers()
        self._inflight: dict[Any, asyncio.Task] = {}  # NEW: for Task 6 cancel
```

Add to `BridgeServer`:

```python
    def _register_stream_handlers(self) -> None:
        self._handlers["session.send_message"] = self._handle_session_send_message

    async def _handle_session_send_message(self, params: Any) -> Any:
        """Long-running: emits stream/event notifications, returns final state.

        The dispatcher already called us inside a task; we track this task so
        cancel handlers can target it. The request id is propagated via params
        for the cancel path — but the dispatcher wraps each request in its own
        task. To wire cancel cleanly we'd need the req_id here; we get it via
        a contextvar set up in _dispatch_request (Task 6 will refactor).
        """
        from meta_harney.bridge.errors import InvalidParams

        p = params or {}
        sid = p.get("session_id")
        msg_dict = p.get("message")
        if not isinstance(sid, str) or not isinstance(msg_dict, dict):
            raise InvalidParams("session_id (str) and message (dict) required")

        # Reconstruct Message from dict
        from meta_harney.abstractions._types import Message

        message = Message.model_validate(msg_dict)

        request_id = _current_request_id.get()
        stop_reason = "completed"
        async for event in self._runtime.stream(sid, message):
            await self._send_notification(
                "stream/event",
                {"request_id": request_id, "event": _serialize_event(event)},
            )
        return {"stopped_reason": stop_reason}
```

Also at module top-level, add:

```python
import contextvars

_current_request_id: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "_current_request_id", default=None
)


def _serialize_event(event: Any) -> Any:
    """Best-effort StreamEvent → JSON-safe dict."""
    if hasattr(event, "model_dump"):
        return event.model_dump()
    if isinstance(event, dict):
        return event
    return {"repr": repr(event)}
```

Update `_dispatch_request` to set the contextvar around the handler call:

```python
    async def _dispatch_request(self, req: JsonRpcRequest) -> None:
        if self._shutting_down and req.method not in ("exit",):
            await self._send_error(req.id, ShuttingDown("server is shutting down"))
            return
        handler = self._handlers.get(req.method)
        if handler is None:
            await self._send_error(req.id, MethodNotFound(req.method))
            return
        token = _current_request_id.set(req.id)
        try:
            try:
                result = await handler(req.params)
            except BridgeError as exc:
                await self._send_error(req.id, exc)
            except Exception as exc:
                logger.exception("internal error in handler %s", req.method)
                err = InternalError(str(exc), data={"traceback": traceback.format_exc()})
                await self._send_error(req.id, err)
            else:
                await self._send_response(req.id, result)
        finally:
            _current_request_id.reset(token)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 22 pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/server.py tests/unit/bridge/test_server_stream.py
git commit -m "feat(bridge): session.send_message + stream/event notifications"
```

---

### Task 6: Cancellation — `$/cancelRequest` + `session.cancel`

**Files:**
- Modify: `src/meta_harney/bridge/server.py`
- Test: `tests/unit/bridge/test_server_cancel.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_server_cancel.py`:

```python
"""Tests for $/cancelRequest and session.cancel."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.builtin.session import InMemorySessionStore


class _SlowEvent:
    def model_dump(self) -> dict:
        return {"kind": "tick"}


class _SlowRuntime:
    """Stream that emits one event every 50ms forever."""

    def __init__(self, store: InMemorySessionStore) -> None:
        self._session_store = store

    async def create_session(self, **kwargs):
        s = Session(id=kwargs.get("session_id") or "s", created_at=datetime.now(timezone.utc))
        await self._session_store.save(s)
        return s

    async def stream(self, session_id, message, **kwargs):
        for _ in range(100):
            await asyncio.sleep(0.05)
            yield _SlowEvent()


def _make_server() -> BridgeServer:
    store = InMemorySessionStore()
    runtime = _SlowRuntime(store)
    return BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "test", "version": "0"},
    )


async def _drive_with_delay(
    server: BridgeServer, initial_lines: list[dict], delayed: list[tuple[float, dict]]
) -> list[dict]:
    reader = asyncio.StreamReader()
    for ln in initial_lines:
        reader.feed_data(json.dumps(ln).encode() + b"\n")

    async def feeder() -> None:
        for delay, ln in delayed:
            await asyncio.sleep(delay)
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

    feeder_task = asyncio.create_task(feeder())
    await server.serve(reader, _W())  # type: ignore[arg-type]
    await feeder_task
    return [json.loads(b) for b in b"".join(write_buf).split(b"\n") if b]


@pytest.mark.asyncio
async def test_dollar_cancel_request_cancels_inflight_stream() -> None:
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
                        "message": {"role": "user", "content": [{"type": "text", "text": "x"}]},
                    },
                },
            ),
            (0.12, {"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": 2}}),
        ],
    )
    send_resp = next((m for m in msgs if m.get("id") == 2), None)
    assert send_resp is not None
    assert send_resp.get("error", {}).get("code") == -32002  # Cancelled


@pytest.mark.asyncio
async def test_session_cancel_request_returns_true_when_inflight() -> None:
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
                        "message": {"role": "user", "content": [{"type": "text", "text": "x"}]},
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
    assert cancel_resp["result"]["cancelled"] is True


@pytest.mark.asyncio
async def test_session_cancel_unknown_id_returns_false() -> None:
    server = _make_server()
    reader = asyncio.StreamReader()
    reader.feed_data(
        b'{"jsonrpc":"2.0","id":1,"method":"session.cancel","params":{"request_id":999}}\n'
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
    resp = json.loads(b"".join(write_buf).split(b"\n")[0])
    assert resp["result"]["cancelled"] is False
```

- [ ] **Step 2: Verify tests fail**

Expected: cancel handlers not registered → MethodNotFound; $/cancelRequest no-op.

- [ ] **Step 3: Implement cancellation**

In `BridgeServer.__init__`, register:

```python
        self._handlers["session.cancel"] = self._handle_session_cancel
        self._notification_handlers["$/cancelRequest"] = self._handle_cancel_notification
```

Update `_dispatch_request` to track in-flight tasks (replace the body):

```python
    async def _dispatch_request(self, req: JsonRpcRequest) -> None:
        if self._shutting_down and req.method not in ("exit",):
            await self._send_error(req.id, ShuttingDown("server is shutting down"))
            return
        handler = self._handlers.get(req.method)
        if handler is None:
            await self._send_error(req.id, MethodNotFound(req.method))
            return

        task = asyncio.current_task()
        if task is not None:
            self._inflight[req.id] = task

        token = _current_request_id.set(req.id)
        try:
            try:
                result = await handler(req.params)
            except asyncio.CancelledError:
                from meta_harney.bridge.errors import Cancelled

                await self._send_error(req.id, Cancelled("request cancelled by client"))
                return
            except BridgeError as exc:
                await self._send_error(req.id, exc)
            except Exception as exc:
                logger.exception("internal error in handler %s", req.method)
                err = InternalError(str(exc), data={"traceback": traceback.format_exc()})
                await self._send_error(req.id, err)
            else:
                await self._send_response(req.id, result)
        finally:
            _current_request_id.reset(token)
            self._inflight.pop(req.id, None)
```

Add handlers:

```python
    async def _handle_session_cancel(self, params: Any) -> Any:
        from meta_harney.bridge.errors import InvalidParams

        p = params or {}
        rid = p.get("request_id")
        if rid is None:
            raise InvalidParams("request_id required")
        task = self._inflight.get(rid)
        if task is None or task.done():
            return {"cancelled": False}
        task.cancel()
        return {"cancelled": True}

    async def _handle_cancel_notification(self, params: Any) -> None:
        p = params or {}
        rid = p.get("id")
        task = self._inflight.get(rid)
        if task is not None and not task.done():
            task.cancel()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 25 pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/server.py tests/unit/bridge/test_server_cancel.py
git commit -m "feat(bridge): \$/cancelRequest + session.cancel with task tracking"
```

---

### Task 7: BridgePermissionResolver + `permission/request` round-trip

**Files:**
- Create: `src/meta_harney/bridge/permission.py`
- Modify: `src/meta_harney/bridge/server.py` (pending-request table for outbound requests)
- Test: `tests/unit/bridge/test_permission.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_permission.py`:

```python
"""Tests for BridgePermissionResolver and bidirectional permission/request."""

from __future__ import annotations

import asyncio

import pytest

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.bridge.permission import BridgePermissionResolver


@pytest.mark.asyncio
async def test_resolver_sends_request_and_returns_decision() -> None:
    sent: list[tuple[str, dict]] = []

    async def fake_send_request(method: str, params: dict) -> dict:
        sent.append((method, params))
        return {"decision": "allow"}

    resolver = BridgePermissionResolver(send_request=fake_send_request)
    inv = ToolInvocation(tool_name="bash", arguments={"command": "ls"}, call_id="call-1")
    decision = await resolver.resolve(inv, session_id="sess-1")
    assert isinstance(decision, PermissionDecision)
    assert decision.verdict == "allow"
    assert len(sent) == 1
    method, params = sent[0]
    assert method == "permission/request"
    assert params["tool"] == "bash"
    assert params["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_resolver_maps_deny() -> None:
    async def send(method: str, params: dict) -> dict:
        return {"decision": "deny"}

    r = BridgePermissionResolver(send_request=send)
    inv = ToolInvocation(tool_name="bash", arguments={}, call_id="c")
    d = await r.resolve(inv, session_id="s")
    assert d.verdict == "deny"


@pytest.mark.asyncio
async def test_resolver_caches_allow_always_per_tool() -> None:
    call_count = 0

    async def send(method: str, params: dict) -> dict:
        nonlocal call_count
        call_count += 1
        return {"decision": "allow_always"}

    r = BridgePermissionResolver(send_request=send)
    inv1 = ToolInvocation(tool_name="bash", arguments={}, call_id="c1")
    inv2 = ToolInvocation(tool_name="bash", arguments={}, call_id="c2")
    d1 = await r.resolve(inv1, session_id="s")
    d2 = await r.resolve(inv2, session_id="s")
    assert d1.verdict == "allow"
    assert d2.verdict == "allow"
    assert call_count == 1  # second call hit the cache


@pytest.mark.asyncio
async def test_resolver_unknown_decision_falls_back_to_deny() -> None:
    async def send(method: str, params: dict) -> dict:
        return {"decision": "what"}

    r = BridgePermissionResolver(send_request=send)
    inv = ToolInvocation(tool_name="x", arguments={}, call_id="c")
    d = await r.resolve(inv, session_id="s")
    assert d.verdict == "deny"
```

- [ ] **Step 2: Verify tests fail**

Expected: ImportError.

- [ ] **Step 3: Implement BridgePermissionResolver + outbound request table in server**

Create `src/meta_harney/bridge/permission.py`:

```python
"""BridgePermissionResolver — forwards permission requests to the client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation

SendRequest = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class BridgePermissionResolver:
    """Sends `permission/request` to the client and awaits the decision.

    Decisions:
    - "allow"        -> PermissionDecision(verdict="allow")
    - "deny"         -> PermissionDecision(verdict="deny")
    - "allow_always" -> "allow" + cache (tool_name) so future invocations skip
                        the round-trip
    - anything else  -> PermissionDecision(verdict="deny")
    """

    def __init__(self, *, send_request: SendRequest) -> None:
        self._send_request = send_request
        self._always_allow: set[str] = set()

    async def resolve(
        self, invocation: ToolInvocation, session_id: str
    ) -> PermissionDecision:
        if invocation.tool_name in self._always_allow:
            return PermissionDecision(verdict="allow")
        response = await self._send_request(
            "permission/request",
            {
                "tool": invocation.tool_name,
                "tool_args": invocation.arguments,
                "session_id": session_id,
                "call_id": invocation.call_id,
            },
        )
        decision = response.get("decision") if isinstance(response, dict) else None
        if decision == "allow":
            return PermissionDecision(verdict="allow")
        if decision == "allow_always":
            self._always_allow.add(invocation.tool_name)
            return PermissionDecision(verdict="allow")
        return PermissionDecision(verdict="deny")
```

In `server.py`, add a pending-request table and outbound `send_request` method:

```python
# At top, add:
import itertools

# In __init__:
        self._pending: dict[Any, asyncio.Future[Any]] = {}
        self._outbound_id_counter = itertools.count(start=-1, step=-1)  # negative ids

# Update serve() loop's `JsonRpcResponse` branch:
                elif isinstance(msg, JsonRpcResponse):
                    fut = self._pending.pop(msg.id, None)
                    if fut is not None and not fut.done():
                        if msg.error is not None:
                            fut.set_exception(
                                RuntimeError(f"client error: {msg.error.message}")
                            )
                        else:
                            fut.set_result(msg.result)

# Add new method:
    async def send_request(self, method: str, params: dict[str, Any]) -> Any:
        rid = next(self._outbound_id_counter)
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        req = JsonRpcRequest(id=rid, method=method, params=params)
        await self._send_raw(req.model_dump(exclude_none=True))
        try:
            return await fut
        finally:
            self._pending.pop(rid, None)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 29 pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/permission.py src/meta_harney/bridge/server.py tests/unit/bridge/test_permission.py
git commit -m "feat(bridge): BridgePermissionResolver + outbound permission/request"
```

---

### Task 8: BridgeTraceSink + `telemetry/subscribe`

**Files:**
- Create: `src/meta_harney/bridge/trace.py`
- Modify: `src/meta_harney/bridge/server.py`
- Test: `tests/unit/bridge/test_trace.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/bridge/test_trace.py`:

```python
"""Tests for BridgeTraceSink + telemetry/subscribe."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.bridge.trace import BridgeTraceSink


@pytest.mark.asyncio
async def test_sink_drops_events_when_unsubscribed() -> None:
    sent: list[tuple[str, dict]] = []

    async def send_note(method: str, params: dict) -> None:
        sent.append((method, params))

    sink = BridgeTraceSink(send_notification=send_note)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        kind="test.event",
        span_id="span-1",
    )
    await sink.emit(ev)
    assert sent == []


@pytest.mark.asyncio
async def test_sink_forwards_events_when_subscribed() -> None:
    sent: list[tuple[str, dict]] = []

    async def send_note(method: str, params: dict) -> None:
        sent.append((method, params))

    sink = BridgeTraceSink(send_notification=send_note)
    sink.set_enabled(True)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        kind="test.event",
        span_id="span-1",
        payload={"x": 1},
    )
    await sink.emit(ev)
    assert len(sent) == 1
    method, params = sent[0]
    assert method == "telemetry/event"
    assert params["event_type"] == "test.event"
    assert params["payload"]["session_id"] == "s"


@pytest.mark.asyncio
async def test_sink_handles_send_errors_silently() -> None:
    async def boom(method: str, params: dict) -> None:
        raise RuntimeError("network down")

    sink = BridgeTraceSink(send_notification=boom)
    sink.set_enabled(True)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s", kind="x", span_id="sp"
    )
    # Must not raise — observability shouldn't kill the engine
    await sink.emit(ev)
```

- [ ] **Step 2: Verify tests fail**

Expected: ImportError.

- [ ] **Step 3: Implement BridgeTraceSink + handler**

Create `src/meta_harney/bridge/trace.py`:

```python
"""BridgeTraceSink — forwards trace events as telemetry/event notifications."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.abstractions.trace import TraceEvent

logger = logging.getLogger("meta_harney.bridge.trace")

SendNotification = Callable[[str, dict[str, Any]], Awaitable[None]]


class BridgeTraceSink:
    """Forwards TraceEvents to the bridge client when subscription is enabled.

    Per the TraceSink contract, this MUST NOT raise — exceptions are caught
    and logged so observability never kills the engine.
    """

    def __init__(self, *, send_notification: SendNotification) -> None:
        self._send = send_notification
        self._enabled = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def emit(self, event: TraceEvent) -> None:
        if not self._enabled:
            return
        try:
            await self._send(
                "telemetry/event",
                {
                    "event_type": event.kind,
                    "payload": event.model_dump(mode="json"),
                },
            )
        except Exception:
            logger.exception("BridgeTraceSink: failed to forward event")
```

In `server.py` add a `telemetry/subscribe` handler. Server should hold an optional `BridgeTraceSink` reference (set from outside) — but for symmetry we'll let the server provide a `set_trace_sink_subscription(enabled)` callback. Simplest: the host wires a `BridgeTraceSink` into the runtime AND passes it to the server so the server can flip the subscription bit:

In `BridgeServer.__init__`, add parameter:

```python
        trace_sink: "BridgeTraceSink | None" = None,
```

(use forward string ref to avoid circular import; import inside the body)

And:

```python
        from meta_harney.bridge.trace import BridgeTraceSink as _BTS  # noqa: F401
        self._trace_sink = trace_sink  # may be None
        self._handlers["telemetry/subscribe"] = self._handle_telemetry_subscribe
        self._handlers["tools.list"] = self._handle_tools_list
```

Handlers:

```python
    async def _handle_telemetry_subscribe(self, params: Any) -> Any:
        from meta_harney.bridge.errors import InvalidParams

        p = params or {}
        enabled = p.get("enabled")
        if not isinstance(enabled, bool):
            raise InvalidParams("enabled (bool) required")
        if self._trace_sink is not None:
            self._trace_sink.set_enabled(enabled)
        return {"enabled": enabled}

    async def _handle_tools_list(self, params: Any) -> Any:
        tools = getattr(self._runtime, "_tools", {}) or {}
        out = []
        for name, tool in tools.items():
            schema = None
            for attr in ("input_schema", "args_schema", "schema"):
                v = getattr(tool, attr, None)
                if v is not None:
                    schema = v.model_json_schema() if hasattr(v, "model_json_schema") else v
                    break
            out.append({
                "name": name,
                "description": getattr(tool, "description", ""),
                "input_schema": schema,
            })
        return out
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/bridge/ -v`
Expected: 32 pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/trace.py src/meta_harney/bridge/server.py tests/unit/bridge/test_trace.py
git commit -m "feat(bridge): BridgeTraceSink + telemetry/subscribe + tools.list"
```

---

### Task 9: Example runner + subprocess integration test

**Files:**
- Create: `src/meta_harney/bridge/example/__init__.py` (empty)
- Create: `src/meta_harney/bridge/example/__main__.py`
- Create: `tests/integration/bridge/__init__.py` (empty)
- Test: `tests/integration/bridge/test_subprocess.py`

- [ ] **Step 1: Write failing test**

Create `tests/integration/bridge/test_subprocess.py`:

```python
"""End-to-end: spawn `python -m meta_harney.bridge.example` subprocess, drive lifecycle."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest


@pytest.mark.asyncio
async def test_subprocess_full_lifecycle() -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "meta_harney.bridge.example",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    async def send(req: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(req).encode() + b"\n")
        await proc.stdin.drain()

    async def read_one() -> dict:
        assert proc.stdout is not None
        line = await proc.stdout.readline()
        return json.loads(line)

    try:
        # initialize
        await send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        resp = await read_one()
        assert resp["id"] == 1
        assert resp["result"]["server_info"]["name"] == "meta-harney-bridge-example"

        # session.create
        await send({"jsonrpc": "2.0", "id": 2, "method": "session.create"})
        resp = await read_one()
        assert resp["id"] == 2
        sid = resp["result"]["id"]

        # session.send_message — fake provider returns "hello from fake"
        await send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session.send_message",
                "params": {
                    "session_id": sid,
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hi"}],
                    },
                },
            }
        )

        # Read messages until id=3 final response arrives
        got_final = False
        stream_event_count = 0
        for _ in range(100):
            msg = await read_one()
            if msg.get("method") == "stream/event":
                stream_event_count += 1
            elif msg.get("id") == 3:
                got_final = True
                break
        assert got_final
        assert stream_event_count >= 1  # at least one event

        # shutdown + exit
        await send({"jsonrpc": "2.0", "id": 99, "method": "shutdown"})
        await read_one()
        await send({"jsonrpc": "2.0", "method": "exit"})

        await asyncio.wait_for(proc.wait(), timeout=5)
        assert proc.returncode == 0
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
```

- [ ] **Step 2: Verify failing**

Expected: ModuleNotFoundError on the example module.

- [ ] **Step 3: Implement example runner**

Create `src/meta_harney/bridge/example/__init__.py` (empty).

Create `src/meta_harney/bridge/example/__main__.py`:

```python
"""Runnable bridge example with a FakeLLMProvider — for integration testing.

    python -m meta_harney.bridge.example
"""

from __future__ import annotations

import asyncio
import sys

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.bridge.framing import NewlineFraming
from meta_harney.bridge.server import BridgeServer
from meta_harney.bridge.trace import BridgeTraceSink
from meta_harney.bridge.permission import BridgePermissionResolver
from meta_harney.builtin.session import InMemorySessionStore
from meta_harney.builtin.trace import NullTraceSink  # type: ignore[attr-defined]


class _FakeProvider:
    """Minimal LLM provider that yields one text delta then stops."""

    async def stream(self, *args, **kwargs):  # pragma: no cover - shape varies
        from meta_harney.engine.stream_events import TextDelta, TurnEnd

        yield TextDelta(text="hello from bridge example")
        yield TurnEnd(stop_reason="end_turn")


class _MiniRuntime:
    """Hand-rolled runtime stub: enough surface for the bridge integration test."""

    def __init__(self) -> None:
        from datetime import datetime, timezone

        self._session_store = InMemorySessionStore()
        self._tools: dict = {}
        self._datetime = datetime
        self._tz = timezone

    async def create_session(self, **kwargs):
        from meta_harney.abstractions.session import Session

        sid = kwargs.get("session_id") or "sess-bridge"
        s = Session(id=sid, created_at=self._datetime.now(self._tz.utc))
        await self._session_store.save(s)
        return s

    async def stream(self, session_id, message, **kwargs):
        # Emit a handful of simple events, then stop.
        class _E:
            def __init__(self, k: str, payload: dict | None = None) -> None:
                self.kind = k
                self.payload = payload or {}

            def model_dump(self) -> dict:
                return {"kind": self.kind, **self.payload}

        yield _E("text_delta", {"text": "hello"})
        yield _E("text_delta", {"text": " from bridge"})
        yield _E("turn_end", {"stop_reason": "end_turn"})


async def main() -> None:
    runtime = _MiniRuntime()
    server = BridgeServer(
        runtime=runtime,  # type: ignore[arg-type]
        framing=NewlineFraming(),
        server_info={"name": "meta-harney-bridge-example", "version": "0.1.0"},
    )
    await server.serve_stdio()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
```

Create `tests/integration/bridge/__init__.py` (empty).

- [ ] **Step 4: Run integration test**

Run: `.venv/bin/pytest tests/integration/bridge/ -v`
Expected: pass.

Run full suite: `.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/bridge/example tests/integration/bridge
git commit -m "feat(bridge): example runner + subprocess integration test"
```

---

### Task 10: Public API exports + version bump v0.1.0

**Files:**
- Modify: `src/meta_harney/bridge/__init__.py`
- Modify: `src/meta_harney/__init__.py`
- Modify: `pyproject.toml`
- Modify: `README.md` (small bridge section)

- [ ] **Step 1: Populate bridge __init__**

Replace `src/meta_harney/bridge/__init__.py`:

```python
"""meta_harney.bridge — JSON-RPC 2.0 server exposing AgentRuntime over stdio."""

from meta_harney.bridge.errors import (
    BridgeError,
    Cancelled,
    InternalError,
    InvalidParams,
    InvalidRequest,
    MethodNotFound,
    ParseError,
    PermissionDenied,
    SessionNotFound,
    ShuttingDown,
)
from meta_harney.bridge.framing import (
    ContentLengthFraming,
    Framing,
    NewlineFraming,
)
from meta_harney.bridge.permission import BridgePermissionResolver
from meta_harney.bridge.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_incoming,
)
from meta_harney.bridge.server import BridgeServer
from meta_harney.bridge.trace import BridgeTraceSink

__all__ = [
    "BridgeError",
    "BridgePermissionResolver",
    "BridgeServer",
    "BridgeTraceSink",
    "Cancelled",
    "ContentLengthFraming",
    "Framing",
    "InternalError",
    "InvalidParams",
    "InvalidRequest",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "MethodNotFound",
    "NewlineFraming",
    "ParseError",
    "PermissionDenied",
    "SessionNotFound",
    "ShuttingDown",
    "parse_incoming",
]
```

- [ ] **Step 2: Bump version + top-level re-exports**

In `pyproject.toml`:

```toml
version = "0.1.0"
```

In `src/meta_harney/__init__.py` — find the `__version__` line, change to `"0.1.0"`. Append bridge surface to existing `__all__`:

```python
from meta_harney.bridge import (
    BridgeServer,
    BridgePermissionResolver,
    BridgeTraceSink,
    NewlineFraming,
    ContentLengthFraming,
)
# extend existing __all__ accordingly
```

- [ ] **Step 3: README addition**

In `README.md`, add a new section after the existing content:

```markdown
## Bridge — drive AgentRuntime from another process

```python
import asyncio
from meta_harney import AgentRuntime
from meta_harney.bridge import BridgeServer, NewlineFraming

runtime = build_your_runtime()  # tools, permissions, sessions wired by you
server = BridgeServer(
    runtime=runtime,
    framing=NewlineFraming(),
    server_info={"name": "my-bridge", "version": "0.1.0"},
)
asyncio.run(server.serve_stdio())
```

JSON-RPC 2.0 over stdio. Methods: `initialize`, `shutdown`, `exit`,
`session.create/list/load`, `session.send_message` (with `stream/event`
notifications), `session.cancel`, `$/cancelRequest`, `tools.list`,
`permission/request` (server → client), `telemetry/subscribe`,
`telemetry/event`. Two framings supported: `NewlineFraming`,
`ContentLengthFraming`.
```

- [ ] **Step 4: Final quality gates**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/mypy src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
python -c "import meta_harney; print(meta_harney.__version__)"
```

Expected: all clean, version 0.1.0.

- [ ] **Step 5: Commit + tag v0.1.0**

```bash
git add src/meta_harney/__init__.py src/meta_harney/bridge/__init__.py pyproject.toml README.md
git commit -m "release: v0.1.0 — meta_harney.bridge (JSON-RPC over stdio)

Phase 10 ships:
- Two framings: NewlineFraming, ContentLengthFraming
- JSON-RPC 2.0 protocol layer
- BridgeServer with lifecycle, sessions, streaming, cancel, permissions, telemetry
- BridgePermissionResolver (bidirectional permission/request)
- BridgeTraceSink (telemetry/subscribe gate)
- Example runner under meta_harney.bridge.example for downstream integration"

git tag -a v0.1.0 -m "v0.1.0 — Phase 10 Bridge"
git push origin main
git push origin v0.1.0
```

---

## Self-Review

**Spec coverage:**
- ✅ Framing × 2 (Task 1)
- ✅ JSON-RPC 2.0 protocol (Task 2)
- ✅ Lifecycle initialize/shutdown/exit (Task 3)
- ✅ session.create/list/load (Task 4)
- ✅ session.send_message + stream/event (Task 5)
- ✅ Cancellation: $/cancelRequest + session.cancel (Task 6)
- ✅ BridgePermissionResolver + outbound permission/request + allow_always caching (Task 7)
- ✅ BridgeTraceSink + telemetry/subscribe + tools.list (Task 8)
- ✅ Subprocess integration test (Task 9)
- ✅ Public API + version bump + tag (Task 10)

**Placeholder scan:** No TBDs. Every step includes full code blocks for new files; modify steps cite line locations or full functions.

**Type consistency:**
- `Framing` Protocol defined in T1, used by `BridgeServer` from T3 onward. ✅
- `JsonRpcRequest/Response/Notification` defined in T2, used by server. ✅
- `_current_request_id` ContextVar introduced in T5, used by T6 cancel. ✅
- `BridgePermissionResolver.send_request` callable type matches what T7 wires in `server.py`. ✅
- `BridgeTraceSink.send_notification` matches `BridgeServer._send_notification` signature `(method: str, params: Any) -> Awaitable[None]`. ✅

**Risk callouts:**
- T9 example runner uses a minimal `_MiniRuntime` shim — fine for integration test, but document that real production usage builds a full AgentRuntime.
- T7 outbound request id uses negative integers (`itertools.count(start=-1, step=-1)`) to avoid collision with client-sent positive ids — make sure clients use positive ids by convention. Document in spec.
- T8 `tools.list` introspects `getattr(runtime, "_tools", {})` — a fragile private attribute. Acceptable for v1; future task: add `runtime.tools` public property.

All clear.

---

## Execution

**Subagent-Driven** per the user's standing preference (Phase 6+ auto-approve). Fresh subagent per task, two-stage review where applicable. Continue uninterrupted.
