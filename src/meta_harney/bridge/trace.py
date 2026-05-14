"""BridgeTraceSink — forwards trace events as ``telemetry/event`` notifications.

Implements the :class:`~meta_harney.abstractions.trace.TraceSink` Protocol
(``emit`` + ``flush``). Honours the observability contract: ``emit`` MUST NOT
raise, otherwise a buggy client connection could kill an in-flight agent turn.
Subscription is gated by ``set_enabled`` so the framework doesn't waste
bandwidth on clients that don't care about telemetry.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.abstractions.trace import TraceEvent

logger = logging.getLogger("meta_harney.bridge.trace")

SendNotification = Callable[[str, dict[str, Any]], Awaitable[None]]


class BridgeTraceSink:
    """Forwards TraceEvents to the bridge client when subscription is enabled.

    The send callback typically points at ``BridgeServer._send_notification``.
    Exceptions raised by the callback (e.g. broken pipe) are logged and
    swallowed; the engine is shielded from observability failures.
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
            # Observability shouldn't kill the engine. Log and drop.
            logger.exception("BridgeTraceSink: failed to forward event")

    async def flush(self) -> None:
        # No internal buffering — every emit forwards immediately. Provided to
        # satisfy the TraceSink Protocol.
        return None
