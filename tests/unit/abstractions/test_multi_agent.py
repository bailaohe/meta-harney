"""Tests for AgentSpec, SpawnHandle, MultiAgentBackend Protocol."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meta_harney.abstractions.multi_agent import (
    AgentSpec,
    MultiAgentBackend,
    SpawnHandle,
)
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


def test_agent_spec_defaults():
    spec = AgentSpec(
        name="helper",
        instructions="You are helpful.",
        allowed_tools=["echo"],
    )
    assert spec.max_iters == 10


def test_spawn_handle_modes():
    h = SpawnHandle(child_session_id="child-1", mode="blocking")
    assert h.mode == "blocking"
    h2 = SpawnHandle(child_session_id="child-2", mode="detached")
    assert h2.mode == "detached"


def test_spawn_handle_invalid_mode():
    with pytest.raises(ValidationError):
        SpawnHandle(child_session_id="x", mode="async")  # type: ignore


async def test_protocol_satisfied_by_duck_typing():
    class FakeBackend:
        async def spawn(self, spec, initial_message, parent_session_id, mode="blocking"):
            return SpawnHandle(child_session_id="child", mode=mode)

        async def join(self, child_session_id, timeout=None):
            return ToolResult(success=True, output="child done")

        async def status(self, child_session_id):
            return TaskState.SUCCEEDED

        async def cancel(self, child_session_id):
            return None

    backend: MultiAgentBackend = FakeBackend()
    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    h = await backend.spawn(spec, "hello", "parent")
    assert h.child_session_id == "child"
    r = await backend.join("child")
    assert r.success
