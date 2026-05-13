"""Permission abstraction: PermissionResolver Protocol + PermissionDecision.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.4.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from meta_harney.abstractions.tool import ToolInvocation


class PermissionDecision(BaseModel):
    """Resolver verdict on a single tool invocation."""

    verdict: Literal["allow", "deny", "ask"]
    reason: str | None = None


class PermissionResolver(Protocol):
    """Decides whether a tool invocation is allowed.

    Implementations are duck-typed; no inheritance required. The framework
    ships `AllowAllPermissionResolver` and `DenyAllPermissionResolver` as
    defaults under `meta_harney.builtin.permission`.
    """

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision: ...
