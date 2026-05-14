"""InProcessMultiAgentBackend — child agents run in the same process.

Each spawn() creates a fresh Session linked to the parent, then runs
engine.run_turn with a _ChildPromptBuilder. Blocking mode awaits the
result; detached mode creates an asyncio.Task and stores it.

Task 8 implements spawn() blocking mode.
Task 9 implements spawn() detached + join + status + cancel.
"""
from __future__ import annotations

import asyncio
from typing import Literal

from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import AgentSpec, SpawnHandle
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import BaseTool, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import TokenCounter
from meta_harney.providers.base import LLMProvider


class InProcessMultiAgentBackend:
    """Multi-agent backend that runs children in the same asyncio loop."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        permission_resolver: PermissionResolver,
        session_store: SessionStore,
        trace_sink: TraceSink,
        config: RuntimeConfig,
        all_tools: dict[str, BaseTool],
        hooks: list[BaseHook],
        compaction: CompactionStrategy | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._provider = provider
        self._permission_resolver = permission_resolver
        self._session_store = session_store
        self._trace_sink = trace_sink
        self._config = config
        self._all_tools = all_tools
        self._hooks = hooks
        self._compaction = compaction
        self._token_counter = token_counter

        # Detached-mode bookkeeping
        self._tasks: dict[str, asyncio.Task[ToolResult]] = {}
        self._results: dict[str, ToolResult] = {}

    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: Literal["blocking", "detached"] = "blocking",
    ) -> SpawnHandle:
        if mode not in ("blocking", "detached"):
            raise ValueError(f"unknown spawn mode: {mode!r}")

        # Create child session linked to parent
        import uuid as _uuid
        from datetime import datetime, timezone

        from meta_harney.abstractions.session import Session

        parent = await self._session_store.load(parent_session_id)
        child_id = f"child-{_uuid.uuid4().hex[:12]}"
        child = Session(
            id=child_id,
            tenant_id=parent.tenant_id if parent else None,
            user_id=parent.user_id if parent else None,
            parent_session_id=parent_session_id,
            created_at=datetime.now(timezone.utc),
        )
        await self._session_store.save(child)

        # Filter parent's toolset to those allowed in the spec
        child_tools = {
            name: tool
            for name, tool in self._all_tools.items()
            if name in spec.allowed_tools
        }

        # Build a config that respects spec.max_iters
        child_config = self._config.model_copy(update={"max_iterations": spec.max_iters})

        # Run the child agent and capture the final assistant text as ToolResult
        if mode == "blocking":
            result = await self._run_child(
                child_id=child_id,
                initial_message=initial_message,
                instructions=spec.instructions,
                child_tools=child_tools,
                child_config=child_config,
            )
            self._results[child_id] = result
            return SpawnHandle(child_session_id=child_id, mode="blocking")

        # detached
        coro = self._run_child(
            child_id=child_id,
            initial_message=initial_message,
            instructions=spec.instructions,
            child_tools=child_tools,
            child_config=child_config,
        )
        task = asyncio.create_task(coro)
        self._tasks[child_id] = task
        return SpawnHandle(child_session_id=child_id, mode="detached")

    async def _run_child(
        self,
        *,
        child_id: str,
        initial_message: str,
        instructions: str,
        child_tools: dict[str, BaseTool],
        child_config: RuntimeConfig,
    ) -> ToolResult:
        """Run one child agent turn; return final assistant text as ToolResult."""
        from meta_harney.abstractions._types import Message, TextBlock
        from meta_harney.builtin.multi_agent.child_prompt import _ChildPromptBuilder
        from meta_harney.engine.loop import run_turn
        from meta_harney.engine.stream_events import TextDelta

        child_builder = _ChildPromptBuilder(
            instructions=instructions,
            session_store=self._session_store,
        )
        user_msg = Message(role="user", content=[TextBlock(text=initial_message)])
        assistant_text_chunks: list[str] = []

        async for ev in run_turn(
            session_id=child_id,
            user_message=user_msg,
            provider=self._provider,
            prompt_builder=child_builder,
            permission_resolver=self._permission_resolver,
            tools=child_tools,
            hooks=self._hooks,
            session_store=self._session_store,
            trace_sink=self._trace_sink,
            config=child_config,
            compaction=self._compaction,
            token_counter=self._token_counter,
        ):
            if isinstance(ev, TextDelta):
                assistant_text_chunks.append(ev.text)

        final_text = "".join(assistant_text_chunks)
        return ToolResult(success=True, output=final_text)

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        # Already-completed blocking child?
        if child_session_id in self._results:
            return self._results[child_session_id]

        task = self._tasks.get(child_session_id)
        if task is None:
            raise KeyError(f"no such child: {child_session_id!r}")

        from meta_harney.errors import ChildTimeoutError

        try:
            if timeout is None:
                result = await task
            else:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ChildTimeoutError(
                f"child {child_session_id!r} did not complete within {timeout}s"
            ) from exc
        self._results[child_session_id] = result
        return result

    async def status(self, child_session_id: str) -> TaskState:
        if child_session_id in self._results:
            return TaskState.SUCCEEDED
        task = self._tasks.get(child_session_id)
        if task is None:
            return TaskState.PENDING  # unknown child — treat as not yet started
        if task.cancelled():
            return TaskState.CANCELLED
        if task.done():
            if task.exception() is not None:
                return TaskState.FAILED
            return TaskState.SUCCEEDED
        return TaskState.RUNNING

    async def cancel(self, child_session_id: str) -> None:
        task = self._tasks.get(child_session_id)
        if task is None or task.done():
            return
        task.cancel()
        # Drain the cancellation
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
