"""Contract tests for LLMProvider implementations."""

from __future__ import annotations

from abc import abstractmethod

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
)


class LLMProviderContract:
    """Contract tests every LLMProvider must pass.

    Subclass and implement `make_provider()`. The provider must be scripted
    or otherwise set up to respond to a single text-only round.
    """

    @abstractmethod
    def make_provider(self) -> LLMProvider: ...

    async def test_stream_yields_terminal_stream_done(self) -> None:
        provider = self.make_provider()
        events = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="x"),
        ):
            events.append(ev)
        assert len(events) >= 1
        assert isinstance(events[-1], ProviderStreamDone), (
            f"last event must be ProviderStreamDone, got {type(events[-1]).__name__}"
        )

    async def test_stream_stop_reason_is_valid(self) -> None:
        provider = self.make_provider()
        events = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="x"),
        ):
            events.append(ev)
        done = [e for e in events if isinstance(e, ProviderStreamDone)][-1]
        assert done.stop_reason in {"end_turn", "tool_use", "max_tokens", "error"}
