"""Contract tests for MultiAgentBackend implementations."""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions.multi_agent import AgentSpec, MultiAgentBackend
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


class MultiAgentBackendContract:
    """Contract tests every MultiAgentBackend must pass.

    Subclass provides:
      - make_backend_and_store() -> tuple of (backend, store)
    """

    @abstractmethod
    def make_backend_and_store(self) -> tuple[MultiAgentBackend, SessionStore]: ...

    async def test_blocking_spawn_returns_handle(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-1", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-1",
            mode="blocking",
        )
        assert handle.mode == "blocking"
        assert handle.child_session_id

    async def test_detached_spawn_returns_handle(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-2", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-2",
            mode="detached",
        )
        assert handle.mode == "detached"
        await backend.join(handle.child_session_id)

    async def test_join_returns_tool_result(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-3", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-3",
            mode="detached",
        )
        result = await backend.join(handle.child_session_id)
        assert isinstance(result, ToolResult)

    async def test_status_succeeded_after_join(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-4", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-4",
            mode="detached",
        )
        await backend.join(handle.child_session_id)
        s = await backend.status(handle.child_session_id)
        assert s == TaskState.SUCCEEDED

    async def test_child_session_links_to_parent(self) -> None:
        backend, store = self.make_backend_and_store()
        parent_id = "p-5"
        await store.save(
            Session(id=parent_id, tenant_id="acme", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id=parent_id,
            mode="blocking",
        )
        child = await store.load(handle.child_session_id)
        assert child is not None
        assert child.parent_session_id == parent_id
        assert child.tenant_id == "acme"
