"""BridgeServer — orchestrates dispatch, lifecycle, and writer queue."""

from __future__ import annotations

import asyncio
import contextvars
import itertools
import json
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.bridge.errors import (
    BridgeError,
    Cancelled,
    InternalError,
    InvalidParams,
    MethodNotFound,
    SessionNotFound,
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
        self._inflight: set[asyncio.Task[None]] = set()
        # Map JSON-RPC request id -> dispatch task, so cancel handlers can target
        # a specific in-flight request. Distinct from `_inflight` (used only for
        # graceful drain on EOF). Populated by `_dispatch_request`.
        self._inflight_by_request_id: dict[Any, asyncio.Task[Any]] = {}
        # Server-initiated outbound requests (e.g., permission/request). Keyed
        # by the request id we generate; negative-counting so we can't collide
        # with the client's positive ids on the same connection.
        self._pending: dict[Any, asyncio.Future[Any]] = {}
        self._outbound_id_counter: Callable[[], int] = itertools.count(
            start=-1, step=-1
        ).__next__
        self._register_lifecycle_handlers()
        self._register_session_handlers()
        self._register_stream_handlers()
        self._register_cancel_handlers()

    # ---- handler registration ----

    def _register_lifecycle_handlers(self) -> None:
        self._handlers["initialize"] = self._handle_initialize
        self._handlers["shutdown"] = self._handle_shutdown
        self._notification_handlers["exit"] = self._handle_exit

    def _register_session_handlers(self) -> None:
        self._handlers["session.create"] = self._handle_session_create
        self._handlers["session.list"] = self._handle_session_list
        self._handlers["session.load"] = self._handle_session_load

    def _register_stream_handlers(self) -> None:
        self._handlers["session.send_message"] = self._handle_session_send_message

    def _register_cancel_handlers(self) -> None:
        # session.cancel: request — returns {"cancelled": bool}
        # $/cancelRequest: LSP-style notification — no response
        self._handlers["session.cancel"] = self._handle_session_cancel
        self._notification_handlers["$/cancelRequest"] = self._handle_cancel_notification

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
                    self._spawn(self._dispatch_request(msg))
                elif isinstance(msg, JsonRpcNotification):
                    # Lifecycle notifications (e.g. `exit`) must run inline so
                    # the read loop observes their state changes immediately.
                    if msg.method in self._notification_handlers:
                        await self._dispatch_notification(msg)
                    else:
                        self._spawn(self._dispatch_notification(msg))
                else:
                    # JsonRpcResponse: correlate against an outstanding outbound
                    # request (e.g., permission/request). Unknown ids are dropped
                    # — the peer may have responded to a stale request after we
                    # cancelled it locally.
                    self._handle_inbound_response(msg)
        finally:
            # Drain any in-flight handler tasks so their responses are written
            # before we close the writer.
            if self._inflight:
                await asyncio.gather(*self._inflight, return_exceptions=True)
            try:
                close = getattr(writer, "close", None)
                if callable(close):
                    close()
                wait_closed = getattr(writer, "wait_closed", None)
                if callable(wait_closed):
                    await wait_closed()
            except Exception:
                pass

    def _spawn(self, coro: Awaitable[None]) -> None:
        """Create a background task and track it for graceful drain."""
        task: asyncio.Task[None] = asyncio.ensure_future(coro)
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)

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

        # Register this dispatch task under its JSON-RPC id so cancel handlers
        # ($/cancelRequest, session.cancel) can target it. We use current_task()
        # because `_spawn` wraps this coroutine in a Task.
        current = asyncio.current_task()
        if current is not None and req.id is not None:
            self._inflight_by_request_id[req.id] = current

        token = _current_request_id.set(req.id)
        try:
            try:
                result = await handler(req.params)
            except asyncio.CancelledError:
                # A cancel handler called task.cancel() on us. Translate to a
                # well-formed Cancelled JSON-RPC error response so the parent
                # doesn't hang. Do NOT re-raise — that would propagate to the
                # serve() loop and look like a 500.
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
            if req.id is not None:
                self._inflight_by_request_id.pop(req.id, None)

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

    # ---- outbound (server-initiated) requests ----

    async def send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a server-initiated JSON-RPC request to the client and await the result.

        Used by ``BridgePermissionResolver`` and any future server-pushed RPCs
        (e.g., interactive elicitation). Returns the response ``result`` on
        success; raises ``RuntimeError`` if the client returns a JSON-RPC error.
        """
        rid = self._outbound_id_counter()
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        req = JsonRpcRequest(id=rid, method=method, params=params)
        await self._send_raw(req.model_dump(exclude_none=True))
        try:
            return await fut
        finally:
            self._pending.pop(rid, None)

    def _handle_inbound_response(self, msg: JsonRpcResponse) -> None:
        """Resolve the pending future for an inbound response, if any."""
        fut = self._pending.pop(msg.id, None)
        if fut is None or fut.done():
            logger.debug("dropping response for unknown/completed id: %r", msg.id)
            return
        if msg.error is not None:
            fut.set_exception(
                RuntimeError(f"client error {msg.error.code}: {msg.error.message}")
            )
        else:
            fut.set_result(msg.result)

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

    # ---- session handlers ----

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

    async def _handle_session_send_message(self, params: Any) -> Any:
        """Long-running: stream runtime events as `stream/event` notifications.

        Each emitted event is wrapped in a notification whose `params.request_id`
        equals the JSON-RPC id of THIS send_message request (recovered from the
        `_current_request_id` ContextVar set by `_dispatch_request`).

        After the runtime stream is fully drained, returns a final response of
        the form `{"stopped_reason": ...}`.
        """
        from meta_harney.abstractions._types import Message

        p = params or {}
        sid = p.get("session_id")
        msg_dict = p.get("message")
        if not isinstance(sid, str) or not sid or not isinstance(msg_dict, dict):
            raise InvalidParams("session_id (str) and message (dict) required")

        try:
            message = Message.model_validate(msg_dict)
        except Exception as exc:  # pydantic ValidationError -> InvalidParams
            raise InvalidParams(f"invalid message: {exc}") from exc

        request_id = _current_request_id.get()
        stop_reason = "completed"
        async for event in self._runtime.stream(sid, message):
            await self._send_notification(
                "stream/event",
                {"request_id": request_id, "event": _serialize_event(event)},
            )
        return {"stopped_reason": stop_reason}

    # ---- cancel handlers ----

    async def _handle_session_cancel(self, params: Any) -> Any:
        """Request handler — returns {"cancelled": bool}.

        Unknown request_id is NOT an error; it returns {"cancelled": false} so
        clients can fire-and-forget cancels without racing against completion.
        """
        p = params or {}
        rid = p.get("request_id")
        if rid is None:
            raise InvalidParams("request_id required")
        task = self._inflight_by_request_id.get(rid)
        if task is None or task.done():
            return {"cancelled": False}
        task.cancel()
        return {"cancelled": True}

    async def _handle_cancel_notification(self, params: Any) -> None:
        """Notification handler for `$/cancelRequest` (LSP-style)."""
        p = params or {}
        rid = p.get("id")
        if rid is None:
            return
        task = self._inflight_by_request_id.get(rid)
        if task is not None and not task.done():
            task.cancel()

    async def _handle_session_load(self, params: Any) -> Any:
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


def _json_default(o: Any) -> Any:
    """Fallback JSON serializer for non-JSON-native types."""
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


# ---- streaming support ---------------------------------------------------
# `_current_request_id` lets long-running handlers (e.g. session.send_message)
# recover the JSON-RPC id of the request that invoked them, so they can embed
# it in correlated notifications. The dispatcher sets it for the duration of
# each handler call (see `_dispatch_request`). Task 6 (cancel) reuses this.
_current_request_id: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "_current_request_id", default=None
)


def _serialize_event(event: Any) -> Any:
    """Best-effort StreamEvent → JSON-safe dict."""
    if hasattr(event, "model_dump"):
        dumped = event.model_dump()
        return dumped
    if isinstance(event, dict):
        return event
    return {"repr": repr(event)}
