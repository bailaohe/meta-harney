"""Tests for OpenAIProvider — Chat Completions adapter."""
from __future__ import annotations

import pytest

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.openai import OpenAIProvider, _convert_messages_to_openai


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
