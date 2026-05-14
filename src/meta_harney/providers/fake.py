"""FakeLLMProvider — scripted, deterministic provider for testing the engine.

Each call to stream() consumes one FakeRound from the script. The round can
emit text (optionally chunked via split_on), tool calls, or both, followed
by a stop_reason. The provider records all calls in `provider.calls` for
test assertions.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from meta_harney.abstractions._types import Message
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)


class FakeRound(BaseModel):
    """One scripted LLM response."""

    text: str = ""
    split_on: str | None = None  # if set, text is split and each chunk emitted as a delta
    tool_calls: list[ProviderToolCall] = []
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class RecordedCall:
    """A snapshot of the inputs to one stream() call."""

    messages: list[Message]
    system_prompt: str
    tools: list[ToolSpec]
    config: ProviderCallConfig


@dataclass
class FakeLLMProvider:
    """LLMProvider impl that returns pre-scripted rounds in order."""

    rounds: list[FakeRound]
    calls: list[RecordedCall] = field(default_factory=list)
    _index: int = field(default=0, init=False)

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        self.calls.append(
            RecordedCall(
                messages=list(messages),
                system_prompt=system_prompt,
                tools=list(tools),
                config=config,
            )
        )

        if self._index >= len(self.rounds):
            raise RuntimeError(
                f"FakeLLMProvider script exhausted: {len(self.rounds)} rounds, "
                f"caller requested round {self._index + 1}"
            )
        round_ = self.rounds[self._index]
        self._index += 1

        # Emit text (chunked if split_on set)
        if round_.text:
            if round_.split_on is not None:
                for chunk in round_.text.split(round_.split_on):
                    yield ProviderTextDelta(text=chunk)
            else:
                yield ProviderTextDelta(text=round_.text)

        # Emit tool calls
        for tc in round_.tool_calls:
            yield tc

        # Always end with stream_done
        yield ProviderStreamDone(
            stop_reason=round_.stop_reason,
            input_tokens=round_.input_tokens,
            output_tokens=round_.output_tokens,
        )
