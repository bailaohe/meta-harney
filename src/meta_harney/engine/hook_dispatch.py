"""Hook event dispatch for the engine.

Filters subscribed hooks, dispatches in order, merges decisions:
- First deny short-circuits (returns immediately)
- HookHaltError propagates to caller (terminates run_turn)
- Other exceptions are logged to trace and execution continues (fail-open)
- `transform` is only honored on pre_* events; ignored on post_* events
"""
from __future__ import annotations

from typing import Any

from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.tracing import emit_event, new_span_id
from meta_harney.errors import HookHaltError


async def dispatch_hooks(
    hooks: list[BaseHook],
    event: HookEvent,
    sink: TraceSink,
    current_span_id: str,
) -> HookDecision:
    """Run every hook subscribed to `event.kind`. Return merged decision.

    - allow=True default when no hook fires
    - First allow=False short-circuits
    - HookHaltError propagates
    - Other exceptions caught and logged (fail-open)
    - `transform` honored only for pre_* events
    """
    merged_transform: dict[str, Any] | None = None
    is_pre = event.kind.startswith("pre_")

    for hook in hooks:
        if event.kind not in hook.subscribed_events:
            continue

        hook_span = new_span_id()
        hook_name = type(hook).__name__

        try:
            decision = await hook.handle(event)
        except HookHaltError:
            # Explicit business signal — propagate.
            raise
        except Exception as exc:
            await emit_event(
                sink,
                session_id=event.session_id,
                kind="error.raised",
                span_id=hook_span,
                parent_span_id=current_span_id,
                payload={
                    "source": "hook",
                    "hook_name": hook_name,
                    "event_kind": event.kind,
                    "exc_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            continue  # fail-open: skip this hook, try next

        await emit_event(
            sink,
            session_id=event.session_id,
            kind="hook.fired",
            span_id=hook_span,
            parent_span_id=current_span_id,
            payload={
                "hook_name": hook_name,
                "event_kind": event.kind,
                "decision_allow": decision.allow,
                "decision_reason": decision.reason,
            },
        )

        # Deny short-circuits
        if not decision.allow:
            return decision

        # Merge transforms (only on pre_*)
        if is_pre and decision.transform is not None:
            if merged_transform is None:
                merged_transform = dict(decision.transform)
            else:
                merged_transform.update(decision.transform)
        elif decision.transform is not None and not is_pre:
            await emit_event(
                sink,
                session_id=event.session_id,
                kind="hook.fired",
                span_id=new_span_id(),
                parent_span_id=current_span_id,
                payload={
                    "warning": "transform_ignored_on_post_event",
                    "hook_name": hook_name,
                    "event_kind": event.kind,
                },
            )

    return HookDecision(allow=True, transform=merged_transform)
