# Phase 10 — `meta_harney.bridge`: JSON-RPC bridge for AgentRuntime

## Goal

Expose `AgentRuntime` as a JSON-RPC 2.0 server over stdio so a non-Python parent process (Node, Go, Rust, ...) can drive an agent. This unlocks Phase 11 (React + Ink TUI) and any future IDE/editor integration. Generic infrastructure — no oh-mini coupling.

## Scope: Full (per user choice)

Standard methods + cancel + telemetry forward.

## Architecture

```
Parent process (Node/TUI/IDE)
   ↓ stdin (JSON-RPC requests + notifications)
   ↑ stdout (JSON-RPC responses + notifications)
   ↑ stderr (human logs, ignored by protocol)
Python child process
   = meta_harney.bridge.BridgeServer
     ├── Framing (newline | content-length)
     ├── Protocol (JSON-RPC 2.0 message types)
     ├── MethodDispatcher (routes incoming requests)
     ├── BridgePermissionResolver  ──→ sends permission/request UP
     ├── BridgeTraceSink           ──→ sends telemetry/event UP
     └── AgentRuntime (constructed by caller, injected)
```

The bridge does NOT construct the AgentRuntime. The host wires its own tools/permissions/sessions and hands a runtime instance to `BridgeServer.serve()`. Both `oh bridge` (oh-mini side, separate phase) and arbitrary downstream apps benefit.

## Module layout

```
src/meta_harney/bridge/
├── __init__.py        # public exports
├── framing.py         # Framing Protocol + NewlineFraming + ContentLengthFraming
├── protocol.py        # JsonRpcRequest/Response/Notification/Error pydantic types
├── errors.py          # JSON-RPC error codes + BridgeError exception
├── permission.py      # BridgePermissionResolver
├── trace.py           # BridgeTraceSink
├── dispatch.py        # method handlers (route + parse + call runtime)
└── server.py          # BridgeServer (orchestrator)
```

## Framing — two strategies, user picks

Generic `Framing` Protocol:

```python
class Framing(Protocol):
    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None: ...
    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None: ...
```

### NewlineFraming
One JSON object per line, terminated by `\n`. Payload must not contain raw newlines (JSON `\n` escapes are fine). Simplest; debuggable with `cat`.

### ContentLengthFraming (LSP-style)
```
Content-Length: <N>\r\n
\r\n
<N bytes of JSON>
```
Robust for multi-MB payloads with embedded newlines. Required if telemetry blobs get huge.

`BridgeServer(framing=NewlineFraming())` or `BridgeServer(framing=ContentLengthFraming())`.

## JSON-RPC 2.0 protocol

`protocol.py` defines pydantic v2 frozen models:

```python
class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] | list[Any] | None = None

class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    result: Any | None = None
    error: JsonRpcError | None = None

class JsonRpcNotification(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None

class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None
```

Standard error codes in `errors.py`:
- `-32700` ParseError, `-32600` InvalidRequest, `-32601` MethodNotFound,
  `-32602` InvalidParams, `-32603` InternalError
- Custom: `-32000` SessionNotFound, `-32001` PermissionDenied, `-32002` Cancelled

## Method surface

### Lifecycle

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `initialize` | C→S | Request | `{client_info: {name, version}, protocol_version: 1, capabilities: {...}}` | `{server_info: {name, version}, capabilities: {...}}` |
| `shutdown` | C→S | Request | `{}` | `null` |
| `exit` | C→S | Notification | `{}` | n/a |

Server emits `initialized` response after wiring runtime. After `shutdown`, the server only accepts `exit`. After `exit`, the process terminates with code 0 (clean) or 1 (no prior shutdown).

### Sessions

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `session.create` | C→S | Request | `{session_id?, tenant_id?, user_id?, attributes?, metadata?}` | `{id, created_at}` |
| `session.list` | C→S | Request | `{}` | `[{id, created_at, message_count, last_message_at}]` |
| `session.load` | C→S | Request | `{session_id}` | `{id, created_at, messages: [...]}` |

`session.list` requires the SessionStore to support listing — if not, returns `MethodNotFound`. Adding a `list_sessions()` method to `SessionStore` is part of this phase.

