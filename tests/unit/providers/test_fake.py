"""Tests for FakeLLMProvider — scripted responses for engine tests."""
from __future__ import annotations

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound


async def _drain(provider: FakeLLMProvider, **kwargs: object) -> list[ProviderStreamEvent]:
    out: list[ProviderStreamEvent] = []
    async for ev in provider.stream(
        messages=kwargs.get("messages", []),  # type: ignore[arg-type]
        system_prompt=kwargs.get("system_prompt", ""),  # type: ignore[arg-type]
        tools=kwargs.get("tools", []),  # type: ignore[arg-type]
        config=kwargs.get("config", ProviderCallConfig(model="fake")),  # type: ignore[arg-type]
    ):
        out.append(ev)
    return out


async def test_single_text_round() -> None:
    provider = FakeLLMProvider(
        rounds=[FakeRound(text="Hello, world!", stop_reason="end_turn")]
    )
    events = await _drain(provider)
    assert len(events) == 2
    assert isinstance(events[0], ProviderTextDelta)
    assert events[0].text == "Hello, world!"
    assert isinstance(events[1], ProviderStreamDone)
    assert events[1].stop_reason == "end_turn"


async def test_text_chunked() -> None:
    provider = FakeLLMProvider(
        rounds=[FakeRound(text="ab|cd|ef", stop_reason="end_turn", split_on="|")]
    )
    events = await _drain(provider)
    texts = [e.text for e in events if isinstance(e, ProviderTextDelta)]
    assert texts == ["ab", "cd", "ef"]


async def test_tool_call_round() -> None:
    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[ProviderToolCall(invocation_id="inv1", name="echo", args={"x": 1})],
                stop_reason="tool_use",
            )
        ]
    )
    events = await _drain(provider)
    assert any(isinstance(e, ProviderToolCall) for e in events)
    done = next(e for e in events if isinstance(e, ProviderStreamDone))
    assert done.stop_reason == "tool_use"


async def test_multi_round_sequential() -> None:
    """Each call to stream() consumes the next scripted round."""
    provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="first", stop_reason="end_turn"),
            FakeRound(text="second", stop_reason="end_turn"),
        ]
    )
    e1 = await _drain(provider)
    e2 = await _drain(provider)
    first_delta = next(x for x in e1 if isinstance(x, ProviderTextDelta))
    second_delta = next(x for x in e2 if isinstance(x, ProviderTextDelta))
    assert first_delta.text == "first"
    assert second_delta.text == "second"


async def test_exhausted_script_raises() -> None:
    provider = FakeLLMProvider(rounds=[FakeRound(text="only", stop_reason="end_turn")])
    await _drain(provider)
    with pytest.raises(RuntimeError, match="script exhausted"):
        await _drain(provider)


async def test_records_calls() -> None:
    """FakeLLMProvider records args for assertion in tests."""
    provider = FakeLLMProvider(rounds=[FakeRound(text="x", stop_reason="end_turn")])
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    await _drain(provider, messages=msgs, system_prompt="be helpful")
    assert len(provider.calls) == 1
    assert provider.calls[0].system_prompt == "be helpful"
    assert provider.calls[0].messages == msgs


from meta_harney.providers.base import LLMProvider as _LLMProvider
from tests.contracts.llm_provider import LLMProviderContract


class TestFakeLLMProviderContract(LLMProviderContract):
    def make_provider(self) -> _LLMProvider:
        return FakeLLMProvider(
            rounds=[FakeRound(text="ok", stop_reason="end_turn")]
        )
