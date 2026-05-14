"""Tests for BridgePermissionResolver and bidirectional permission/request."""

from __future__ import annotations

from typing import Any

import pytest

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.bridge.permission import BridgePermissionResolver


def _make_invocation(name: str = "bash", **args: Any) -> ToolInvocation:
    return ToolInvocation(
        name=name,
        args=args,
        invocation_id="call-1",
        session_id="sess-1",
    )


@pytest.mark.asyncio
async def test_resolver_sends_request_and_returns_decision() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    async def fake_send_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        sent.append((method, params))
        return {"decision": "allow"}

    resolver = BridgePermissionResolver(send_request=fake_send_request)
    inv = _make_invocation(name="bash", command="ls")
    decision = await resolver.resolve(inv, session_id="sess-1")
    assert isinstance(decision, PermissionDecision)
    assert decision.verdict == "allow"
    assert len(sent) == 1
    method, params = sent[0]
    assert method == "permission/request"
    assert params["tool"] == "bash"
    assert params["session_id"] == "sess-1"
    assert params["tool_args"] == {"command": "ls"}
    assert params["call_id"] == "call-1"


@pytest.mark.asyncio
async def test_resolver_maps_deny() -> None:
    async def send(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "deny"}

    r = BridgePermissionResolver(send_request=send)
    inv = _make_invocation(name="bash")
    d = await r.resolve(inv, session_id="s")
    assert d.verdict == "deny"


@pytest.mark.asyncio
async def test_resolver_caches_allow_always_per_tool() -> None:
    call_count = 0

    async def send(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"decision": "allow_always"}

    r = BridgePermissionResolver(send_request=send)
    inv1 = ToolInvocation(name="bash", args={}, invocation_id="c1", session_id="s")
    inv2 = ToolInvocation(name="bash", args={}, invocation_id="c2", session_id="s")
    d1 = await r.resolve(inv1, session_id="s")
    d2 = await r.resolve(inv2, session_id="s")
    assert d1.verdict == "allow"
    assert d2.verdict == "allow"
    assert call_count == 1  # second call hit the cache


@pytest.mark.asyncio
async def test_resolver_unknown_decision_falls_back_to_deny() -> None:
    async def send(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "what"}

    r = BridgePermissionResolver(send_request=send)
    inv = _make_invocation(name="x")
    d = await r.resolve(inv, session_id="s")
    assert d.verdict == "deny"
