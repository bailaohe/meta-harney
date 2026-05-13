"""AllowAllPermissionResolver — the framework default.

WARNING: This resolver allows EVERY tool invocation. Business apps SHOULD
replace it with a policy-aware implementation before going to production.
"""

from __future__ import annotations

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation


class AllowAllPermissionResolver:
    """Allows every tool invocation unconditionally."""

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision:
        return PermissionDecision(verdict="allow")
