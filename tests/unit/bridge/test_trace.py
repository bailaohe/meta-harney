"""Tests for BridgeTraceSink + telemetry/subscribe + tools.list."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.bridge.trace import BridgeTraceSink


@pytest.mark.asyncio
async def test_sink_drops_events_when_unsubscribed() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    async def send_note(method: str, params: dict[str, Any]) -> None:
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
    sent: list[tuple[str, dict[str, Any]]] = []

    async def send_note(method: str, params: dict[str, Any]) -> None:
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
    assert params["payload"]["kind"] == "test.event"
    assert params["payload"]["payload"] == {"x": 1}


@pytest.mark.asyncio
async def test_sink_handles_send_errors_silently() -> None:
    async def boom(method: str, params: dict[str, Any]) -> None:
        raise RuntimeError("network down")

    sink = BridgeTraceSink(send_notification=boom)
    sink.set_enabled(True)
    ev = TraceEvent(ts=datetime.now(timezone.utc), session_id="s", kind="x", span_id="sp")
    # Must not raise — observability shouldn't kill the engine
    await sink.emit(ev)


@pytest.mark.asyncio
async def test_sink_flush_is_noop() -> None:
    """TraceSink protocol requires `flush`; BridgeTraceSink has nothing to drain."""

    async def send_note(method: str, params: dict[str, Any]) -> None:
        return None

    sink = BridgeTraceSink(send_notification=send_note)
    # Must not raise regardless of enabled state.
    await sink.flush()
    sink.set_enabled(True)
    await sink.flush()
