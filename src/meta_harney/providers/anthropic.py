"""AnthropicProvider — adapts the Anthropic Messages API to LLMProvider Protocol.

Uses the official `anthropic` Python SDK. Install via:
    pip install meta-harney[anthropic]

Phase 4 task 6: scaffold + constructor + api_key validation.
Tasks 7-10 implement message conversion, stream event mapping, tool calls,
and error classification.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic

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

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream one Anthropic Messages call.

        Translates SDK SSE events into ProviderStreamEvent variants:
        - content_block_delta with text_delta → ProviderTextDelta
        - content_block_delta with input_json_delta → buffered into tool args
        - content_block_stop (on tool_use) → emit ProviderToolCall
        - message_stop → emit ProviderStreamDone with usage
        """
        client = AsyncAnthropic(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        wire_messages, extracted_system = _convert_messages_to_anthropic(messages)
        final_system = system_prompt
        if extracted_system:
            final_system = (
                f"{extracted_system}\n\n{system_prompt}" if system_prompt else extracted_system
            )

        wire_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

        max_tokens = config.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "max_tokens": max_tokens,
        }
        if final_system:
            kwargs["system"] = final_system
        if wire_tools:
            kwargs["tools"] = wire_tools
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        # Per-tool-use streaming state: block_index → {"id":..., "name":..., "json_chunks":[...]}
        tool_use_buffer: dict[int, dict[str, Any]] = {}

        try:
            async with client.messages.stream(**kwargs) as stream_:
                async for event in stream_:
                    etype = getattr(event, "type", None)

                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[union-attr]
                        if getattr(block, "type", None) == "tool_use":
                            tool_use_buffer[event.index] = {  # type: ignore[union-attr]
                                "id": block.id,  # type: ignore[union-attr]
                                "name": block.name,  # type: ignore[union-attr]
                                "json_chunks": [],
                            }

                    elif etype == "content_block_delta":
                        delta = event.delta  # type: ignore[union-attr]
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta":
                            yield ProviderTextDelta(text=delta.text)  # type: ignore[union-attr]
                        elif dtype == "input_json_delta":
                            idx = event.index  # type: ignore[union-attr]
                            if idx in tool_use_buffer:
                                tool_use_buffer[idx]["json_chunks"].append(delta.partial_json)  # type: ignore[union-attr]

                    elif etype == "content_block_stop":
                        idx = event.index  # type: ignore[union-attr]
                        if idx in tool_use_buffer:
                            buf = tool_use_buffer.pop(idx)
                            raw_json = "".join(buf["json_chunks"])
                            try:
                                parsed_args = json.loads(raw_json) if raw_json else {}
                            except json.JSONDecodeError:
                                parsed_args = {}
                            yield ProviderToolCall(
                                invocation_id=buf["id"],
                                name=buf["name"],
                                args=parsed_args,
                            )

                    elif etype == "message_stop":
                        msg = event.message  # type: ignore[union-attr]
                        usage = getattr(msg, "usage", None)
                        raw_stop_reason = getattr(msg, "stop_reason", "end_turn")
                        # Map Anthropic stop reasons to our Literal; unknown → "end_turn"
                        known = {"end_turn", "tool_use", "max_tokens", "error"}
                        stop_reason = raw_stop_reason if raw_stop_reason in known else "end_turn"
                        yield ProviderStreamDone(
                            stop_reason=stop_reason,  # type: ignore[arg-type]
                            input_tokens=(getattr(usage, "input_tokens", None) if usage else None),
                            output_tokens=(
                                getattr(usage, "output_tokens", None) if usage else None
                            ),
                        )
                        return
        except APIStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and (status == 429 or 500 <= status < 600):
                raise RetryableProviderError(
                    f"anthropic transient error (status {status}): {exc}"
                ) from exc
            raise NonRetryableProviderError(
                f"anthropic API error (status {status}): {exc}"
            ) from exc
        except APIConnectionError as exc:
            raise RetryableProviderError(f"anthropic connection error: {exc}") from exc
