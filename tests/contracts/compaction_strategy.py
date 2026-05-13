"""Contract tests for CompactionStrategy implementations."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.session import Session, SessionStore


class CompactionStrategyContract:
    """Contract tests every CompactionStrategy must pass."""

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    @abstractmethod
    def make_strategy(self, store: SessionStore) -> CompactionStrategy: ...

    async def test_should_compact_returns_bool(self) -> None:
        strat = self.make_strategy(self.make_store())
        v = await strat.should_compact("s", current_tokens=100, window_limit=1000)
        assert isinstance(v, bool)

    async def test_compact_returns_list_of_messages(self) -> None:
        store = self.make_store()
        s = Session(
            id="s1",
            created_at=datetime.now(timezone.utc),
            messages=[Message(role="user", content=[TextBlock(text="x")])],
        )
        await store.save(s)
        strat = self.make_strategy(store)
        new = await strat.compact("s1")
        assert isinstance(new, list)
        assert all(isinstance(m, Message) for m in new)

    async def test_compact_missing_session_returns_empty(self) -> None:
        strat = self.make_strategy(self.make_store())
        new = await strat.compact("nonexistent")
        assert new == []
