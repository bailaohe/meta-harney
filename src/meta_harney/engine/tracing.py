"""Tracing helpers for the engine: span_id generation + safe sink emission.

The engine uses these directly; tools/hooks receive `current_span_id` and a
`new_span_id` callable via ToolContext to emit their own child spans.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def new_span_id() -> str:
    """Generate a short (16 hex chars) span id."""
    return uuid.uuid4().hex[:16]


async def emit_event(
    sink: TraceSink,
    *,
    session_id: str,
    kind: str,
    span_id: str,
    parent_span_id: str | None,
    payload: dict[str, Any],
    duration_ms: float | None = None,
) -> None:
    """Emit a TraceEvent to the sink, swallowing any sink exceptions.

    Per spec §7.2 rule ②: observability MUST NOT kill business. If the
    sink raises, the engine logs to stderr and continues.
    """
    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id=session_id,
        kind=kind,
        span_id=span_id,
        parent_span_id=parent_span_id,
        payload=payload,
        duration_ms=duration_ms,
    )
    try:
        await sink.emit(event)
    except Exception as exc:
        print(
            f"[meta_harney] trace sink failed for kind={kind!r}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
