"""Tool dispatch helper.

Wraps a single ToolInvocation execution with:
  1. Permission check
  2. Pre-tool hooks (with possible args transform via HookDecision.transform)
  3. Timeout-bounded tool execution
  4. Post-tool hooks
  5. Trace events at each step

Returns a ToolResult — never raises (except HookHaltError, which propagates).
"""

from __future__ import annotations

import asyncio
import time

from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.hook_dispatch import dispatch_hooks
from meta_harney.engine.tracing import emit_event


async def execute_tool(
    *,
    invocation: ToolInvocation,
    tool: BaseTool,
    permission_resolver: PermissionResolver,
    hooks: list[BaseHook],
    ctx: ToolContext,
    config: RuntimeConfig,
    parent_span_id: str,
) -> ToolResult:
    """Run one tool invocation. Returns a ToolResult.

    All errors (permission deny, hook deny, exception, timeout) are
    converted to ToolResult(success=False, error=...). Only HookHaltError
    propagates (per spec §7 rule 3).
    """
    sink = ctx.trace_sink

    # 1. Permission check
    perm_span = ctx.new_span_id()
    perm = await permission_resolver.resolve(invocation, invocation.session_id)
    await emit_event(
        sink,
        session_id=invocation.session_id,
        kind="permission.resolved",
        span_id=perm_span,
        parent_span_id=parent_span_id,
        payload={"verdict": perm.verdict, "reason": perm.reason, "tool": invocation.name},
    )
    if perm.verdict == "deny":
        await emit_event(
            sink,
            session_id=invocation.session_id,
            kind="tool.denied",
            span_id=ctx.new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "reason": perm.reason or "denied"},
        )
        return ToolResult(success=False, error=f"permission denied: {perm.reason or 'no reason'}")
    if perm.verdict == "ask":
        # No human-approval mechanism in Phase 2 → safe-default to deny.
        # Future phases may introduce a HumanApprovalHook that flips ask → allow.
        await emit_event(
            sink,
            session_id=invocation.session_id,
            kind="tool.permission_pending",
            span_id=ctx.new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "reason": perm.reason or "approval needed"},
        )
        return ToolResult(
            success=False,
            error=f"permission requires approval: {perm.reason or 'no reason'}",
        )

    # 2. pre_tool hooks
    pre_event = HookEvent(
        kind="pre_tool",
        session_id=invocation.session_id,
        payload={"tool_name": invocation.name, "args": invocation.args},
    )
    pre_decision = await dispatch_hooks(hooks, pre_event, sink, parent_span_id)
    if not pre_decision.allow:
        return ToolResult(success=False, error=f"hook denied: {pre_decision.reason or 'no reason'}")

    # Apply pre-hook arg transform
    if pre_decision.transform is not None and "args" in pre_decision.transform:
        invocation = invocation.model_copy(update={"args": pre_decision.transform["args"]})

    # 3. Execute with timeout
    timeout = config.resolve_tool_timeout(tool)
    tool_span = ctx.new_span_id()
    invoke_ctx = ToolContext(
        session_store=ctx.session_store,
        trace_sink=ctx.trace_sink,
        current_span_id=tool_span,
        new_span_id=ctx.new_span_id,
    )
    await emit_event(
        sink,
        session_id=invocation.session_id,
        kind="tool.invoked",
        span_id=tool_span,
        parent_span_id=parent_span_id,
        payload={
            "tool_name": invocation.name,
            "args": invocation.args,
            "timeout_s": timeout,
        },
    )

    start = time.monotonic()
    try:
        if timeout is None:
            result = await tool.execute(invocation, invoke_ctx)
        else:
            result = await asyncio.wait_for(tool.execute(invocation, invoke_ctx), timeout=timeout)
    except asyncio.TimeoutError:
        duration_ms = (time.monotonic() - start) * 1000.0
        await emit_event(
            sink,
            session_id=invocation.session_id,
            kind="tool.timed_out",
            span_id=ctx.new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "timeout_s": timeout},
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=False,
            error=f"tool {invocation.name!r} timed out after {timeout}s",
        )
    except Exception as exc:
        duration_ms = (time.monotonic() - start) * 1000.0
        await emit_event(
            sink,
            session_id=invocation.session_id,
            kind="error.raised",
            span_id=ctx.new_span_id(),
            parent_span_id=parent_span_id,
            payload={
                "source": "tool",
                "tool_name": invocation.name,
                "exc_type": type(exc).__name__,
                "message": str(exc),
            },
            duration_ms=duration_ms,
        )
        return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")

    duration_ms = (time.monotonic() - start) * 1000.0
    await emit_event(
        sink,
        session_id=invocation.session_id,
        kind="tool.completed",
        span_id=ctx.new_span_id(),
        parent_span_id=parent_span_id,
        payload={"tool_name": invocation.name, "success": result.success},
        duration_ms=duration_ms,
    )

    # 4. post_tool hooks
    post_event = HookEvent(
        kind="post_tool",
        session_id=invocation.session_id,
        payload={
            "tool_name": invocation.name,
            "args": invocation.args,
            "result": result.model_dump(),
        },
    )
    await dispatch_hooks(hooks, post_event, sink, parent_span_id)

    return result
