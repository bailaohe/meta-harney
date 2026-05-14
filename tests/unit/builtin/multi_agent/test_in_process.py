"""Tests for InProcessMultiAgentBackend (Phase 3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import BaseModel

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.multi_agent import AgentSpec
from meta_harney.abstractions.session import Session
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.multi_agent.child_prompt import _ChildPromptBuilder
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.errors import ChildTimeoutError
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ToolSpec,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound
from tests.contracts.multi_agent_backend import MultiAgentBackendContract


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


async def test_spawn_blocking_returns_handle_with_result() -> None:
    """Blocking spawn awaits the child to completion and returns the handle."""
    store = MemorySessionStore()
    # Pre-create parent session
    parent = Session(id="parent-1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="child output text", stop_reason="end_turn"),
        ]
    )

    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    spec = AgentSpec(
        name="helper",
        instructions="You are a helpful child agent.",
        allowed_tools=[],
    )
    handle = await backend.spawn(
        spec=spec,
        initial_message="please help",
        parent_session_id="parent-1",
        mode="blocking",
    )

    assert handle.mode == "blocking"
    assert handle.child_session_id  # non-empty

    # Child session was created with parent linkage
    child = await store.load(handle.child_session_id)
    assert child is not None
    assert child.parent_session_id == "parent-1"
    # Child has user msg + assistant msg
    assert len(child.messages) == 2


async def test_spawn_blocking_filters_tools_by_allowed_list() -> None:
    """Children only see tools listed in spec.allowed_tools."""

    class _DummyInput(BaseModel):
        pass

    class _AvailTool(BaseTool):
        name: ClassVar[str] = "avail"
        description: ClassVar[str] = "available to child"
        input_schema: ClassVar[type[BaseModel]] = _DummyInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output="ok")

    class _ForbiddenTool(BaseTool):
        name: ClassVar[str] = "forbidden"
        description: ClassVar[str] = "not allowed for child"
        input_schema: ClassVar[type[BaseModel]] = _DummyInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output="should not run")

    store = MemorySessionStore()
    parent = Session(id="parent-2", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="ok", stop_reason="end_turn")])

    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={"avail": _AvailTool(), "forbidden": _ForbiddenTool()},
        hooks=[],
    )

    spec = AgentSpec(
        name="helper",
        instructions="be helpful",
        allowed_tools=["avail"],  # forbidden excluded
    )
    await backend.spawn(
        spec=spec,
        initial_message="hi",
        parent_session_id="parent-2",
        mode="blocking",
    )
    # Verify by asserting the recorded call only exposed the "avail" tool.
    assert len(provider.calls) == 1
    tool_names = [t.name for t in provider.calls[0].tools]
    assert tool_names == ["avail"]


async def test_spawn_unknown_mode_raises() -> None:
    """Invalid mode arg raises ValueError."""
    store = MemorySessionStore()
    parent = Session(id="parent-3", created_at=datetime.now(timezone.utc))
    await store.save(parent)
    backend = InProcessMultiAgentBackend(
        provider=FakeLLMProvider(rounds=[]),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )
    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    with pytest.raises(ValueError, match="mode"):
        await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="parent-3",
            mode="bogus",  # type: ignore[arg-type]
        )


async def test_spawn_detached_returns_handle_immediately() -> None:
    """Detached spawn returns SpawnHandle without waiting for child."""
    store = MemorySessionStore()
    parent = Session(id="parent-d1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="result", stop_reason="end_turn")])
    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    handle = await backend.spawn(
        spec=spec,
        initial_message="go",
        parent_session_id="parent-d1",
        mode="detached",
    )
    assert handle.mode == "detached"

    # Join to await completion
    result = await backend.join(handle.child_session_id)
    assert result.success
    assert "result" in str(result.output)


async def test_status_for_completed_child() -> None:
    store = MemorySessionStore()
    parent = Session(id="parent-s1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="done", stop_reason="end_turn")])
    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-s1",
        mode="detached",
    )
    # Await completion
    await backend.join(handle.child_session_id)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.SUCCEEDED


class _SlowProvider:
    """Sleeps before emitting one text round."""

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        await asyncio.sleep(0.5)
        yield ProviderTextDelta(text="slow")
        yield ProviderStreamDone(stop_reason="end_turn")


async def test_status_for_running_child() -> None:
    """While the child is still running, status is RUNNING."""
    store = MemorySessionStore()
    parent = Session(id="parent-r1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_SlowProvider(),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-r1",
        mode="detached",
    )
    # Status before join (race-safe: provider sleeps 500ms)
    await asyncio.sleep(0.05)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.RUNNING

    # Then await
    result = await backend.join(handle.child_session_id)
    assert result.success


class _BlockingProvider:
    """Sleeps indefinitely — used to test cancellation."""

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        await asyncio.sleep(10.0)
        yield  # type: ignore[misc]  # unreachable but needed to make this an async generator


async def test_cancel_detached_child() -> None:
    """cancel() interrupts a running detached child task."""
    store = MemorySessionStore()
    parent = Session(id="parent-c1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_BlockingProvider(),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-c1",
        mode="detached",
    )
    await asyncio.sleep(0.05)
    await backend.cancel(handle.child_session_id)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.CANCELLED


async def test_join_unknown_child_raises() -> None:
    """Joining a child that was never spawned raises."""
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
    with pytest.raises(KeyError, match="no such child"):
        await backend.join("nonexistent-id")


async def test_join_timeout_raises_child_timeout_error() -> None:
    """join(timeout=...) raises ChildTimeoutError if exceeded."""
    store = MemorySessionStore()
    parent = Session(id="parent-t1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_BlockingProvider(),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-t1",
        mode="detached",
    )
    with pytest.raises(ChildTimeoutError):
        await backend.join(handle.child_session_id, timeout=0.1)

    # Cleanup the still-running task
    await backend.cancel(handle.child_session_id)


class TestInProcessMultiAgentBackendContract(MultiAgentBackendContract):
    """Inherits all standard MultiAgentBackend contract tests."""

    def make_backend_and_store(self) -> tuple[InProcessMultiAgentBackend, MemorySessionStore]:
        store = MemorySessionStore()
        backend = InProcessMultiAgentBackend(
            provider=FakeLLMProvider(
                rounds=[
                    FakeRound(text="contract test result", stop_reason="end_turn"),
                    FakeRound(text="contract test result", stop_reason="end_turn"),
                    FakeRound(text="contract test result", stop_reason="end_turn"),
                    FakeRound(text="contract test result", stop_reason="end_turn"),
                    FakeRound(text="contract test result", stop_reason="end_turn"),
                ]
            ),
            permission_resolver=AllowAllPermissionResolver(),
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(model="fake"),
            all_tools={},
            hooks=[],
        )
        return backend, store
