"""Prompt abstraction: PromptBuilder Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.5.
"""

from __future__ import annotations

from typing import Protocol

from meta_harney.abstractions._types import Message


class PromptBuilder(Protocol):
    """Builds the system prompt and context messages for a given session."""

    async def build_system_prompt(self, session_id: str) -> str: ...

    async def build_context_messages(self, session_id: str) -> list[Message]: ...
