"""Contract tests for PromptBuilder implementations."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore


class PromptBuilderContract:
    """Contract tests every PromptBuilder must pass.

    Subclass provides:
      - make_builder(store) -> PromptBuilder
      - make_store() -> SessionStore
    """

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    @abstractmethod
    def make_builder(self, store: SessionStore) -> PromptBuilder: ...

    async def test_system_prompt_returns_string(self) -> None:
        builder = self.make_builder(self.make_store())
        sp = await builder.build_system_prompt("any-session-id")
        assert isinstance(sp, str)
        assert sp  # non-empty

    async def test_context_messages_empty_for_missing_session(self) -> None:
        builder = self.make_builder(self.make_store())
        msgs = await builder.build_context_messages("nonexistent")
        assert msgs == []

    async def test_context_messages_for_known_session(self) -> None:
        store = self.make_store()
        s = Session(
            id="s1",
            created_at=datetime.now(timezone.utc),
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
        )
        await store.save(s)
        builder = self.make_builder(store)
        msgs = await builder.build_context_messages("s1")
        assert isinstance(msgs, list)
        assert all(isinstance(m, Message) for m in msgs)
