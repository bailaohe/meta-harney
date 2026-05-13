"""MinimalPromptBuilder — domain-agnostic default.

System prompt is a single configurable string; context messages are
the session's full message history. No coding-context assumptions.
"""

from __future__ import annotations

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.session import SessionStore

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class MinimalPromptBuilder:
    """Minimal, domain-neutral PromptBuilder."""

    def __init__(
        self,
        session_store: SessionStore,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._session_store = session_store
        self._system_prompt = system_prompt

    async def build_system_prompt(self, session_id: str) -> str:
        return self._system_prompt

    async def build_context_messages(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None:
            return []
        return list(s.messages)
