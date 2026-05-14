"""Tests for InProcessMultiAgentBackend (Phase 3)."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.multi_agent.child_prompt import _ChildPromptBuilder
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.providers.fake import FakeLLMProvider


async def test_child_prompt_builder_returns_instructions() -> None:
    """_ChildPromptBuilder overrides system prompt with AgentSpec.instructions."""
    store = MemorySessionStore()
    builder = _ChildPromptBuilder(
        instructions="You are a billing specialist.",
        session_store=store,
    )
    sp = await builder.build_system_prompt("any-session-id")
    assert sp == "You are a billing specialist."


async def test_child_prompt_builder_returns_session_messages() -> None:
    """_ChildPromptBuilder loads context from the session store like Minimal."""
    store = MemorySessionStore()
    s = Session(
        id="s1",
        created_at=datetime.now(timezone.utc),
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    await store.save(s)

    builder = _ChildPromptBuilder(
        instructions="be helpful",
        session_store=store,
    )
    msgs = await builder.build_context_messages("s1")
    assert len(msgs) == 1
    assert isinstance(msgs[0].content[0], TextBlock)


async def test_child_prompt_builder_empty_for_missing_session() -> None:
    store = MemorySessionStore()
    builder = _ChildPromptBuilder(
        instructions="x",
        session_store=store,
    )
    msgs = await builder.build_context_messages("nonexistent")
    assert msgs == []


def test_in_process_backend_constructs() -> None:
    """Scaffold: constructor accepts all service deps."""
    store = MemorySessionStore()
    backend = InProcessMultiAgentBackend(
        provider=FakeLLMProvider(rounds=[]),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )
    # Just verify the object exists with the expected interface
    assert hasattr(backend, "spawn")
    assert hasattr(backend, "join")
    assert hasattr(backend, "status")
    assert hasattr(backend, "cancel")
