"""Hook abstraction: BaseHook ABC + HookEvent + HookDecision.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

HookEventKind = Literal[
    "pre_tool",
    "post_tool",
    "pre_llm",
    "post_llm",
    "session_start",
    "session_end",
    "turn_complete",
]


class HookEvent(BaseModel):
    """A lifecycle event delivered to subscribed hooks."""

    kind: HookEventKind
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class HookDecision(BaseModel):
    """Hook return value: allow/deny + optional in-flight transform.

    `transform` is only applied for pre_* events; engine ignores it for
    post_* events (and emits a warning trace).
    """

    allow: bool = True
    transform: dict[str, Any] | None = None
    reason: str | None = None


class BaseHook(ABC):
    """Base class for all hooks.

    Subclasses declare `subscribed_events` and implement `handle()`.
    """

    subscribed_events: ClassVar[set[HookEventKind]]

    @abstractmethod
    async def handle(self, event: HookEvent) -> HookDecision:
        """Handle a subscribed event. Must be async."""
