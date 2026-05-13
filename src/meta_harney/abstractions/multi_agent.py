"""MultiAgent abstraction: AgentSpec + SpawnHandle + MultiAgentBackend Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.9.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


class AgentSpec(BaseModel):
    """Definition of a child agent to spawn."""

    name: str
    instructions: str  # the child's system prompt
    allowed_tools: list[str]
    max_iters: int = 10


class SpawnHandle(BaseModel):
    """Returned by spawn() — identifies the child session."""

    child_session_id: str
    mode: Literal["blocking", "detached"]


class MultiAgentBackend(Protocol):
    """Coordinates spawning, joining, status-checking and cancelling child agents.

    Concrete implementations (in-process, subprocess, remote RPC) plug in here.
    The Phase 1 plan only defines the Protocol; implementations land in Phase 3.
    """

    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: Literal["blocking", "detached"] = "blocking",
    ) -> SpawnHandle: ...

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult: ...

    async def status(self, child_session_id: str) -> TaskState: ...

    async def cancel(self, child_session_id: str) -> None: ...
