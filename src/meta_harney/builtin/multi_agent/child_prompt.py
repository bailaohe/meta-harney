"""Child agent prompt builder.

Wraps a SessionStore + overrides system prompt with AgentSpec.instructions.
Used by InProcessMultiAgentBackend to give each child agent a different
system prompt than the parent.
"""
from __future__ import annotations

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.session import SessionStore


class _ChildPromptBuilder:
    """PromptBuilder for child agents — instructions override system prompt."""

    def __init__(
        self,
        instructions: str,
        session_store: SessionStore,
    ) -> None:
        self._instructions = instructions
        self._session_store = session_store

    async def build_system_prompt(self, session_id: str) -> str:
        return self._instructions

    async def build_context_messages(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None:
            return []
        return list(s.messages)
