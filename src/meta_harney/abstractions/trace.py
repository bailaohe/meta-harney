"""Trace abstraction: TraceEvent model + TraceSink Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.8.
Reserved kind vocabulary in Appendix A of the spec.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """A single observation event in the agent's life.

    `kind` is open-typed (str) for forward compatibility; the spec reserves
    a vocabulary (Appendix A) and recommends business prefixes (e.g., crm.*)
    for custom kinds. The framework does not enforce prefix validation —
    that is a TraceSink implementation decision.
    """

    ts: datetime
    session_id: str
    kind: str
    span_id: str
    parent_span_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class TraceSink(Protocol):
    """Receives all trace events emitted by the engine.

    Implementations MUST NOT raise to the engine: any exception is caught
    by the engine and logged to stderr, never propagated. This is the
    "observability shouldn't kill the system" rule.
    """

    async def emit(self, event: TraceEvent) -> None: ...

    async def flush(self) -> None: ...
