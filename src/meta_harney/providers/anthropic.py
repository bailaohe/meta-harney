"""AnthropicProvider — adapts the Anthropic Messages API to LLMProvider Protocol.

Uses the official `anthropic` Python SDK. Install via:
    pip install meta-harney[anthropic]

Phase 4 task 6: scaffold + constructor + api_key validation.
Tasks 7-10 implement message conversion, stream event mapping, tool calls,
and error classification.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.errors import ConfigurationError
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamEvent,
    ToolSpec,
)


def _convert_messages_to_anthropic(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], str | None]:
    """Convert meta_harney messages to Anthropic Messages API format.

    Returns (anthropic_messages, extracted_system_prompt).

    Conversion rules:
    - role=system → extracted; multiple are concatenated with "\\n\\n"
    - role=user → role=user with content blocks converted
    - role=assistant → role=assistant with content blocks converted
    - role=tool → role=user with tool_result blocks (Anthropic convention)
    - TextBlock → {"type":"text","text":...}
    - ImageBlock → {"type":"image","source":{"type":"url"|"base64",...}}
    - ToolCallBlock → {"type":"tool_use","id":...,"name":...,"input":...}
    - ToolResultBlock → {"type":"tool_result","tool_use_id":...,"content":...,"is_error":bool}
    """
    anthropic_messages: list[dict[str, Any]] = []
    system_parts: list[str] = []

    def _convert_block(block: object) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ImageBlock):
            if block.url is not None:
                return {
                    "type": "image",
                    "source": {"type": "url", "url": block.url},
                }
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": block.media_type,
                    "data": block.data,
                },
            }
        if isinstance(block, ToolCallBlock):
            return {
                "type": "tool_use",
                "id": block.invocation_id,
                "name": block.name,
                "input": block.args,
            }
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": str(content),
            }
            if not block.success:
                result_block["is_error"] = True
            return result_block
        raise ValueError(f"unknown content block type: {type(block).__name__}")

    for msg in messages:
        if msg.role == "system":
            for block in msg.content:
                if isinstance(block, TextBlock):
                    system_parts.append(block.text)
            continue

        # Map role: tool → user (Anthropic convention)
        wire_role = "user" if msg.role == "tool" else msg.role
        content_blocks = [_convert_block(b) for b in msg.content]
        anthropic_messages.append({"role": wire_role, "content": content_blocks})

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return anthropic_messages, system_prompt


class AnthropicProvider:
    """LLMProvider implementation using the anthropic SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ConfigurationError("AnthropicProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url
        self._default_max_tokens = default_max_tokens

    def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream a single LLM call. Filled in by Tasks 7-10."""
        raise NotImplementedError("Anthropic stream lands in Task 8")
