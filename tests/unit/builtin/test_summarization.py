from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.compaction.summarization import SummarizationCompactor
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.compaction_strategy import CompactionStrategyContract


async def _fake_summarize(messages):
    return f"Summary of {len(messages)} messages."


class TestSummarizationCompactor(CompactionStrategyContract):
    def make_store(self):
        return MemorySessionStore()

    def make_strategy(self, store):
        return SummarizationCompactor(
            session_store=store,
            summarize_fn=_fake_summarize,
            keep_recent=10,
        )


# Strategy-specific tests:


def _msg(role, text):
    return Message(role=role, content=[TextBlock(text=text)])


async def test_should_compact_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(session_store=store, summarize_fn=_fake_summarize)
    assert await c.should_compact("s", current_tokens=8001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=7999, window_limit=10000)


async def test_should_compact_custom_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        trigger_ratio=0.5,
    )
    assert await c.should_compact("s", current_tokens=5001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=4999, window_limit=10000)


async def test_compact_preserves_recent_and_system():
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS")] + [_msg("user", f"u-{i}") for i in range(20)]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        keep_recent=5,
    )
    new = await c.compact("s1")
    assert new[0].role == "system"
    b0 = new[0].content[0]
    assert isinstance(b0, TextBlock)
    assert "SYS" in b0.text
    assert new[1].role == "system"
    b1 = new[1].content[0]
    assert isinstance(b1, TextBlock)
    assert "Summary" in b1.text
    assert len(new) == 1 + 1 + 5
    blast = new[-1].content[0]
    assert isinstance(blast, TextBlock)
    assert blast.text == "u-19"


async def test_compact_short_history_unchanged():
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS"), _msg("user", "hello")]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        keep_recent=10,
    )
    new = await c.compact("s1")
    assert len(new) == 2
