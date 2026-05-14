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
        self._inflight: set[asyncio.Task[None]] = set()
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
                    self._spawn(self._dispatch_request(msg))
                elif isinstance(msg, JsonRpcNotification):
                    # Lifecycle notifications (e.g. `exit`) must run inline so
                    # the read loop observes their state changes immediately.
                    if msg.method in self._notification_handlers:
                        await self._dispatch_notification(msg)
                    else:
                        self._spawn(self._dispatch_notification(msg))
                else:
                    # JsonRpcResponse: bridge doesn't currently send outbound
                    # requests in this skeleton — Task 7 will add a pending-table
                    logger.debug("response received but no pending request table yet")
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
