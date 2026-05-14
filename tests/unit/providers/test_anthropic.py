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
from tests.contracts.llm_provider import LLMProviderContract


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
    assert converted == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
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
        Message(
            role="assistant",
            content=[
                TextBlock(text="Let me check."),
                ToolCallBlock(invocation_id="t1", name="search", args={"query": "x"}),
            ],
        ),
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
        Message(
            role="tool",
            content=[
                ToolResultBlock(
                    invocation_id="t1",
                    success=True,
                    output="result text",
                )
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[0]["role"] == "user"
    block = converted[0]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "t1"
    assert "result text" in str(block["content"])


def test_convert_failed_tool_result_marks_is_error() -> None:
    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(
                    invocation_id="t1",
                    success=False,
                    output=None,
                    error="boom",
                )
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block.get("is_error") is True
    assert "boom" in str(block["content"])


def test_convert_image_block() -> None:
    msgs = [
        Message(
            role="user",
            content=[
                ImageBlock(url="https://x/y.png", media_type="image/png"),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["type"] == "url"
    assert block["source"]["url"] == "https://x/y.png"


def test_convert_image_block_base64() -> None:
    """ImageBlock with base64 data converts to source.type='base64'."""
    msgs = [
        Message(
            role="user",
            content=[
                ImageBlock(data="iVBORw0KGgo...", media_type="image/png"),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    assert block["source"]["data"] == "iVBORw0KGgo..."


class _FakeAnthropicStream:
    """Mimics anthropic SDK's stream context manager."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def __aenter__(self) -> _FakeAnthropicStream:
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


def test_convert_tool_result_with_dict_output_serializes_json() -> None:
    """Successful ToolResult with dict output uses JSON, not Python repr."""
    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(
                    invocation_id="c1",
                    success=True,
                    output={"id": "C-001", "name": "Acme"},
                ),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    result_block = converted[0]["content"][0]
    assert result_block["type"] == "tool_result"
    # Must be JSON (double quotes), not Python repr (single quotes)
    assert result_block["content"] == '{"id": "C-001", "name": "Acme"}'


def test_convert_tool_result_with_none_output_empty_content() -> None:
    """Successful ToolResult with output=None produces empty content, not 'None'."""
    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(invocation_id="c1", success=True, output=None),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[0]["content"][0]["content"] == ""


class TestAnthropicProviderContract(LLMProviderContract):
    """AnthropicProvider passes the standard LLMProvider contract."""

    @pytest.fixture(autouse=True)
    def _stub_anthropic_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace AsyncAnthropic with a mock for the duration of each test."""

        def _factory() -> MagicMock:
            text_block = _make_event(
                "content_block_delta",
                index=0,
                delta=_make_event("text_delta", text="ok"),
            )
            message_stop = _make_event(
                "message_stop",
                message=_make_event(
                    "message",
                    stop_reason="end_turn",
                    usage=_make_event("usage", input_tokens=1, output_tokens=1),
                ),
            )
            fake_messages_client = MagicMock()
            fake_messages_client.stream = MagicMock(
                return_value=_FakeAnthropicStream([text_block, message_stop])
            )
            fake_client = MagicMock()
            fake_client.messages = fake_messages_client
            return fake_client

        monkeypatch.setattr(
            "meta_harney.providers.anthropic.AsyncAnthropic",
            lambda **kwargs: _factory(),
        )

    def make_provider(self) -> AnthropicProvider:
        return AnthropicProvider(api_key="test-contract")


def test_provider_thinking_delta_construction() -> None:
    """ProviderThinkingDelta is a valid stream event variant."""
    from meta_harney.providers.base import (
        ProviderStreamEvent,  # noqa: F401
        ProviderThinkingDelta,
    )

    ev = ProviderThinkingDelta(text="reasoning step 1")
    assert ev.text == "reasoning step 1"
    assert ev.type == "thinking_delta"

    # Must be a member of ProviderStreamEvent union
    def accepts_event(_: ProviderStreamEvent) -> None:
        pass

    accepts_event(ev)  # type-checker enforcement; no runtime assertion needed


async def test_anthropic_thinking_budget_passed_through() -> None:
    """Provider with thinking_budget=N adds thinking kwarg to API call."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import ProviderCallConfig

    captured_kwargs: dict[str, object] = {}

    class _FakeStreamCM:
        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> None:
            raise StopAsyncIteration

    def _fake_stream(**kwargs: object) -> _FakeStreamCM:
        captured_kwargs.update(kwargs)
        return _FakeStreamCM()

    fake_client = MagicMock()
    fake_client.messages.stream = _fake_stream

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        async for _ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            pass

    assert captured_kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 4096}


async def test_anthropic_no_thinking_kwarg_when_budget_none() -> None:
    """Provider with default thinking_budget=None does NOT add thinking kwarg."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import ProviderCallConfig

    captured_kwargs: dict[str, object] = {}

    class _FakeStreamCM:
        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> None:
            raise StopAsyncIteration

    def _fake_stream(**kwargs: object) -> _FakeStreamCM:
        captured_kwargs.update(kwargs)
        return _FakeStreamCM()

    fake_client = MagicMock()
    fake_client.messages.stream = _fake_stream

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test")
        async for _ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            pass

    assert "thinking" not in captured_kwargs


async def test_anthropic_thinking_delta_emits_provider_thinking_delta() -> None:
    """SSE thinking_delta → ProviderThinkingDelta."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamDone,
        ProviderThinkingDelta,
    )

    # Build fake SSE events: content_block_start(thinking) → content_block_delta(thinking_delta)
    # → content_block_stop → message_stop
    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "thinking"

    cb_delta = MagicMock()
    cb_delta.type = "content_block_delta"
    cb_delta.index = 0
    cb_delta.delta = MagicMock()
    cb_delta.delta.type = "thinking_delta"
    cb_delta.delta.thinking = "let me think..."

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [cb_start, cb_delta, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    thinking = [e for e in collected if isinstance(e, ProviderThinkingDelta)]
    assert len(thinking) == 1
    assert thinking[0].text == "let me think..."
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(done) == 1


async def test_anthropic_redacted_thinking_silently_skipped() -> None:
    """redacted_thinking content block with no data field → silently handled."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderRedactedThinking,
        ProviderStreamDone,
        ProviderThinkingDelta,
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "redacted_thinking"
    cb_start.content_block.data = ""  # Empty data field

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [cb_start, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    # Phase 7: ProviderRedactedThinking is now emitted (not silently skipped)
    redacted = [e for e in collected if isinstance(e, ProviderRedactedThinking)]
    assert len(redacted) == 1
    assert redacted[0].data == ""
    # No ProviderThinkingDelta yielded
    assert not any(isinstance(e, ProviderThinkingDelta) for e in collected)
    # Stream completes normally
    assert any(isinstance(e, ProviderStreamDone) for e in collected)


async def test_anthropic_thinking_block_emit_with_signature_accumulation() -> None:
    """Provider buffers thinking_delta + signature_delta and emits one
    ProviderThinkingBlock at content_block_stop."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderThinkingBlock,
        ProviderThinkingDelta,
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "thinking"

    text_delta_1 = MagicMock()
    text_delta_1.type = "content_block_delta"
    text_delta_1.index = 0
    text_delta_1.delta = MagicMock()
    text_delta_1.delta.type = "thinking_delta"
    text_delta_1.delta.thinking = "let me "

    text_delta_2 = MagicMock()
    text_delta_2.type = "content_block_delta"
    text_delta_2.index = 0
    text_delta_2.delta = MagicMock()
    text_delta_2.delta.type = "thinking_delta"
    text_delta_2.delta.thinking = "think..."

    sig_delta_1 = MagicMock()
    sig_delta_1.type = "content_block_delta"
    sig_delta_1.index = 0
    sig_delta_1.delta = MagicMock()
    sig_delta_1.delta.type = "signature_delta"
    sig_delta_1.delta.signature = "sig-pa"

    sig_delta_2 = MagicMock()
    sig_delta_2.type = "content_block_delta"
    sig_delta_2.index = 0
    sig_delta_2.delta = MagicMock()
    sig_delta_2.delta.type = "signature_delta"
    sig_delta_2.delta.signature = "rt2"

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [
        cb_start,
        text_delta_1,
        text_delta_2,
        sig_delta_1,
        sig_delta_2,
        cb_stop,
        msg_stop,
    ]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    # Live stream: 2 ProviderThinkingDelta (unchanged Phase 6 behavior)
    deltas = [e for e in collected if isinstance(e, ProviderThinkingDelta)]
    assert [d.text for d in deltas] == ["let me ", "think..."]

    # Persistence: exactly 1 ProviderThinkingBlock with concatenated text + signature
    blocks = [e for e in collected if isinstance(e, ProviderThinkingBlock)]
    assert len(blocks) == 1
    assert blocks[0].text == "let me think..."
    assert blocks[0].signature == "sig-part2"


async def test_anthropic_redacted_thinking_emits_provider_event() -> None:
    """content_block_start with redacted_thinking → ProviderRedactedThinking immediately."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderRedactedThinking,
        ProviderStreamEvent,  # noqa: F401
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "redacted_thinking"
    cb_start.content_block.data = "opaque-blob-xyz"

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [cb_start, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    redacted = [e for e in collected if isinstance(e, ProviderRedactedThinking)]
    assert len(redacted) == 1
    assert redacted[0].data == "opaque-blob-xyz"


def test_convert_thinking_block_to_anthropic_wire_format() -> None:
    """ThinkingBlock in assistant content → {type:thinking, thinking, signature}."""
    from meta_harney.abstractions._types import Message, ThinkingBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="assistant",
            content=[ThinkingBlock(text="reasoning", signature="sig1")],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    content = converted[0]["content"]
    assert content[0] == {
        "type": "thinking",
        "thinking": "reasoning",
        "signature": "sig1",
    }


def test_convert_redacted_thinking_block_to_anthropic_wire_format() -> None:
    from meta_harney.abstractions._types import Message, RedactedThinkingBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="assistant",
            content=[RedactedThinkingBlock(data="opaque-xyz")],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    content = converted[0]["content"]
    assert content[0] == {"type": "redacted_thinking", "data": "opaque-xyz"}
