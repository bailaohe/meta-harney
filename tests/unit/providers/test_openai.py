"""Tests for OpenAIProvider — Chat Completions adapter."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)
from meta_harney.providers.openai import (
    OpenAIProvider,
    _convert_messages_to_openai,
    _convert_tools_to_openai,
)


class _FakeOpenAIStream:
    """AsyncIterable of fake chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _make_chunk(
    *,
    text: str | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
) -> MagicMock:
    """Build a MagicMock chunk that mimics OpenAI ChatCompletionChunk."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()

    delta.content = text
    delta.tool_calls = None
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _make_usage(prompt_tokens: int, completion_tokens: int) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt_tokens
    u.completion_tokens = completion_tokens
    return u


def test_openai_provider_constructs() -> None:
    p = OpenAIProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_openai_provider_requires_api_key() -> None:
    """Empty api_key should raise ConfigurationError."""
    from meta_harney.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="api_key"):
        OpenAIProvider(api_key="")


def test_convert_simple_user_message_with_system_prompt() -> None:
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    converted = _convert_messages_to_openai(msgs, system_prompt="be helpful")
    assert converted == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]


def test_convert_inband_system_message() -> None:
    """System-role messages from history stay in-band (not extracted)."""
    msgs = [
        Message(role="system", content=[TextBlock(text="be helpful")]),
        Message(role="user", content=[TextBlock(text="hi")]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    # No runtime system_prompt prepended because it's empty
    assert converted == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]


def test_convert_assistant_with_tool_call() -> None:
    msgs = [
        Message(role="user", content=[TextBlock(text="search")]),
        Message(role="assistant", content=[
            TextBlock(text="Let me check."),
            ToolCallBlock(invocation_id="call_1", name="search", args={"q": "x"}),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assistant_msg = converted[-1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Let me check."
    assert assistant_msg["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "search", "arguments": '{"q": "x"}'},
    }]


def test_convert_assistant_tool_call_only_no_text() -> None:
    """Assistant message with only ToolCallBlocks: content is None."""
    msgs = [
        Message(role="assistant", content=[
            ToolCallBlock(invocation_id="c1", name="f", args={}),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["content"] is None
    assert len(converted[0]["tool_calls"]) == 1


def test_convert_tool_result_message() -> None:
    """tool role → OpenAI tool role with tool_call_id."""
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(invocation_id="c1", success=True, output="result text"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["role"] == "tool"
    assert converted[0]["tool_call_id"] == "c1"
    assert "result text" in converted[0]["content"]


def test_convert_failed_tool_result_includes_error() -> None:
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(invocation_id="c1", success=False, output=None, error="boom"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert "boom" in converted[0]["content"]


def test_convert_image_block_uses_image_url() -> None:
    """ImageBlock with url → OpenAI image_url content part."""
    msgs = [
        Message(role="user", content=[
            TextBlock(text="see this"),
            ImageBlock(url="https://x/y.png", media_type="image/png"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    content = converted[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "see this"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://x/y.png"},
    }


def test_convert_image_block_base64() -> None:
    """Base64 ImageBlock → data URL in image_url."""
    msgs = [
        Message(role="user", content=[
            ImageBlock(data="iVBORw0KGgo...", media_type="image/png"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    content = converted[0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_convert_tools_to_openai_basic() -> None:
    tools = [
        ToolSpec(
            name="echo",
            description="Echoes input",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        ),
    ]
    converted = _convert_tools_to_openai(tools)
    assert converted == [{
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echoes input",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
    }]


def test_convert_empty_tools() -> None:
    assert _convert_tools_to_openai([]) == []


async def test_stream_emits_text_delta_and_done() -> None:
    """Simple text response: chunks with text + final finish_reason."""
    chunks = [
        _make_chunk(text="hello "),
        _make_chunk(text="world"),
        _make_chunk(finish_reason="stop"),
        _make_chunk(usage=_make_usage(prompt_tokens=10, completion_tokens=2)),
    ]

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch(
        "meta_harney.providers.openai.AsyncOpenAI",
        return_value=fake_client,
    ):
        provider = OpenAIProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    text_events = [e for e in collected if isinstance(e, ProviderTextDelta)]
    assert [e.text for e in text_events] == ["hello ", "world"]
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(done) == 1
    assert done[0].stop_reason == "end_turn"
    assert done[0].input_tokens == 10
    assert done[0].output_tokens == 2


async def test_stream_finish_reason_length_maps_to_max_tokens() -> None:
    chunks = [
        _make_chunk(text="incomplete"),
        _make_chunk(finish_reason="length"),
    ]
    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected = [
            ev
            async for ev in provider.stream(
                messages=[Message(role="user", content=[TextBlock(text="hi")])],
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="gpt-4"),
            )
        ]
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert done[0].stop_reason == "max_tokens"


def _make_tool_call_delta(
    *,
    index: int,
    id_: str | None = None,
    name: str | None = None,
    arguments: str = "",
) -> MagicMock:
    tc = MagicMock()
    tc.index = index
    tc.id = id_
    tc.type = "function"
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc.function = func
    return tc


def _make_chunk_with_tool_calls(
    *,
    tool_call_deltas: list[Any] | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
) -> MagicMock:
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = tool_call_deltas
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


async def test_stream_emits_tool_call() -> None:
    """OpenAI streams tool_calls as per-index deltas; accumulate and emit one ProviderToolCall."""
    chunks = [
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, id_="call_abc", name="search"),
            ],
        ),
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, arguments='{"query":'),
            ],
        ),
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, arguments='"hello"}'),
            ],
        ),
        _make_chunk_with_tool_calls(finish_reason="tool_calls"),
    ]

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="search hello")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].invocation_id == "call_abc"
    assert tool_calls[0].name == "search"
    assert tool_calls[0].args == {"query": "hello"}
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert done[0].stop_reason == "tool_use"


async def test_stream_multiple_tool_calls() -> None:
    """Two tool calls at different indices accumulate independently."""
    chunks = [
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, id_="c1", name="f1", arguments='{"a":1}'),
                _make_tool_call_delta(index=1, id_="c2", name="f2", arguments='{"b":2}'),
            ],
        ),
        _make_chunk_with_tool_calls(finish_reason="tool_calls"),
    ]

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 2
    by_id = {tc.invocation_id: tc for tc in tool_calls}
    assert by_id["c1"].name == "f1"
    assert by_id["c1"].args == {"a": 1}
    assert by_id["c2"].name == "f2"
    assert by_id["c2"].args == {"b": 2}
