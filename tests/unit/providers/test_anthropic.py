"""Tests for AnthropicProvider — real-LLM-API adapter.

Tests stub the anthropic SDK at the client boundary so they're deterministic
and don't make network calls.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.anthropic import AnthropicProvider, _convert_messages_to_anthropic
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
)


def test_anthropic_provider_constructs() -> None:
    p = AnthropicProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_anthropic_provider_requires_api_key() -> None:
    """Empty api_key should raise ConfigurationError."""
    from meta_harney.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="api_key"):
        AnthropicProvider(api_key="")


def test_convert_simple_user_message() -> None:
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    converted, extracted_system = _convert_messages_to_anthropic(msgs)
    assert converted == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]
    assert extracted_system is None


def test_convert_extracts_system_messages() -> None:
    """System-role messages are extracted and concatenated."""
    msgs = [
        Message(role="system", content=[TextBlock(text="be helpful")]),
        Message(role="system", content=[TextBlock(text="also be brief")]),
        Message(role="user", content=[TextBlock(text="hi")]),
    ]
    converted, extracted_system = _convert_messages_to_anthropic(msgs)
    assert extracted_system == "be helpful\n\nalso be brief"
    assert len(converted) == 1
    assert converted[0]["role"] == "user"


def test_convert_assistant_with_tool_call() -> None:
    msgs = [
        Message(role="user", content=[TextBlock(text="search")]),
        Message(role="assistant", content=[
            TextBlock(text="Let me check."),
            ToolCallBlock(invocation_id="t1", name="search", args={"query": "x"}),
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[1]["role"] == "assistant"
    assistant_blocks = converted[1]["content"]
    assert assistant_blocks[0] == {"type": "text", "text": "Let me check."}
    assert assistant_blocks[1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "search",
        "input": {"query": "x"},
    }


def test_convert_tool_result_message() -> None:
    """Tool-role message converts to user-role with tool_result content."""
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(
                invocation_id="t1",
                success=True,
                output="result text",
            )
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[0]["role"] == "user"
    block = converted[0]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "t1"
    assert "result text" in str(block["content"])


def test_convert_failed_tool_result_marks_is_error() -> None:
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(
                invocation_id="t1",
                success=False,
                output=None,
                error="boom",
            )
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block.get("is_error") is True
    assert "boom" in str(block["content"])


def test_convert_image_block() -> None:
    msgs = [
        Message(role="user", content=[
            ImageBlock(url="https://x/y.png", media_type="image/png"),
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["type"] == "url"
    assert block["source"]["url"] == "https://x/y.png"


class _FakeAnthropicStream:
    """Mimics anthropic SDK's stream context manager."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def __aenter__(self) -> "_FakeAnthropicStream":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        for event in self._events:
            yield event


def _make_event(event_type: str, **kwargs: Any) -> MagicMock:
    """Build a MagicMock that mimics an Anthropic SSE event."""
    m = MagicMock()
    m.type = event_type
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


async def test_stream_emits_text_delta() -> None:
    """Simple text response: one delta + stream_done."""
    text_block = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("text_delta", text="hello"),
    )
    message_stop = _make_event(
        "message_stop",
        message=_make_event(
            "message",
            stop_reason="end_turn",
            usage=_make_event("usage", input_tokens=10, output_tokens=5),
        ),
    )
    events = [text_block, message_stop]

    fake_messages_client = MagicMock()
    fake_messages_client.stream = MagicMock(return_value=_FakeAnthropicStream(events))

    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    text_events = [e for e in collected if isinstance(e, ProviderTextDelta)]
    done_events = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(text_events) >= 1
    assert text_events[0].text == "hello"
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "end_turn"
    assert done_events[0].input_tokens == 10
    assert done_events[0].output_tokens == 5


async def test_stream_emits_tool_call() -> None:
    """Tool use response: accumulates streaming JSON, yields ProviderToolCall."""
    tool_use_start = _make_event(
        "content_block_start",
        index=0,
        content_block=_make_event(
            "tool_use",
            id="toolu_01abc",
            name="search",
            input={},
        ),
    )
    json_delta_1 = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("input_json_delta", partial_json='{"query":'),
    )
    json_delta_2 = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("input_json_delta", partial_json='"hello"}'),
    )
    block_stop = _make_event("content_block_stop", index=0)
    message_stop = _make_event(
        "message_stop",
        message=_make_event(
            "message",
            stop_reason="tool_use",
            usage=_make_event("usage", input_tokens=10, output_tokens=5),
        ),
    )

    fake_messages_client = MagicMock()
    fake_messages_client.stream = MagicMock(
        return_value=_FakeAnthropicStream(
            [tool_use_start, json_delta_1, json_delta_2, block_stop, message_stop]
        )
    )
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="search hello")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "search"
    assert tool_calls[0].args == {"query": "hello"}
    assert tool_calls[0].invocation_id == "toolu_01abc"


async def test_anthropic_429_maps_to_retryable() -> None:
    """RateLimitError → RetryableProviderError."""
    from anthropic import APIStatusError

    from meta_harney.errors import RetryableProviderError

    fake_messages_client = MagicMock()

    def _raise_rate_limit(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 429
        raise APIStatusError("rate limited", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_rate_limit)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass


async def test_anthropic_500_maps_to_retryable() -> None:
    """5xx → RetryableProviderError."""
    from anthropic import APIStatusError

    from meta_harney.errors import RetryableProviderError

    fake_messages_client = MagicMock()

    def _raise_500(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 503
        raise APIStatusError("upstream error", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_500)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass


async def test_anthropic_401_maps_to_non_retryable() -> None:
    """401 → NonRetryableProviderError."""
    from anthropic import APIStatusError

    from meta_harney.errors import NonRetryableProviderError

    fake_messages_client = MagicMock()

    def _raise_401(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 401
        raise APIStatusError("auth failed", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_401)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(NonRetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass
