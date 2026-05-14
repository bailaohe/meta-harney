"""OpenAIProvider — adapts the OpenAI Chat Completions API to LLMProvider Protocol.

Uses the official `openai` Python SDK. Install via:
    pip install meta-harney[openai]

Phase 5 task 1: scaffold + constructor + api_key validation.
Tasks 2-7 implement message conversion, stream event mapping, and error
classification.
"""
from __future__ import annotations

import json
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


def _convert_messages_to_openai(
    messages: list[Message],
    *,
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Convert meta_harney messages to OpenAI Chat Completions format.

    Conversion rules:
    - system_prompt (if non-empty) → prepended as {"role":"system"} message
    - role=user → {"role":"user","content":...} (string or list of content parts)
    - role=assistant text-only → {"role":"assistant","content":<str>}
    - role=assistant with tool calls →
        {"role":"assistant","content":<str|None>,"tool_calls":[...]}
    - role=tool → {"role":"tool","tool_call_id":...,"content":<str>}
    - TextBlock → {"type":"text","text":...} (inside content list)
    - ImageBlock (url) → {"type":"image_url","image_url":{"url":...}}
    - ImageBlock (data) → {"type":"image_url","image_url":{"url":"data:<media>;base64,<data>"}}
    """
    out: list[dict[str, Any]] = []
    if system_prompt:
        out.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "system":
            # In-band system message: keep verbatim text
            text = "".join(
                b.text for b in msg.content if isinstance(b, TextBlock)
            )
            out.append({"role": "system", "content": text})
            continue

        if msg.role == "tool":
            # Tool result: one ToolResultBlock per OpenAI tool message
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    content_str = (
                        block.error if not block.success else str(block.output)
                    )
                    out.append({
                        "role": "tool",
                        "tool_call_id": block.invocation_id,
                        "content": content_str or "",
                    })
            continue

        # user or assistant
        text_parts: list[str] = []
        content_parts: list[dict[str, Any]] = []  # for vision-style multi-part
        tool_calls: list[dict[str, Any]] = []
        has_non_text = False

        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
                content_parts.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageBlock):
                has_non_text = True
                if block.url is not None:
                    url = block.url
                else:
                    url = f"data:{block.media_type};base64,{block.data}"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            elif isinstance(block, ToolCallBlock):
                tool_calls.append({
                    "id": block.invocation_id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.args),
                    },
                })
            # ToolResultBlock in user/assistant message is unexpected — skip

        entry: dict[str, Any] = {"role": msg.role}

        if has_non_text:
            entry["content"] = content_parts
        elif text_parts:
            entry["content"] = "".join(text_parts)
        else:
            entry["content"] = None  # tool_calls-only assistant

        if tool_calls:
            entry["tool_calls"] = tool_calls

        out.append(entry)

    return out


def _convert_tools_to_openai(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec list to OpenAI tools array.

    Maps ToolSpec to OpenAI function definition format:
    {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


class OpenAIProvider:
    """LLMProvider implementation using the openai SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ConfigurationError("OpenAIProvider requires a non-empty api_key")
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
        """Stream a single LLM call. Filled in by Tasks 4-6."""
        raise NotImplementedError("OpenAI stream lands in Task 4")
