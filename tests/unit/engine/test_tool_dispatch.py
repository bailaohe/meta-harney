"""Tests for tool dispatch helper."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from pydantic import BaseModel

from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.tool_dispatch import execute_tool
from meta_harney.engine.tracing import new_span_id


class _EchoInput(BaseModel):
    text: str = ""


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes."
    input_schema = _EchoInput
    default_timeout = 5.0

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output={"echoed": inv.args.get("text", "")})


class _RaiseTool(BaseTool):
    name = "raise"
    description = "Always raises."
    input_schema = _EchoInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        raise ValueError("boom")


class _SlowTool(BaseTool):
    name = "slow"
    description = "Sleeps too long."
    input_schema = _EchoInput
    default_timeout = 0.01  # 10ms — easy to exceed

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(1.0)
        return ToolResult(success=True, output="never")


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id=new_span_id(),
        new_span_id=new_span_id,
    )


async def test_execute_tool_happy_path() -> None:
    ctx = _make_ctx()
    inv = ToolInvocation(name="echo", args={"text": "hi"}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert result.success
    assert result.output == {"echoed": "hi"}


async def test_execute_tool_permission_denied() -> None:
    ctx = _make_ctx()
    inv = ToolInvocation(name="echo", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=DenyAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "deny" in (result.error or "").lower()


async def test_execute_tool_exception_becomes_failure() -> None:
    ctx = _make_ctx()
    inv = ToolInvocation(name="raise", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_RaiseTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "boom" in (result.error or "")


async def test_execute_tool_timeout() -> None:
    ctx = _make_ctx()
    inv = ToolInvocation(name="slow", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_SlowTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "timed out" in (result.error or "").lower()


async def test_execute_tool_pre_hook_can_transform_args() -> None:
    class _OverrideArgs(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(transform={"args": {"text": "OVERRIDE"}})

    ctx = _make_ctx()
    inv = ToolInvocation(
        name="echo", args={"text": "original"}, invocation_id="i1", session_id="s1"
    )
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[_OverrideArgs()],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert result.output == {"echoed": "OVERRIDE"}


async def test_execute_tool_pre_hook_deny() -> None:
    class _Block(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(allow=False, reason="hook-blocked")

    ctx = _make_ctx()
    inv = ToolInvocation(name="echo", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[_Block()],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "hook-blocked" in (result.error or "")


async def test_execute_tool_permission_ask_is_treated_as_deny() -> None:
    """Phase 2 has no human-approval — verdict='ask' is safe-defaulted to deny."""
    from meta_harney.abstractions.permission import PermissionDecision

    class _AskResolver:
        async def resolve(self, invocation: ToolInvocation, session_id: str) -> PermissionDecision:
            return PermissionDecision(verdict="ask", reason="needs manager approval")

    ctx = _make_ctx()
    inv = ToolInvocation(name="echo", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=_AskResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "approval" in (result.error or "").lower()
    assert "needs manager approval" in (result.error or "")
