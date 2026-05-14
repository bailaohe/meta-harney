"""Shared data contracts: Content blocks and Message envelope.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.1.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class _ContentBlockBase(BaseModel):
    type: str


class TextBlock(_ContentBlockBase):
    type: Literal["text"] = "text"
    text: str


class ImageBlock(_ContentBlockBase):
    type: Literal["image"] = "image"
    url: str | None = None
    data: str | None = None  # base64
    media_type: str


class ToolCallBlock(_ContentBlockBase):
    type: Literal["tool_call"] = "tool_call"
    invocation_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(_ContentBlockBase):
    type: Literal["tool_result"] = "tool_result"
    invocation_id: str
    success: bool
    output: Any = None
    error: str | None = None


class ThinkingBlock(_ContentBlockBase):
    """Anthropic extended-thinking content, fully persisted.

    Carried in assistant Message.content to round-trip back to the provider
    on subsequent turns. Required for Anthropic's thinking-continuity check
    when extended thinking + tool_use is enabled.
    """

    type: Literal["thinking"] = "thinking"
    text: str
    signature: str


class RedactedThinkingBlock(_ContentBlockBase):
    """Opaque encrypted thinking payload from Anthropic.

    `data` is treated as a black box: we never decrypt, only round-trip.
    """

    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


ContentBlock = Annotated[
    TextBlock
    | ImageBlock
    | ToolCallBlock
    | ToolResultBlock
    | ThinkingBlock
    | RedactedThinkingBlock,
    Field(discriminator="type"),
]


class Message(BaseModel):
    """A single message in a session's history.

    `role` is constrained to the LLM wire vocabulary; `author` is a free-form
    business label (e.g., "sales", "customer") that provider adapters map to
    the wire (OpenAI: `name`; Anthropic: text prefix injection).
    """

    role: Literal["user", "assistant", "system", "tool"]
    author: str | None = None
    name: str | None = None  # OpenAI passthrough
    content: list[ContentBlock]
