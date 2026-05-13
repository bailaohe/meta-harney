"""Tests for CompactionStrategy Protocol."""

from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.compaction import CompactionStrategy


async def test_protocol_satisfied_by_duck_typing():
    class AlwaysCompact:
        async def should_compact(self, session_id, current_tokens, window_limit):
            return current_tokens > window_limit * 0.5

        async def compact(self, session_id):
            return [Message(role="system", content=[TextBlock(text="summary")])]

    strat: CompactionStrategy = AlwaysCompact()
    assert await strat.should_compact("s", 600, 1000)
    assert not await strat.should_compact("s", 400, 1000)
    msgs = await strat.compact("s")
    assert len(msgs) == 1
    assert msgs[0].content[0].text == "summary"
