"""Tests for LLMProvider Protocol + ProviderStreamEvent + ToolSpec."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)


def test_tool_spec_fields() -> None:
    spec = ToolSpec(
        name="echo",
        description="Echoes input.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    assert spec.name == "echo"
    assert spec.input_schema["type"] == "object"


def test_provider_text_delta() -> None:
    ev = ProviderTextDelta(text="hello")
    assert ev.type == "text_delta"
    assert ev.text == "hello"


def test_provider_tool_call() -> None:
    ev = ProviderToolCall(invocation_id="inv1", name="echo", args={"text": "hi"})
    assert ev.type == "tool_call"
    assert ev.invocation_id == "inv1"
    assert ev.name == "echo"
    assert ev.args == {"text": "hi"}


def test_provider_stream_done_minimal() -> None:
    ev = ProviderStreamDone(stop_reason="end_turn")
    assert ev.type == "stream_done"
    assert ev.stop_reason == "end_turn"
    assert ev.input_tokens is None


def test_provider_stream_done_with_usage() -> None:
    ev = ProviderStreamDone(stop_reason="tool_use", input_tokens=100, output_tokens=50)
    assert ev.input_tokens == 100
    assert ev.output_tokens == 50


def test_provider_call_config_defaults() -> None:
    cfg = ProviderCallConfig(model="gpt-test")
    assert cfg.model == "gpt-test"
    assert cfg.max_tokens is None
    assert cfg.temperature is None


async def test_protocol_duck_typing() -> None:
    class FakeProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            yield ProviderTextDelta(text="ok")
            yield ProviderStreamDone(stop_reason="end_turn")

    p: LLMProvider = FakeProvider()
    events = []
    async for e in p.stream(
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        system_prompt="you help",
        tools=[],
        config=ProviderCallConfig(model="gpt-test"),
    ):
        events.append(e)
    assert len(events) == 2
    assert events[0].type == "text_delta"
    assert events[1].type == "stream_done"