### Streaming

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `session.send_message` | C→S | Request | `{session_id, message: {role, content: [...]}}` | `{stopped_reason, final_message?}` |
| `stream/event` | S→C | Notification | `{request_id, event: <StreamEvent>}` | n/a |
| `session.cancel` | C→S | Request | `{request_id}` | `{cancelled: true|false}` |
| `$/cancelRequest` | C→S | Notification | `{id}` | n/a |

Lifecycle of `session.send_message`:
1. Server picks up request, starts streaming runtime.stream()
2. For each StreamEvent, emit `stream/event` notification with `request_id = <id of send_message>` and serialized event
3. May emit `permission/request` (see below) during execution
4. On completion: respond to original send_message with final state
5. On cancel: respond with error code `-32002` (Cancelled)

`$/cancelRequest` is LSP-style: a notification carrying the in-flight request id. Server cancels the matching asyncio.Task. `session.cancel` is the request-style equivalent (returns whether the cancel actually fired).

### Permissions (server-initiated)

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `permission/request` | S→C | Request | `{tool, tool_args, session_id, request_id}` | `{decision: "allow"\|"deny"\|"allow_always"}` |

Implementation: `BridgePermissionResolver` is constructed by the bridge server, given a "send_request" callback. When `resolve()` is called by the runtime, it sends a `permission/request` upstream, awaits the response, returns the decision.

### Tools

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `tools.list` | C→S | Request | `{}` | `[{name, description, input_schema}]` |

Returns the tool specs registered with the runtime.

### Telemetry

| Method | Direction | Type | Params | Result |
|---|---|---|---|---|
| `telemetry/subscribe` | C→S | Request | `{enabled: bool}` | `{enabled}` |
| `telemetry/event` | S→C | Notification | `{event_type, payload}` | n/a |

`BridgeTraceSink` implements `TraceSink`. When subscription is enabled, it forwards each trace event as a `telemetry/event` notification. When disabled (default), trace events are dropped at the sink. Per `_serialize` patterns already used in the runtime.

## Cancellation semantics

- `$/cancelRequest` (notification) — fire-and-forget; preferred for "user clicked stop"
- `session.cancel` (request) — gives a confirmation result; preferred for programmatic cancel
- Both target an in-flight `session.send_message` by its request id
- Server tracks in-flight tasks: `dict[req_id → asyncio.Task]`
- On cancel: `task.cancel()` + send final response with `Cancelled` error code
- Tool execution should propagate cancellation (existing runtime should already handle CancelledError)

## Concurrency model

- Server is single-process asyncio
- Multiple `session.send_message` can run concurrently (different session_ids)
- One reader task pulls messages from stdin → dispatcher
- One writer queue serializes outbound messages to stdout (avoids interleaving)
- Bidirectional requests use a pending-request table keyed by id

## SessionStore extension

To support `session.list`, add an optional method to the `SessionStore` Protocol:

```python
class SessionStore(Protocol):
    # existing: save, load, append_messages, ...
    async def list_sessions(self) -> list[SessionSummary]: ...  # NEW
```

Default `InMemorySessionStore` and `FileSessionStore` (used by oh-mini) implement it. Protocols may be missing it — bridge returns MethodNotFound gracefully.

Add a tiny `SessionSummary` dataclass: `{id, created_at, message_count, last_message_at}`.

## Error handling

All exceptions in dispatch handlers are caught and converted to JSON-RPC error responses:
- `ValidationError` (pydantic) → `-32602` InvalidParams
- `SessionConflictError`, `SessionNotFoundError` → `-32000` SessionNotFound (when relevant)
- `PermissionDenied` (runtime) → bubble up as stream/event error then `-32001` PermissionDenied on the send_message response
- `asyncio.CancelledError` → `-32002` Cancelled
- Anything else → `-32603` InternalError with `data: {type, traceback}` (traceback in dev mode only — controlled by env `META_HARNEY_BRIDGE_DEV=1`)

## Public API

