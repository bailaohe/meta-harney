"""Tests for AgentRuntime — top-level SDK entry point."""
from __future__ import annotations

from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
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
