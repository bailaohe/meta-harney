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
from typing import Any, Literal

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from meta_harney.abstractions._serialize import _serialize_tool_output
from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.errors import (
    ConfigurationError,
    NonRetryableProviderError,
    RetryableProviderError,
)
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
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
            text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
            out.append({"role": "system", "content": text})
            continue

        if msg.role == "tool":
            # Tool result: one ToolResultBlock per OpenAI tool message
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    if block.success:
                        content_str = _serialize_tool_output(block.output)
                    else:
                        content_str = _serialize_tool_output(block.error)
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.invocation_id,
                            "content": content_str,
                        }
                    )
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
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": url},
                    }
                )
            elif isinstance(block, ToolCallBlock):
                tool_calls.append(
                    {
                        "id": block.invocation_id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.args),
                        },
                    }
                )
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

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream one OpenAI Chat Completions call."""
        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        wire_messages = _convert_messages_to_openai(messages, system_prompt=system_prompt)
        wire_tools = _convert_tools_to_openai(tools)
        max_tokens = config.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if wire_tools:
            kwargs["tools"] = wire_tools
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        # tool_call_buffer[index] = {"id": str, "name": str, "args_chunks": [str, ...]}
        tool_call_buffer: dict[int, dict[str, Any]] = {}

        try:
            stream_ = await client.chat.completions.create(**kwargs)
            async for chunk in stream_:
                if getattr(chunk, "usage", None) is not None:
                    input_tokens = getattr(chunk.usage, "prompt_tokens", None)
                    output_tokens = getattr(chunk.usage, "completion_tokens", None)

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                text_delta = getattr(delta, "content", None)
                if text_delta:
                    yield ProviderTextDelta(text=text_delta)

                tc_deltas = getattr(delta, "tool_calls", None) or []
                for tc_delta in tc_deltas:
                    idx = tc_delta.index
                    if idx not in tool_call_buffer:
                        tool_call_buffer[idx] = {
                            "id": None,
                            "name": None,
                            "args_chunks": [],
                        }
                    buf = tool_call_buffer[idx]
                    if tc_delta.id is not None:
                        buf["id"] = tc_delta.id
                    fn = getattr(tc_delta, "function", None)
                    if fn is not None:
                        if fn.name is not None:
                            buf["name"] = fn.name
                        if fn.arguments:
                            buf["args_chunks"].append(fn.arguments)

                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason
        except RateLimitError as exc:
            raise RetryableProviderError(f"openai rate limit: {exc}") from exc
        except APIStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and 500 <= status < 600:
                raise RetryableProviderError(
                    f"openai transient error (status {status}): {exc}"
                ) from exc
            raise NonRetryableProviderError(f"openai API error (status {status}): {exc}") from exc
        except APIConnectionError as exc:
            raise RetryableProviderError(f"openai connection error: {exc}") from exc

        # Emit ProviderToolCall for each accumulated tool call (sorted by index)
        for idx in sorted(tool_call_buffer):
            buf = tool_call_buffer[idx]
            raw = "".join(buf["args_chunks"])
            try:
                parsed_args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed_args = {}
            yield ProviderToolCall(
                invocation_id=buf["id"] or f"openai-tc-{idx}",
                name=buf["name"] or "",
                args=parsed_args,
            )

        stop_map: dict[str, Literal["end_turn", "max_tokens", "tool_use", "error"]] = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "function_call": "tool_use",
        }
        mapped: Literal["end_turn", "max_tokens", "tool_use", "error"] = stop_map.get(
            finish_reason or "stop", "error"
        )

        yield ProviderStreamDone(
            stop_reason=mapped,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
