"""NullSink — discards all events. The framework default."""

from __future__ import annotations

from meta_harney.abstractions.trace import TraceEvent


class NullSink:
    """No-op sink. Useful as default; tests use it when trace is irrelevant."""

    async def emit(self, event: TraceEvent) -> None:
        return None

    async def flush(self) -> None:
        return None
