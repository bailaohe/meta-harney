"""Tool abstraction: BaseTool ABC + ToolInvocation/ToolResult/ToolContext.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from meta_harney.abstractions.session import SessionStore
    from meta_harney.abstractions.trace import TraceSink


class ToolInvocation(BaseModel):
    """A single tool call request from the engine."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    invocation_id: str
    session_id: str  # tools load Session on demand via ctx.session_store


class ToolResult(BaseModel):
    """A single tool call result."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ToolContext:
    """Runtime services exposed to tools at execute() time.

    Business tools may subclass to inject additional services (e.g., DB session).
    The engine constructs ToolContext per invocation.
    """

    session_store: SessionStore
    trace_sink: TraceSink
    current_span_id: str
    new_span_id: Callable[[], str]


class BaseTool(ABC):
    """Base class for all tools.

    Subclasses declare `name`, `description`, `input_schema`, and optionally
    `default_timeout`, then implement `execute()`.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    default_timeout: ClassVar[float | None] = None

    @abstractmethod
    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        """Execute the tool with the given invocation. Must be async."""
