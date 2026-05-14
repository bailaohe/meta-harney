"""BridgePermissionResolver — forwards permission requests to the client.

Implements the runtime's ``PermissionResolver`` protocol over the bridge:
each ``resolve()`` call sends an outbound ``permission/request`` JSON-RPC
request to the client, awaits the response, and maps the client's decision
back into a ``PermissionDecision``.

Decision mapping:
- ``"allow"``        -> ``PermissionDecision(verdict="allow")``
- ``"deny"``         -> ``PermissionDecision(verdict="deny")``
- ``"allow_always"`` -> ``"allow"`` and cache the tool name so future
                        invocations of the same tool skip the round-trip
- anything else      -> ``PermissionDecision(verdict="deny")`` (secure default)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation

SendRequest = Callable[[str, dict[str, Any]], Awaitable[Any]]


class BridgePermissionResolver:
    """Round-trips tool permission decisions through the bridge client.

    Wired by ``BridgeServer``; tests pass any awaitable callable.
    """

    def __init__(self, *, send_request: SendRequest) -> None:
        self._send_request = send_request
        self._always_allow: set[str] = set()

    async def resolve(
        self, invocation: ToolInvocation, session_id: str
    ) -> PermissionDecision:
        if invocation.name in self._always_allow:
            return PermissionDecision(verdict="allow")

        response = await self._send_request(
            "permission/request",
            {
                "tool": invocation.name,
                "tool_args": invocation.args,
                "session_id": session_id,
                "call_id": invocation.invocation_id,
            },
        )

        decision = response.get("decision") if isinstance(response, dict) else None
        if decision == "allow":
            return PermissionDecision(verdict="allow")
        if decision == "allow_always":
            self._always_allow.add(invocation.name)
            return PermissionDecision(verdict="allow")
        # "deny" and any unknown / malformed shape -> secure default
        return PermissionDecision(verdict="deny")
