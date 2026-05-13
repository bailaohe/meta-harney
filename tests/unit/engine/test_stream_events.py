"""Tests for engine StreamEvent types (the engine-level event stream emitted to callers)."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolResult
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)


def test_text_delta() -> None:
    ev = TextDelta(text="hello")
    assert ev.kind == "text_delta"
    assert ev.text == "hello"


def test_thinking_delta() -> None:
    ev = ThinkingDelta(text="reasoning...")
    assert ev.kind == "thinking_delta"


def test_tool_call_started() -> None:
    ev = ToolCallStarted(
        tool_name="echo",
        invocation_id="inv-1",
        args={"x": 1},
    )
    assert ev.kind == "tool_call_started"
    assert ev.tool_name == "echo"


def test_tool_call_completed() -> None:
    ev = ToolCallCompleted(
        tool_name="echo",
        invocation_id="inv-1",
        result=ToolResult(success=True, output={"x": 1}),
    )
    assert ev.kind == "tool_call_completed"
    assert ev.result.success


def test_iteration_completed() -> None:
    ev = IterationCompleted(iteration=0)
    assert ev.kind == "iteration_completed"
    assert ev.iteration == 0


def test_turn_completed() -> None:
    ev = TurnCompleted(total_iterations=3)
    assert ev.kind == "turn_completed"
    assert ev.total_iterations == 3


def test_stream_event_union() -> None:
    events: list[StreamEvent] = [
        TextDelta(text="a"),
        ThinkingDelta(text="b"),
        ToolCallStarted(tool_name="t", invocation_id="i", args={}),
        ToolCallCompleted(
            tool_name="t",
            invocation_id="i",
            result=ToolResult(success=True, output=None),
        ),
        IterationCompleted(iteration=0),
        TurnCompleted(total_iterations=1),
    ]
    assert len(events) == 6
