"""Tests for engine.tracing helpers."""

from __future__ import annotations

from datetime import datetime

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.engine.tracing import emit_event, new_span_id


def test_new_span_id_returns_short_hex_string() -> None:
    sid = new_span_id()
    assert isinstance(sid, str)
    assert len(sid) == 16
    # Each call gives a unique id
    assert new_span_id() != sid


async def test_emit_event_calls_sink() -> None:
    class CollectingSink:
        def __init__(self) -> None:
            self.events: list[TraceEvent] = []

        async def emit(self, event: TraceEvent) -> None:
            self.events.append(event)

        async def flush(self) -> None:
            pass

    sink = CollectingSink()
    await emit_event(
        sink,
        session_id="s1",
        kind="turn.started",
        span_id="span-1",
        parent_span_id=None,
        payload={"user_message_id": "m1"},
    )
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.session_id == "s1"
    assert ev.kind == "turn.started"
    assert ev.span_id == "span-1"
    assert ev.payload == {"user_message_id": "m1"}
    assert isinstance(ev.ts, datetime)


async def test_emit_event_swallows_sink_exceptions() -> None:
    """Sink exceptions MUST NOT propagate — observability shouldn't kill business."""

    class BrokenSink:
        async def emit(self, event: TraceEvent) -> None:
            raise RuntimeError("kaboom")

        async def flush(self) -> None:
            pass

    # Should not raise.
    await emit_event(
        BrokenSink(),
        session_id="s1",
        kind="x",
        span_id="sp",
        parent_span_id=None,
        payload={},
    )


async def test_emit_event_with_duration_ms() -> None:
    class CollectingSink:
        def __init__(self) -> None:
            self.events: list[TraceEvent] = []

        async def emit(self, event: TraceEvent) -> None:
            self.events.append(event)

        async def flush(self) -> None:
            pass

    sink = CollectingSink()
    await emit_event(
        sink,
        session_id="s",
        kind="tool.completed",
        span_id="x",
        parent_span_id="y",
        payload={},
        duration_ms=42.5,
    )
    assert sink.events[0].duration_ms == 42.5
