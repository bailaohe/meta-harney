"""LLM provider abstraction: LLMProvider Protocol + ProviderStreamEvent + ToolSpec.

Provider implementations (Anthropic, OpenAI, etc.) plug in here. The engine
calls `provider.stream(...)` once per LLM round and consumes the async
iterator of ProviderStreamEvent until ProviderStreamDone is yielded.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from meta_harney.abstractions._types import Message


class ToolSpec(BaseModel):
    """Description of a tool exposed to the LLM.

    Engine derives ToolSpec from a registered BaseTool's name, description,
    and input_schema before calling provider.stream(...).
    """

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ProviderCallConfig(BaseModel):
    """Per-call provider parameters."""

    model: str
    max_tokens: int | None = None
    temperature: float | None = None


class _ProviderStreamEventBase(BaseModel):
    type: str


class ProviderTextDelta(_ProviderStreamEventBase):
    """Incremental text chunk emitted by the LLM."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ProviderToolCall(_ProviderStreamEventBase):
    """A completed tool call request from the LLM.

    Provider implementations should buffer streaming JSON tool args internally
    and yield this event only when the full tool call is ready.
    """

    type: Literal["tool_call"] = "tool_call"
    invocation_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ProviderStreamDone(_ProviderStreamEventBase):
    """Terminal event for a single LLM round."""

    type: Literal["stream_done"] = "stream_done"
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"]
    input_tokens: int | None = None
    output_tokens: int | None = None


ProviderStreamEvent = ProviderTextDelta | ProviderToolCall | ProviderStreamDone


class LLMProvider(Protocol):
    """Streams one LLM completion. Yields ProviderStreamEvents.

    Implementations MUST:
    - yield at least one ProviderStreamDone as the final event
    - raise RetryableProviderError on 429/5xx/network errors
    - raise NonRetryableProviderError on auth/4xx/invalid-request errors
    """

    def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]: ...
