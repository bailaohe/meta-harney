"""Tests for TraceEvent + TraceSink Protocol."""

from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def test_trace_event_minimal():
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="turn.started",
        span_id="span-a",
        payload={},
    )
    assert ev.parent_span_id is None
    assert ev.duration_ms is None


def test_trace_event_with_parent():
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="tool.completed",
        span_id="span-b",
        parent_span_id="span-a",
        payload={"success": True},
        duration_ms=123.4,
    )
    assert ev.parent_span_id == "span-a"
    assert ev.duration_ms == 123.4


async def test_protocol_satisfied_by_duck_typing():
    class CollectingSink:
        def __init__(self) -> None:
            self.events: list[TraceEvent] = []
            self.flushed = False

        async def emit(self, event: TraceEvent) -> None:
            self.events.append(event)

        async def flush(self) -> None:
            self.flushed = True

    # Use the concrete type so mypy knows about .events and .flushed
    sink = CollectingSink()
    _protocol_sink: TraceSink = sink  # verify duck-typing compatibility
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="turn.started",
        span_id="x",
        payload={},
    )
    await sink.emit(ev)
    await sink.flush()
    assert len(sink.events) == 1
    assert sink.flushed
