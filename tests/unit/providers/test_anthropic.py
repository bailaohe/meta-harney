"""Tests for AnthropicProvider — real-LLM-API adapter.

Tests stub the anthropic SDK at the client boundary so they're deterministic
and don't make network calls.
"""
from __future__ import annotations

import pytest

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.anthropic import AnthropicProvider, _convert_messages_to_anthropic


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
