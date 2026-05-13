"""DenyAllPermissionResolver — secure-by-default option.

Useful in tests and as a starting point: deny everything, then allow
specific tools via custom resolver logic.
"""

from __future__ import annotations

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation


class DenyAllPermissionResolver:
    """Denies every tool invocation."""

    def __init__(self, reason: str = "default deny"):
        self._reason = reason

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision:
        return PermissionDecision(verdict="deny", reason=self._reason)
