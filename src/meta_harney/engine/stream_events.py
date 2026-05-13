"""Engine-level StreamEvent types.

These are emitted by `engine.loop.run_turn()` to the caller. They are
HIGHER level than ProviderStreamEvent: they describe "what the agent did",
not "what the LLM said". See spec §5.2 for the StreamEvent vs TraceEvent
distinction.

Six kinds:
- text_delta: incremental assistant text
- thinking_delta: incremental extended-thinking text
- tool_call_started: a tool was invoked (permission cleared, executing)
- tool_call_completed: a tool returned (success or failure)
- iteration_completed: one LLM-round + optional tool-batch is done
- turn_completed: the whole agent turn is done
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import ToolResult


class _StreamEventBase(BaseModel):
    kind: str


class TextDelta(_StreamEventBase):
    kind: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(_StreamEventBase):
    kind: Literal["thinking_delta"] = "thinking_delta"
    text: str


class ToolCallStarted(_StreamEventBase):
    kind: Literal["tool_call_started"] = "tool_call_started"
    tool_name: str
    invocation_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolCallCompleted(_StreamEventBase):
    kind: Literal["tool_call_completed"] = "tool_call_completed"
    tool_name: str
    invocation_id: str
    result: ToolResult


class IterationCompleted(_StreamEventBase):
    kind: Literal["iteration_completed"] = "iteration_completed"
    iteration: int


class TurnCompleted(_StreamEventBase):
    kind: Literal["turn_completed"] = "turn_completed"
    total_iterations: int


StreamEvent = (
    TextDelta
    | ThinkingDelta
    | ToolCallStarted
    | ToolCallCompleted
    | IterationCompleted
    | TurnCompleted
)
