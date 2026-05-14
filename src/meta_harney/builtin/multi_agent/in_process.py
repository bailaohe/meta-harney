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
        raise NotImplementedError("Task 8 implements blocking; Task 9 detached")

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        raise NotImplementedError("Task 9")

    async def status(self, child_session_id: str) -> TaskState:
        raise NotImplementedError("Task 9")

    async def cancel(self, child_session_id: str) -> None:
        raise NotImplementedError("Task 9")
