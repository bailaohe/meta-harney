"""Contract tests for TraceSink implementations."""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def _event(kind: str = "test.kind", span_id: str = "x") -> TraceEvent:
    return TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind=kind,
        span_id=span_id,
        payload={},
    )


class TraceSinkContract:
    """Contract tests every TraceSink must pass."""

    @abstractmethod
    def make_sink(self) -> TraceSink: ...

    async def test_emit_does_not_raise(self) -> None:
        sink = self.make_sink()
        await sink.emit(_event())  # must complete without exception

    async def test_flush_does_not_raise(self) -> None:
        sink = self.make_sink()
        await sink.flush()  # idempotent with empty buffer

    async def test_emit_many_then_flush(self) -> None:
        sink = self.make_sink()
        for i in range(50):
            await sink.emit(_event(span_id=str(i)))
        await sink.flush()  # must not raise

    async def test_concurrent_emit_safe(self) -> None:
        sink = self.make_sink()

        async def burst() -> None:
            for i in range(10):
                await sink.emit(_event(span_id=f"burst-{i}"))

        await asyncio.gather(*(burst() for _ in range(5)))
        await sink.flush()
