"""End-to-end engine tests using FakeLLMProvider."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import run_turn
from meta_harney.engine.stream_events import (
    StreamEvent,
    TextDelta,
    TurnCompleted,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound


async def _new_session(store: MemorySessionStore, session_id: str = "s1") -> Session:
    s = Session(id=session_id, created_at=datetime.now(timezone.utc))
    await store.save(s)
    return s


async def test_happy_path_text_only() -> None:
    """One user message → one LLM response, no tools."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(text="Hello!", stop_reason="end_turn"),
    ])

    builder = MinimalPromptBuilder(session_store=store)

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,
        prompt_builder=builder,
        permission_resolver=AllowAllPermissionResolver(),
        tools={},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake-model"),
    ):
        events.append(ev)

    # Last event is TurnCompleted
    assert isinstance(events[-1], TurnCompleted)
    # At least one TextDelta
    assert any(isinstance(e, TextDelta) and e.text == "Hello!" for e in events)

    # Session updated: user msg + assistant msg
    loaded = await store.load("s1")
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"
    text_block = loaded.messages[1].content[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "Hello!"