```python
# src/meta_harney/bridge/__init__.py
from meta_harney.bridge.framing import Framing, NewlineFraming, ContentLengthFraming
from meta_harney.bridge.server import BridgeServer, BridgeServerConfig
from meta_harney.bridge.protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcNotification, JsonRpcError,
)
from meta_harney.bridge.errors import (
    BridgeError, ParseError, InvalidRequest, MethodNotFound,
    InvalidParams, InternalError, SessionNotFound, PermissionDenied, Cancelled,
)
```

Usage by host:

```python
import asyncio
from meta_harney import AgentRuntime
from meta_harney.bridge import BridgeServer, NewlineFraming

# Host builds runtime however they like:
runtime = build_my_runtime()

server = BridgeServer(
    runtime=runtime,
    framing=NewlineFraming(),
    server_info={"name": "oh-mini-bridge", "version": "0.1.0"},
)
asyncio.run(server.serve_stdio())
```

`serve_stdio()` reads from `sys.stdin` and writes to `sys.stdout`. For testing, `serve(reader, writer)` accepts arbitrary asyncio streams.

## Testing strategy

| Test file | Coverage |
|---|---|
| `tests/unit/bridge/test_framing.py` | NewlineFraming round-trip; ContentLengthFraming round-trip; partial reads; EOF |
| `tests/unit/bridge/test_protocol.py` | Request/Response/Notification/Error parse + serialize; unknown fields rejected |
| `tests/unit/bridge/test_dispatch.py` | Method dispatch by name; unknown method → MethodNotFound; invalid params → InvalidParams |
| `tests/unit/bridge/test_permission.py` | BridgePermissionResolver awaits upstream response; timeout behavior; decision mapping |
| `tests/unit/bridge/test_trace.py` | BridgeTraceSink subscription on/off; event serialization |
| `tests/unit/bridge/test_cancel.py` | $/cancelRequest cancels in-flight task; session.cancel returns true/false; double cancel safe |
| `tests/integration/bridge/test_lifecycle.py` | initialize → session.create → send_message → stream/event notifications → final response |
| `tests/integration/bridge/test_permission_roundtrip.py` | Tool execution suspends on permission, resumes on response |
| `tests/integration/bridge/test_subprocess.py` | Spawn `python -m meta_harney.bridge.example` subprocess from test (acts as Node), drive full session |
| `tests/integration/bridge/test_telemetry.py` | telemetry/subscribe enables, events flow; unsubscribe stops them |

A small bundled example runner (`src/meta_harney/bridge/example/__main__.py`) lets tests spawn a real bridge with a FakeLLMProvider — useful for the subprocess integration test.

## Acceptance

1. `BridgeServer` serves a full lifecycle: initialize → create session → send message → receive stream events → final response → shutdown → exit
2. NewlineFraming and ContentLengthFraming both round-trip a 1MB JSON payload
3. Cancel via `$/cancelRequest` mid-stream cleanly stops the runtime task with no leaked tasks
4. Permission round-trip works: tool execution waits for upstream decision
5. Telemetry events flow when subscribed, dropped when not
6. `pytest -q` 100% green; mypy strict clean; ruff clean
7. Released as meta-harney v0.1.0 (significant new module → minor version bump)

## Out of scope

- Authentication / process trust handshake
- Multi-client per server (one client at a time)
- Backpressure / flow control beyond what asyncio.StreamWriter does
- Custom transport (only stdio; future: TCP/Unix socket)
- Python ←→ Python bridge optimization (just-use-the-runtime-directly)
- TUI itself (Phase 11)

## Risks

- **Asyncio cancellation correctness**: cancelling mid-tool-execution must not corrupt session state. Mitigation: existing `engine/loop.py` should handle CancelledError; verify with dedicated test.
- **JSON serialization of all StreamEvents**: events contain pydantic models; need a coherent `model_dump()` strategy. Mitigation: meta-harney already uses `_serialize` for traces — reuse the same approach.
- **Bidirectional request id collision**: client and server both generate ids. Mitigation: use separate id pools per direction (e.g., client ids are positive ints, server ids are negative ints, or use UUIDs).
- **Stdin/stdout buffering on Windows**: tests should run on macOS/Linux only for v1; document Windows as best-effort.

## Versioning

Meta-harney v0.0.8 → **v0.1.0**. New top-level module + new public API justifies minor bump (still pre-1.0 per semver allowance). Tag and push.
