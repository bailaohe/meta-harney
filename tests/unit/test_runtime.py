"""Tests for AgentRuntime — top-level SDK entry point."""
from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.stream_events import StreamEvent, TextDelta, TurnCompleted
from meta_harney.providers.fake import FakeLLMProvider, FakeRound
from meta_harney.runtime import AgentRuntime


def _runtime(store: MemorySessionStore | None = None) -> AgentRuntime:
    s = store or MemorySessionStore()
    return AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="ok", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=s),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=s,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )


async def test_create_session_returns_unique_session() -> None:
    rt = _runtime()
    s1 = await rt.create_session()
    s2 = await rt.create_session()
    assert s1.id != s2.id
    # Both persisted
    assert await rt._session_store.load(s1.id) is not None
    assert await rt._session_store.load(s2.id) is not None


async def test_create_session_with_explicit_id() -> None:
    rt = _runtime()
    s = await rt.create_session(session_id="my-explicit-id")
    assert s.id == "my-explicit-id"


async def test_create_session_with_tenant_user_attrs() -> None:
    rt = _runtime()
    s = await rt.create_session(
        tenant_id="acme",
        user_id="u-1",
        attributes={"customer_id": "C-001"},
        metadata={"source": "api"},
    )
    assert s.tenant_id == "acme"
    assert s.user_id == "u-1"
    assert s.attributes["customer_id"] == "C-001"
    assert s.metadata["source"] == "api"


async def test_create_session_duplicate_id_raises() -> None:
    """Explicit session_id that already exists raises (don't silently clobber)."""
    import pytest

    from meta_harney.errors import SessionConflictError

    rt = _runtime()
    await rt.create_session(session_id="dup")
    with pytest.raises(SessionConflictError):
        await rt.create_session(session_id="dup")


async def test_stream_yields_events() -> None:
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="hello from stream", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    session = await rt.create_session()

    events: list[StreamEvent] = []
    async for ev in rt.stream(session.id, "hi"):
        events.append(ev)

    assert any(isinstance(e, TurnCompleted) for e in events)
    assert any(isinstance(e, TextDelta) and "hello from stream" in e.text for e in events)


async def test_stream_accepts_string_or_message() -> None:
    """stream() accepts a plain string (creates user TextBlock) OR a full Message."""
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="a", stop_reason="end_turn"),
            FakeRound(text="b", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    s = await rt.create_session()

    # String input
    async for _ in rt.stream(s.id, "first"):
        pass
    # Message input
    msg = Message(role="user", content=[TextBlock(text="second")])
    async for _ in rt.stream(s.id, msg):
        pass

    loaded = await store.load(s.id)
    assert loaded is not None
    user_msgs = [m for m in loaded.messages if m.role == "user"]
    user_texts = [
        m.content[0].text
        for m in user_msgs
        if isinstance(m.content[0], TextBlock)
    ]
    assert user_texts == ["first", "second"]


async def test_invoke_returns_final_assistant_message() -> None:
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="The answer is 42.", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    session = await rt.create_session()
    result = await rt.invoke(session.id, "what is the answer?")

    assert result.role == "assistant"
    assert isinstance(result.content[0], TextBlock)
    assert "answer is 42" in result.content[0].text


async def test_invoke_returns_empty_assistant_on_no_text() -> None:
    """When LLM emits no text, return assistant message with empty content."""
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    s = await rt.create_session()
    result = await rt.invoke(s.id, "hi")
    assert result.role == "assistant"
    # No TextBlocks expected
    assert all(not isinstance(b, TextBlock) for b in result.content)
