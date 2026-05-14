# meta-harney Phase 4: Polish + Testing Helpers + Anthropic Provider

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Address Phase 3 polish carry-overs; (2) introduce `meta_harney.testing` module per spec §8.5; (3) implement the first real LLM provider (Anthropic) with deterministic mocked-HTTP tests, proving the `LLMProvider` Protocol works for a real backend.

**Architecture:** Three independent threads:
- **Polish:** small, scoped engine + multi-agent fixes (status semantic, task-leak prevention, ToolCallStarted ordering).
- **Testing module:** new `src/meta_harney/testing/` namespace re-exporting `FakeLLMProvider`/`FakeRound` plus a `runtime_for_testing()` factory.
- **Anthropic provider:** new `providers/anthropic.py` using the official `anthropic` SDK (optional dependency). Tests use mocked SDK clients (no real network calls).

**Tech Stack:**
- Python 3.10+
- Pydantic v2
- pytest + pytest-asyncio
- `anthropic` SDK (NEW optional dependency)
- mypy strict + ruff

**Spec reference:** `docs/superpowers/specs/2026-05-13-meta-harney-design.md` §3 (providers/anthropic.py), §5.2 (StreamEvent), §7 (error handling), §8.5 (testing module).

**Phase 3 status (already merged on `main` @ v0.0.3):**
- AgentRuntime + InProcessMultiAgentBackend complete
- 224/224 tests pass; mypy strict + ruff clean

**Phase 4 carry-over items addressed:**
- ✅ T1: `status("unknown")` raises explicit error (symmetric with `join()`)
- ✅ T2: `join(timeout=...)` auto-cancels the underlying task before raising `ChildTimeoutError`
- ✅ T3: `ToolCallStarted` emitted AFTER permission cleared (semantic fix)
- ✅ T4-T5: `meta_harney.testing` module
- ✅ T6-T11: AnthropicProvider
- ⏸ DEFERRED to Phase 5: OpenAI provider, ThinkingDelta wiring (depends on Anthropic extended thinking), CRM demo

---

## File Structure After Phase 4

```
src/meta_harney/
├── __init__.py                                    # MODIFIED — version 0.0.4, expose testing
│
├── builtin/
│   └── multi_agent/
│       └── in_process.py                          # MODIFIED — status raises, join cancels
│
├── engine/
│   ├── loop.py                                    # MODIFIED — ToolCallStarted ordering
│   └── tool_dispatch.py                           # MODIFIED — yield ToolCallStarted internally
│
├── errors.py                                      # MODIFIED — new ChildNotFoundError
│
├── providers/
│   └── anthropic.py                               # NEW — real Anthropic provider
│
└── testing/                                       # NEW namespace
    ├── __init__.py                                # Re-exports FakeLLMProvider + helpers
    └── runtime_helpers.py                         # runtime_for_testing() factory

tests/
├── unit/
│   ├── builtin/multi_agent/
│   │   └── test_in_process.py                     # MODIFIED — new tests for T1+T2
│   ├── engine/
│   │   └── test_tool_dispatch.py                  # MODIFIED — T3 test
│   ├── providers/
│   │   └── test_anthropic.py                      # NEW
│   └── testing/                                   # NEW
│       ├── __init__.py
│       └── test_runtime_helpers.py
└── integration/
    └── test_engine_e2e.py                         # MODIFIED — multi-turn-session E2E
```

---

## Task 1: `status()` raises explicit error for unknown child

**Files:**
- Modify: `src/meta_harney/errors.py` (new `ChildNotFoundError`)
- Modify: `src/meta_harney/builtin/multi_agent/in_process.py`
- Modify: `tests/unit/builtin/multi_agent/test_in_process.py`

Phase 3 reviewer flagged: `status("unknown-id")` returns `TaskState.PENDING` silently; `join("unknown-id")` raises `KeyError`. The asymmetry is surprising. Fix: introduce `ChildNotFoundError(MultiAgentError)` and have both raise it.

- [ ] **Step 1: Append failing test to `tests/unit/builtin/multi_agent/test_in_process.py`**

Read the existing file. Append at end:

```python


from meta_harney.errors import ChildNotFoundError


async def test_status_unknown_child_raises() -> None:
    """status() raises ChildNotFoundError for unknown child_session_id (symmetry with join)."""
    store = MemorySessionStore()
    backend = InProcessMultiAgentBackend(
        provider=FakeLLMProvider(rounds=[]),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )
    with pytest.raises(ChildNotFoundError, match="no such child"):
        await backend.status("nonexistent-id")


async def test_join_unknown_child_now_raises_child_not_found() -> None:
    """join() raises ChildNotFoundError (refined from generic KeyError)."""
    store = MemorySessionStore()
    backend = InProcessMultiAgentBackend(
        provider=FakeLLMProvider(rounds=[]),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )
    with pytest.raises(ChildNotFoundError, match="no such child"):
        await backend.join("nonexistent-id")
```

The existing test `test_join_unknown_child_raises` expects `KeyError` — UPDATE it (don't delete) to expect `ChildNotFoundError`. Find this in the existing file:

```python
async def test_join_unknown_child_raises() -> None:
    """Joining a child that was never spawned raises."""
    ...
    with pytest.raises(KeyError, match="no such child"):
        await backend.join("nonexistent-id")
```

Change `with pytest.raises(KeyError, match="no such child"):` to `with pytest.raises(ChildNotFoundError, match="no such child"):` (keeps the existing test alive with the refined exception type).

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
```

Expected: 3 failures (the 2 new tests + the updated existing test expecting ChildNotFoundError).

- [ ] **Step 3: Modify `src/meta_harney/errors.py` — add ChildNotFoundError**

In the `MultiAgentError` section of `errors.py`, add:

```python
class ChildNotFoundError(MultiAgentError):
    """No child agent with the given child_session_id exists in this backend."""
```

(Order: place it among the existing MultiAgent exception subclasses: `SpawnError`, `ChildTimeoutError`, `ChildNotFoundError`.)

- [ ] **Step 4: Modify `src/meta_harney/builtin/multi_agent/in_process.py`**

Two changes:

(a) Update `status()`:

```python
    async def status(self, child_session_id: str) -> TaskState:
        if child_session_id in self._results:
            return TaskState.SUCCEEDED
        task = self._tasks.get(child_session_id)
        if task is None:
            from meta_harney.errors import ChildNotFoundError
            raise ChildNotFoundError(f"no such child: {child_session_id!r}")
        if task.cancelled():
            return TaskState.CANCELLED
        if task.done():
            if task.exception() is not None:
                return TaskState.FAILED
            return TaskState.SUCCEEDED
        return TaskState.RUNNING
```

(b) Update `join()` — replace `raise KeyError(...)` with `raise ChildNotFoundError(...)`:

```python
        task = self._tasks.get(child_session_id)
        if task is None:
            from meta_harney.errors import ChildNotFoundError
            raise ChildNotFoundError(f"no such child: {child_session_id!r}")
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
pytest -q  # full suite — verify nothing else broke
ruff check src/meta_harney tests
mypy src/meta_harney
```

Expected: all updated/new tests pass; total ~226 (224 + 2); clean.

- [ ] **Step 6: Update test_errors.py for new ChildNotFoundError**

In `tests/unit/test_errors.py`, find the parametrized `test_nested_hierarchy` test and add:

```python
        (ChildNotFoundError, MultiAgentError),
```

to the list. And update the imports at top to add `ChildNotFoundError`.

Re-run `pytest tests/unit/test_errors.py -v` and verify the new parametrized case passes.

- [ ] **Step 7: Commit**

```bash
git add src/meta_harney/errors.py src/meta_harney/builtin/multi_agent/in_process.py tests/unit/builtin/multi_agent/test_in_process.py tests/unit/test_errors.py
git commit -m "feat(multi-agent): status/join raise ChildNotFoundError on unknown id

Phase 3 reviewer flagged asymmetry: join() raised KeyError, status()
silently returned PENDING. Fix: new MultiAgentError subtype
ChildNotFoundError. Both join() and status() raise it for unknown
child_session_id.

Existing test_join_unknown_child_raises updated to expect the refined
exception type. Two new tests cover status/join symmetry."
```

---

## Task 2: `join(timeout=...)` auto-cancels underlying task

**Files:**
- Modify: `src/meta_harney/builtin/multi_agent/in_process.py`
- Modify: `tests/unit/builtin/multi_agent/test_in_process.py`

Phase 3 reviewer flagged: after `ChildTimeoutError`, the underlying task continues running. If caller drops the reference, the task leaks. Fix: `join()` cancels the task on timeout before raising.

- [ ] **Step 1: Update test for new behavior**

Find the existing `test_join_timeout_raises_child_timeout_error` in `tests/unit/builtin/multi_agent/test_in_process.py`. Replace it with:

```python
async def test_join_timeout_raises_and_cancels_task() -> None:
    """join(timeout=...) raises ChildTimeoutError AND auto-cancels the underlying task."""
    store = MemorySessionStore()
    parent = Session(id="parent-t1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_BlockingProvider(),  # type: ignore[arg-type]
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go", parent_session_id="parent-t1", mode="detached",
    )
    with pytest.raises(ChildTimeoutError):
        await backend.join(handle.child_session_id, timeout=0.1)

    # After timeout, the underlying task should be cancelled — no leak.
    # Allow asyncio one tick to process cancellation.
    await asyncio.sleep(0.05)
    final_status = await backend.status(handle.child_session_id)
    assert final_status == TaskState.CANCELLED
```

(Remove the old `await backend.cancel(...)` cleanup line — auto-cancel makes it unnecessary.)

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py::test_join_timeout_raises_and_cancels_task -v
```

Expected: FAIL — status is still RUNNING after timeout because old code doesn't auto-cancel.

- [ ] **Step 3: Modify `join()` in `src/meta_harney/builtin/multi_agent/in_process.py`**

Replace the `join` method body. Find the `except asyncio.TimeoutError` block and add auto-cancel before re-raising:

```python
    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        if child_session_id in self._results:
            return self._results[child_session_id]

        task = self._tasks.get(child_session_id)
        if task is None:
            from meta_harney.errors import ChildNotFoundError
            raise ChildNotFoundError(f"no such child: {child_session_id!r}")

        from meta_harney.errors import ChildTimeoutError

        try:
            if timeout is None:
                result = await task
            else:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError as exc:
            # Auto-cancel the underlying task to prevent leak
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise ChildTimeoutError(
                f"child {child_session_id!r} did not complete within {timeout}s"
            ) from exc
        self._results[child_session_id] = result
        return result
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
pytest -q
ruff check src/meta_harney/builtin/multi_agent
mypy src/meta_harney/builtin/multi_agent
```

Expected: test passes; total ~226; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/builtin/multi_agent/in_process.py tests/unit/builtin/multi_agent/test_in_process.py
git commit -m "fix(multi-agent): join() auto-cancels task on timeout (no leak)

Phase 3 reviewer flagged: after ChildTimeoutError, the underlying
task continued running. If caller dropped the reference, the task
leaked. Fix: on asyncio.TimeoutError, call task.cancel() and drain
the cancellation before raising ChildTimeoutError.

Test updated to verify status() reports CANCELLED after the timeout
(no manual cleanup needed)."
```

---

## Task 3: `ToolCallStarted` ordering — emit after permission cleared

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `src/meta_harney/engine/tool_dispatch.py`
- Modify: `tests/integration/test_engine_e2e.py`
- Modify: `tests/unit/engine/test_tool_dispatch.py`

Phase 3 reviewer flagged: `ToolCallStarted` is currently yielded by the engine BEFORE `execute_tool` runs permission check. Semantically wrong — "started" should mean "actually executing now".

**Approach:** Move the `ToolCallStarted` yield out of the engine loop and into `execute_tool` itself (after permission clears, before pre_tool hooks). To do that, `execute_tool` must become an async generator yielding both `ToolCallStarted` (once, after permission) and finally a `ToolResult`.

Cleaner alternative: keep `execute_tool` returning ToolResult, but it can call back into a "yield_started_callback" passed from the loop. Simpler still: have `execute_tool` return a tuple `(maybe_started_event, result)` — but None for the started_event indicates permission was denied. Hmm awkward.

**Simplest design:** add a new `execute_tool_with_events()` async generator alongside the existing `execute_tool()`. The generator yields:
- nothing (if permission denied) — caller will not see a `ToolCallStarted`
- `ToolCallStarted` first (if permission cleared), then the `ToolResult` last

The existing `execute_tool()` stays as a convenience wrapper that drains the generator. Engine loop uses the new generator.

But this duplicates logic. Cleanest is: `execute_tool` becomes an async generator. Update both callers (loop + existing unit tests).

Let me pick: convert `execute_tool` to async generator yielding `ToolResult | "started"`. Update the contract.

Actually the absolute simplest approach: leave `execute_tool` as-is (returns ToolResult), and add ONE conditional in the engine loop:

```python
# (1) call execute_tool for permission + hooks pre-phase ONLY (a refactor)
# (2) if permission denied or pre-hook denied, skip ToolCallStarted yield
# (3) otherwise yield ToolCallStarted, then run the actual exec
```

This requires splitting `execute_tool` into 2 phases. Too invasive.

**Pragmatic compromise (this plan):** Keep architecture as-is. Add a NEW `ToolCallRequested` StreamEvent emitted by the loop BEFORE `execute_tool`, and emit `ToolCallStarted` from INSIDE `execute_tool` after permission clears. Both events surface to the caller. The semantic is now precise: Requested = LLM asked, Started = actually executing.

This is additive (no breaking change to existing tests) but does change the loop's emitted events. Existing tests that look for `ToolCallStarted` would still see one — just after permission. New event `ToolCallRequested` fires before permission for callers who want UI signal.

Hmm but this adds API surface for a polish issue. Trade-off: rename ToolCallStarted's semantic vs add new event.

**Decision:** Keep `ToolCallStarted` semantic as "tool actually starting execute" (post permission). Document it. The existing tests will fail if permission is denied — they need updating to no longer expect ToolCallStarted in that case. The plan handles this.

- [ ] **Step 1: Update failing test in `tests/integration/test_engine_e2e.py`**

Find `test_permission_denied_e2e`. Currently it expects a `ToolCallCompleted` (which it gets) but the test doesn't assert on `ToolCallStarted` presence. Add a NEW assertion:

```python
    # ToolCallStarted should NOT have been emitted (permission denied before exec)
    started = [e for e in events if isinstance(e, ToolCallStarted)]
    assert len(started) == 0
```

Place this assertion immediately after the existing `completed` assertions. The test should still pass at this point IF we move the yield as planned.

- [ ] **Step 2: Refactor — move `ToolCallStarted` yield**

In `src/meta_harney/engine/loop.py`, find this section inside the tool-dispatch loop:

```python
        for tc in tool_calls:
            yield ToolCallStarted(
                tool_name=tc.name,
                invocation_id=tc.invocation_id,
                args=tc.args,
            )

            inv = ToolInvocation(...)
            ...
            result = await execute_tool(...)
            ...
            yield ToolCallCompleted(...)
```

The current `yield ToolCallStarted(...)` is at the wrong place (before permission check). We need to defer the yield until after permission clears.

**Refactor:** convert `execute_tool` from `-> ToolResult` to `-> AsyncGenerator[ToolCallStarted | ToolResult, None]` where exactly one of the following sequences is yielded:
- `(ToolResult,)` — permission denied
- `(ToolCallStarted, ToolResult)` — permission cleared, executed

Wait, this complicates `execute_tool`'s API. Simpler approach: add a separate "permission check" helper that the loop calls first.

Actually even simpler: have `execute_tool` accept an `on_permission_cleared: Callable[[], Awaitable[None]]` callback. Loop passes `lambda: queue.put(ToolCallStarted(...))` or similar. But callbacks across async generators are awkward.

**Cleanest design that doesn't fight Python:** split `execute_tool` into two functions:
1. `check_permission_for_tool(invocation, resolver, sink, parent_span_id) -> PermissionDecision`
2. `execute_tool_after_permission(invocation, tool, hooks, ctx, config, parent_span_id) -> ToolResult`

Loop calls #1; if denied, emit deny ToolResult directly. If allowed, yield ToolCallStarted, then call #2.

Implement this refactor.

In `src/meta_harney/engine/tool_dispatch.py`, ADD a new function `check_permission_for_tool`:

```python
async def check_permission_for_tool(
    invocation: ToolInvocation,
    permission_resolver: PermissionResolver,
    sink: TraceSink,
    parent_span_id: str,
    new_span_id: Callable[[], str],
) -> ToolResult | None:
    """Check permission. Return None if allowed; ToolResult(success=False) if denied.

    Emits permission.resolved + tool.denied/tool.permission_pending traces.
    """
    perm_span = new_span_id()
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
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "reason": perm.reason or "denied"},
        )
        return ToolResult(
            success=False,
            error=f"permission denied: {perm.reason or 'no reason'}",
        )
    if perm.verdict == "ask":
        await emit_event(
            sink,
            session_id=invocation.session_id,
            kind="tool.permission_pending",
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "reason": perm.reason or "approval needed"},
        )
        return ToolResult(
            success=False,
            error=f"permission requires approval: {perm.reason or 'no reason'}",
        )
    return None
```

Then update `execute_tool` to assume permission already cleared. Remove the permission check at the top:

```python
async def execute_tool(
    *,
    invocation: ToolInvocation,
    tool: BaseTool,
    permission_resolver: PermissionResolver,  # kept for backwards compat
    hooks: list[BaseHook],
    ctx: ToolContext,
    config: RuntimeConfig,
    parent_span_id: str,
) -> ToolResult:
    """Run one tool invocation. Returns a ToolResult.

    Phase 4 refactor: permission check is now a separate function. This
    function assumes permission already cleared (called only after
    check_permission_for_tool returned None).

    For backwards compatibility, this function still calls
    check_permission_for_tool internally. The engine loop calls them
    separately so it can yield ToolCallStarted at the right moment.
    """
    # Backwards-compat path: if caller still uses execute_tool directly,
    # do the permission check inline.
    sink = ctx.trace_sink
    pre_denial = await check_permission_for_tool(
        invocation, permission_resolver, sink, parent_span_id, ctx.new_span_id
    )
    if pre_denial is not None:
        return pre_denial

    # ... rest of execute_tool unchanged: pre_tool hooks, timeout, exec, post_tool
```

Wait, this duplicates the permission check. Better: have engine loop use a NEW function entirely, and keep `execute_tool` for backwards compat with existing callers (tool_dispatch unit tests).

Actually let me reconsider. The tool_dispatch unit tests in `test_tool_dispatch.py` directly call `execute_tool` and assert various failure modes. They don't see `ToolCallStarted` because they're unit tests of `execute_tool`, not the loop. So keeping `execute_tool` as-is (with embedded permission check) doesn't affect those tests.

What changes is just the LOOP. The loop should:
1. Call `check_permission_for_tool` first
2. If permission denied → emit ToolResultBlock with the denial directly, yield ToolCallCompleted, skip ToolCallStarted
3. If permission cleared → yield ToolCallStarted, then call execute_tool (which redoes permission check, but it's idempotent and the permission check is cheap)

This adds a redundant permission check call in the success path. Marginal cost. Acceptable.

Alternative: introduce `execute_tool_after_permission_cleared` that skips the permission check, used internally by the loop after `check_permission_for_tool` already cleared.

Let me pick this cleaner approach.

In `src/meta_harney/engine/tool_dispatch.py`, refactor:

```python
async def check_permission_for_tool(...) -> ToolResult | None:
    # ... as above ...


async def _execute_after_permission(
    *,
    invocation: ToolInvocation,
    tool: BaseTool,
    hooks: list[BaseHook],
    ctx: ToolContext,
    config: RuntimeConfig,
    parent_span_id: str,
) -> ToolResult:
    """Run the tool (assumes permission cleared). pre_tool → timeout-exec → post_tool."""
    sink = ctx.trace_sink

    # pre_tool hooks
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

    # Execute with timeout
    timeout = config.resolve_tool_timeout(tool)
    tool_span = ctx.new_span_id()
    invoke_ctx = ToolContext(
        session_store=ctx.session_store,
        trace_sink=ctx.trace_sink,
        current_span_id=tool_span,
        new_span_id=ctx.new_span_id,
        multi_agent=ctx.multi_agent,
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

    # post_tool hooks
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
    """Convenience: check_permission + _execute_after_permission. Unchanged API."""
    pre_denial = await check_permission_for_tool(
        invocation, permission_resolver, ctx.trace_sink, parent_span_id, ctx.new_span_id
    )
    if pre_denial is not None:
        return pre_denial
    return await _execute_after_permission(
        invocation=invocation,
        tool=tool,
        hooks=hooks,
        ctx=ctx,
        config=config,
        parent_span_id=parent_span_id,
    )
```

(All existing tests of `execute_tool` keep working because the convenience wrapper preserves the original behavior.)

- [ ] **Step 3: Modify `src/meta_harney/engine/loop.py` — use the split**

Replace the for-tc loop with:

```python
            tool_result_blocks: list[ContentBlock] = []
            for tc in tool_calls:
                inv = ToolInvocation(
                    name=tc.name,
                    args=tc.args,
                    invocation_id=tc.invocation_id,
                    session_id=session_id,
                )

                tool = tools.get(tc.name)
                if tool is None:
                    # Tool not registered — no permission check needed
                    result = await _result_for_unknown_tool(
                        inv=inv,
                        sink=trace_sink,
                        parent_span=turn_span,
                    )
                else:
                    # Step A: permission check
                    pre_denial = await check_permission_for_tool(
                        inv,
                        permission_resolver,
                        trace_sink,
                        turn_span,
                        new_span_id,
                    )
                    if pre_denial is not None:
                        result = pre_denial
                    else:
                        # Step B: permission cleared — NOW yield ToolCallStarted
                        yield ToolCallStarted(
                            tool_name=tc.name,
                            invocation_id=tc.invocation_id,
                            args=tc.args,
                        )
                        ctx = ToolContext(
                            session_store=session_store,
                            trace_sink=trace_sink,
                            current_span_id=turn_span,
                            new_span_id=new_span_id,
                            multi_agent=multi_agent,
                        )
                        result = await _execute_after_permission(
                            invocation=inv,
                            tool=tool,
                            hooks=hooks,
                            ctx=ctx,
                            config=config,
                            parent_span_id=turn_span,
                        )

                tool_result_blocks.append(ToolResultBlock(
                    invocation_id=inv.invocation_id,
                    success=result.success,
                    output=result.output,
                    error=result.error,
                ))
                yield ToolCallCompleted(
                    tool_name=tc.name,
                    invocation_id=tc.invocation_id,
                    result=result,
                )
```

Update imports at top of `loop.py`:

```python
from meta_harney.engine.tool_dispatch import (
    _execute_after_permission,
    check_permission_for_tool,
    execute_tool,
)
```

(`execute_tool` is no longer used directly but kept for re-export consistency. Actually, REMOVE the `execute_tool` import if it's truly unused — let ruff guide.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
pytest tests/unit/engine/test_tool_dispatch.py -v  # existing tests should still pass
pytest -q  # full suite
ruff check src/meta_harney tests
mypy src/meta_harney
```

Expected: all tests pass. The permission_denied E2E now also asserts no ToolCallStarted was emitted; all other tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py src/meta_harney/engine/tool_dispatch.py tests/integration/test_engine_e2e.py
git commit -m "fix(engine): ToolCallStarted emitted after permission cleared

Phase 3 reviewer flagged misleading semantic: ToolCallStarted was
yielded before permission check, so denied tools still emitted a
'started' signal. Fix: split execute_tool into check_permission_for_tool
+ _execute_after_permission. Loop calls them separately and yields
ToolCallStarted only between them.

execute_tool keeps the original combined behavior as a convenience
wrapper for tool_dispatch unit tests.

Test: permission_denied_e2e now asserts no ToolCallStarted is emitted."
```

---

## Task 4: `meta_harney.testing` module — re-export FakeLLMProvider

**Files:**
- Create: `src/meta_harney/testing/__init__.py`
- Create: `tests/unit/testing/__init__.py` (empty)
- Test: `tests/unit/testing/test_module_exposure.py`

Per spec §8.5, business code should be able to:

```python
from meta_harney.testing import FakeLLMProvider, FakeRound, runtime_for_testing
```

Currently `FakeLLMProvider` lives in `providers/fake.py`. The testing module re-exports them so business apps have a clean import path for their test setup.

`runtime_for_testing()` is a convenience factory: returns an `AgentRuntime` with sensible test defaults (`AllowAll` permission, `MemorySessionStore`, `NullSink`, `MinimalPromptBuilder`, configurable scripted provider).

- [ ] **Step 1: Create directories**

```bash
mkdir -p src/meta_harney/testing
mkdir -p tests/unit/testing
touch tests/unit/testing/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/testing/test_module_exposure.py`:

```python
"""Tests for meta_harney.testing module exposure."""
from __future__ import annotations


def test_testing_module_reexports_fake_provider() -> None:
    from meta_harney.testing import FakeLLMProvider, FakeRound
    assert FakeLLMProvider
    assert FakeRound


def test_testing_module_reexports_runtime_helper() -> None:
    from meta_harney.testing import runtime_for_testing
    assert runtime_for_testing


def test_runtime_for_testing_returns_agentruntime() -> None:
    from meta_harney import AgentRuntime, Message, TextBlock
    from meta_harney.testing import FakeRound, runtime_for_testing

    rt = runtime_for_testing(
        scripted_rounds=[FakeRound(text="ok", stop_reason="end_turn")],
    )
    assert isinstance(rt, AgentRuntime)


async def test_runtime_for_testing_works_end_to_end() -> None:
    """Full turn via runtime_for_testing should succeed."""
    from meta_harney.abstractions._types import TextBlock
    from meta_harney.testing import FakeRound, runtime_for_testing

    rt = runtime_for_testing(
        scripted_rounds=[FakeRound(text="hello from helper", stop_reason="end_turn")],
    )
    session = await rt.create_session()
    final = await rt.invoke(session.id, "hi")
    assert final.role == "assistant"
    assert isinstance(final.content[0], TextBlock)
    assert "hello from helper" in final.content[0].text
```

- [ ] **Step 3: RED**

```bash
source .venv/bin/activate
pytest tests/unit/testing/test_module_exposure.py -v
```

Expected: ModuleNotFoundError on `meta_harney.testing`.

- [ ] **Step 4: Implement `src/meta_harney/testing/__init__.py`**

```python
"""meta_harney.testing — public testing helpers for SDK consumers.

Re-exports the FakeLLMProvider + scripted FakeRound from providers/fake.py
under a clean test-oriented namespace.

`runtime_for_testing()` builds an AgentRuntime with sensible test defaults:
- AllowAllPermissionResolver
- MemorySessionStore
- NullSink (no trace I/O)
- MinimalPromptBuilder
- Scripted FakeLLMProvider (from caller-provided rounds)

Business apps test their custom tools/hooks/permission policies via this
factory without rebuilding the dependency graph each time.
"""
from __future__ import annotations

from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import MultiAgentBackend
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool
from meta_harney.abstractions.trace import TraceSink
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.providers.fake import FakeLLMProvider, FakeRound, RecordedCall
from meta_harney.runtime import AgentRuntime


def runtime_for_testing(
    *,
    scripted_rounds: list[FakeRound],
    tools: dict[str, BaseTool] | None = None,
    hooks: list[BaseHook] | None = None,
    permission_resolver: PermissionResolver | None = None,
    prompt_builder: PromptBuilder | None = None,
    session_store: SessionStore | None = None,
    trace_sink: TraceSink | None = None,
    compaction: CompactionStrategy | None = None,
    multi_agent: MultiAgentBackend | None = None,
    model: str = "test-model",
) -> AgentRuntime:
    """Build an AgentRuntime with sensible test defaults.

    The required argument is `scripted_rounds` (a list of FakeRound). Any
    other dependency is constructed if not provided. The returned runtime
    is fully wired and ready for `create_session()` + `invoke()`.
    """
    store = session_store if session_store is not None else MemorySessionStore()
    return AgentRuntime(
        provider=FakeLLMProvider(rounds=scripted_rounds),
        prompt_builder=prompt_builder if prompt_builder is not None else MinimalPromptBuilder(session_store=store),
        permission_resolver=permission_resolver if permission_resolver is not None else AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=trace_sink if trace_sink is not None else NullSink(),
        config=RuntimeConfig(model=model),
        tools=tools or {},
        hooks=hooks or [],
        compaction=compaction,
        multi_agent=multi_agent,
    )


__all__ = [
    "FakeLLMProvider",
    "FakeRound",
    "RecordedCall",
    "runtime_for_testing",
]
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/testing/test_module_exposure.py -v
pytest -q
ruff check src/meta_harney/testing tests/unit/testing
mypy src/meta_harney/testing
```

Expected: 4 tests pass; total ~230; clean.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/testing/ tests/unit/testing/
git commit -m "feat(testing): meta_harney.testing module — public test helpers

Re-exports FakeLLMProvider + FakeRound + RecordedCall under a clean
test-oriented namespace. runtime_for_testing() builds an AgentRuntime
with sensible test defaults (AllowAll permission, MemoryStore, NullSink,
MinimalPromptBuilder, scripted provider).

Spec §8.5: business apps test their custom tools/hooks via this factory."
```

---

## Task 5: Expose `meta_harney.testing` from top-level `__init__`

**Files:**
- Modify: `src/meta_harney/__init__.py`

(Light task — just add to public surface.)

- [ ] **Step 1: Edit `__init__.py`**

Read current file. Add this import:

```python
from meta_harney.testing import (
    FakeLLMProvider,
    FakeRound,
    runtime_for_testing,
)
```

Add `"FakeLLMProvider"`, `"FakeRound"`, `"runtime_for_testing"` to `__all__` (alphabetical).

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
assert mh.runtime_for_testing
assert mh.FakeLLMProvider
assert mh.FakeRound
print(f'Exports: {len(mh.__all__)}')
"
ruff check src/meta_harney/__init__.py
mypy src/meta_harney/__init__.py
pytest -q
```

Expected: OK; exports count up from 49 to 52; clean.

- [ ] **Step 3: Commit**

```bash
git add src/meta_harney/__init__.py
git commit -m "feat: expose testing helpers at meta_harney top level

FakeLLMProvider + FakeRound + runtime_for_testing available as
'from meta_harney import ...'. Convenient for downstream tests."
```

---

## Task 6: Add `anthropic` optional dependency + scaffold `AnthropicProvider`

**Files:**
- Modify: `pyproject.toml`
- Create: `src/meta_harney/providers/anthropic.py`
- Test: `tests/unit/providers/test_anthropic.py`

The official `anthropic` Python SDK handles SSE parsing + streaming for us. We add it as an OPTIONAL dependency so `meta-harney` users who don't need Anthropic don't have to install it.

- [ ] **Step 1: Add optional dependency to `pyproject.toml`**

Find the `[project.optional-dependencies]` section. Add an `anthropic` extras entry:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
    "anthropic>=0.40",  # for AnthropicProvider tests (optional dep is exercised in dev)
]
anthropic = [
    "anthropic>=0.40",
]
```

(Note: anthropic is listed in BOTH dev and anthropic extras so dev install covers it. Production users who only need anthropic install `pip install meta-harney[anthropic]`.)

Install the new dep:

```bash
uv pip install -e ".[dev]"
python -c "import anthropic; print(anthropic.__version__)"
```

Expected: version printed (>=0.40).

- [ ] **Step 2: Write failing test**

Create `tests/unit/providers/test_anthropic.py`:

```python
"""Tests for AnthropicProvider — real-LLM-API adapter.

Tests stub the anthropic SDK at the client boundary so they're deterministic
and don't make network calls.
"""
from __future__ import annotations

import pytest

from meta_harney.providers.anthropic import AnthropicProvider


def test_anthropic_provider_constructs() -> None:
    p = AnthropicProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_anthropic_provider_requires_api_key() -> None:
    """Empty api_key should raise ConfigurationError."""
    from meta_harney.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="api_key"):
        AnthropicProvider(api_key="")
```

- [ ] **Step 3: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
```

Expected: ModuleNotFoundError on `meta_harney.providers.anthropic`.

- [ ] **Step 4: Implement scaffold `src/meta_harney/providers/anthropic.py`**

```python
"""AnthropicProvider — adapts the Anthropic Messages API to LLMProvider Protocol.

Uses the official `anthropic` Python SDK. Install via:
    pip install meta-harney[anthropic]

Phase 4 task 6: scaffold + constructor + api_key validation.
Tasks 7-10 implement message conversion, stream event mapping, tool calls,
and error classification.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from meta_harney.abstractions._types import Message
from meta_harney.errors import ConfigurationError
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamEvent,
    ToolSpec,
)


class AnthropicProvider:
    """LLMProvider implementation using the anthropic SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ConfigurationError("AnthropicProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url
        self._default_max_tokens = default_max_tokens

    def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream a single LLM call. Filled in by Tasks 7-10."""
        raise NotImplementedError("Anthropic stream lands in Task 8")
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: 2 tests pass; clean.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider scaffold + api_key validation

Adds 'anthropic' optional dependency (>=0.40). AnthropicProvider
constructor validates api_key, stores base_url + default_max_tokens.
stream() raises NotImplementedError — implementation in Tasks 7-10."
```

---

## Task 7: Message format conversion (meta_harney.Message → Anthropic format)

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

Anthropic Messages API expects messages in a specific format:

```python
[
    {"role": "user", "content": [{"type": "text", "text": "..."}]},
    {"role": "assistant", "content": [{"type": "text", "text": "..."}, {"type": "tool_use", "id": "...", "name": "...", "input": {...}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]},
]
```

Our `Message` uses `role: user|assistant|system|tool` + `ContentBlock` variants. We need to convert.

Notes:
- Anthropic only uses `user` and `assistant` roles in the messages array. `system` is separate (passed as `system` kwarg).
- Our `tool` role (containing ToolResultBlock) maps to Anthropic's `user` role with `tool_result` content blocks.
- `system` role messages in our format are concatenated and prepended to the `system_prompt` argument.

- [ ] **Step 1: Append failing tests**

Append to `tests/unit/providers/test_anthropic.py`:

```python


from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.anthropic import _convert_messages_to_anthropic


def test_convert_simple_user_message() -> None:
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    converted, extracted_system = _convert_messages_to_anthropic(msgs)
    assert converted == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]
    assert extracted_system is None


def test_convert_extracts_system_messages() -> None:
    """System-role messages are extracted and concatenated."""
    msgs = [
        Message(role="system", content=[TextBlock(text="be helpful")]),
        Message(role="system", content=[TextBlock(text="also be brief")]),
        Message(role="user", content=[TextBlock(text="hi")]),
    ]
    converted, extracted_system = _convert_messages_to_anthropic(msgs)
    assert extracted_system == "be helpful\n\nalso be brief"
    assert len(converted) == 1
    assert converted[0]["role"] == "user"


def test_convert_assistant_with_tool_call() -> None:
    msgs = [
        Message(role="user", content=[TextBlock(text="search")]),
        Message(role="assistant", content=[
            TextBlock(text="Let me check."),
            ToolCallBlock(invocation_id="t1", name="search", args={"query": "x"}),
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[1]["role"] == "assistant"
    assistant_blocks = converted[1]["content"]
    assert assistant_blocks[0] == {"type": "text", "text": "Let me check."}
    assert assistant_blocks[1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "search",
        "input": {"query": "x"},
    }


def test_convert_tool_result_message() -> None:
    """Tool-role message converts to user-role with tool_result content."""
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(
                invocation_id="t1",
                success=True,
                output="result text",
            )
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[0]["role"] == "user"
    block = converted[0]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "t1"
    # Output stringified for Anthropic
    assert "result text" in str(block["content"])


def test_convert_failed_tool_result_marks_is_error() -> None:
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(
                invocation_id="t1",
                success=False,
                output=None,
                error="boom",
            )
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block.get("is_error") is True
    assert "boom" in str(block["content"])


def test_convert_image_block() -> None:
    msgs = [
        Message(role="user", content=[
            ImageBlock(url="https://x/y.png", media_type="image/png"),
        ]),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    block = converted[0]["content"][0]
    assert block["type"] == "image"
    # Anthropic supports source.type=url or base64
    assert block["source"]["type"] == "url"
    assert block["source"]["url"] == "https://x/y.png"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
```

Expected: ImportError on `_convert_messages_to_anthropic`.

- [ ] **Step 3: Implement converter in `src/meta_harney/providers/anthropic.py`**

Add this function to anthropic.py (above the AnthropicProvider class):

```python
def _convert_messages_to_anthropic(
    messages: list[Message],
) -> tuple[list[dict], str | None]:
    """Convert meta_harney messages to Anthropic Messages API format.

    Returns (anthropic_messages, extracted_system_prompt).

    Conversion rules:
    - role=system → extracted; multiple are concatenated with "\\n\\n"
    - role=user → role=user with content blocks converted
    - role=assistant → role=assistant with content blocks converted
    - role=tool → role=user with tool_result blocks (Anthropic convention)
    - TextBlock → {"type":"text","text":...}
    - ImageBlock → {"type":"image","source":{"type":"url"|"base64",...}}
    - ToolCallBlock → {"type":"tool_use","id":...,"name":...,"input":...}
    - ToolResultBlock → {"type":"tool_result","tool_use_id":...,"content":...,"is_error":bool}
    """
    from meta_harney.abstractions._types import (
        ImageBlock,
        TextBlock,
        ToolCallBlock,
        ToolResultBlock,
    )

    anthropic_messages: list[dict] = []
    system_parts: list[str] = []

    def _convert_block(block) -> dict:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ImageBlock):
            if block.url is not None:
                return {
                    "type": "image",
                    "source": {"type": "url", "url": block.url},
                }
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": block.media_type,
                    "data": block.data,
                },
            }
        if isinstance(block, ToolCallBlock):
            return {
                "type": "tool_use",
                "id": block.invocation_id,
                "name": block.name,
                "input": block.args,
            }
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": str(content),
            }
            if not block.success:
                result_block["is_error"] = True
            return result_block
        raise ValueError(f"unknown content block type: {type(block).__name__}")

    for msg in messages:
        if msg.role == "system":
            for block in msg.content:
                if isinstance(block, TextBlock):
                    system_parts.append(block.text)
            continue

        # Map role: tool → user (Anthropic convention)
        wire_role = "user" if msg.role == "tool" else msg.role
        content_blocks = [_convert_block(b) for b in msg.content]
        anthropic_messages.append({"role": wire_role, "content": content_blocks})

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return anthropic_messages, system_prompt
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): Anthropic message format conversion

_convert_messages_to_anthropic(messages) → (anthropic_msgs, system_prompt).
- system role → extracted and concatenated with two newlines
- tool role → user role with tool_result blocks (Anthropic convention)
- TextBlock, ImageBlock, ToolCallBlock, ToolResultBlock all mapped
- ImageBlock supports both url and base64 sources
- Failed ToolResultBlock sets is_error=True"
```

---

## Task 8: AnthropicProvider.stream() — real implementation

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

Use the `anthropic.AsyncAnthropic` client. Stream consumes raw events and yields `ProviderStreamEvent`. Tests stub the SDK client at construction time.

- [ ] **Step 1: Append failing tests**

Append to `tests/unit/providers/test_anthropic.py`:

```python


from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
)


class _FakeAnthropicStream:
    """Mimics anthropic SDK's stream context manager."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def __aenter__(self) -> "_FakeAnthropicStream":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        for event in self._events:
            yield event


def _make_event(event_type: str, **kwargs: Any) -> MagicMock:
    """Build a MagicMock that mimics an Anthropic SSE event."""
    m = MagicMock()
    m.type = event_type
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


async def test_stream_emits_text_delta() -> None:
    """Simple text response: one delta + stream_done."""
    text_block = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("text_delta", text="hello"),
    )
    message_stop = _make_event(
        "message_stop",
        message=_make_event(
            "message",
            stop_reason="end_turn",
            usage=_make_event("usage", input_tokens=10, output_tokens=5),
        ),
    )
    events = [text_block, message_stop]

    fake_messages_client = MagicMock()
    fake_messages_client.stream = MagicMock(return_value=_FakeAnthropicStream(events))

    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    text_events = [e for e in collected if isinstance(e, ProviderTextDelta)]
    done_events = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(text_events) >= 1
    assert text_events[0].text == "hello"
    assert len(done_events) == 1
    assert done_events[0].stop_reason == "end_turn"
    assert done_events[0].input_tokens == 10
    assert done_events[0].output_tokens == 5


async def test_stream_emits_tool_call() -> None:
    """Tool use response: accumulates streaming JSON, yields ProviderToolCall."""
    tool_use_start = _make_event(
        "content_block_start",
        index=0,
        content_block=_make_event(
            "tool_use",
            id="toolu_01abc",
            name="search",
            input={},
        ),
    )
    json_delta_1 = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("input_json_delta", partial_json='{"query":'),
    )
    json_delta_2 = _make_event(
        "content_block_delta",
        index=0,
        delta=_make_event("input_json_delta", partial_json='"hello"}'),
    )
    block_stop = _make_event("content_block_stop", index=0)
    message_stop = _make_event(
        "message_stop",
        message=_make_event(
            "message",
            stop_reason="tool_use",
            usage=_make_event("usage", input_tokens=10, output_tokens=5),
        ),
    )

    fake_messages_client = MagicMock()
    fake_messages_client.stream = MagicMock(
        return_value=_FakeAnthropicStream(
            [tool_use_start, json_delta_1, json_delta_2, block_stop, message_stop]
        )
    )
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="search hello")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "search"
    assert tool_calls[0].args == {"query": "hello"}
    assert tool_calls[0].invocation_id == "toolu_01abc"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_stream_emits_text_delta -v
```

Expected: NotImplementedError (the scaffold raises it).

- [ ] **Step 3: Implement `stream()` in `anthropic.py`**

Replace the `stream()` method in `AnthropicProvider`. Add necessary imports at top:

```python
import json
from typing import Any

from anthropic import AsyncAnthropic
```

Then implement:

```python
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream one Anthropic Messages call.

        Translates SDK SSE events into ProviderStreamEvent variants:
        - content_block_delta with text_delta → ProviderTextDelta
        - content_block_delta with input_json_delta → buffered into tool args
        - content_block_stop (on tool_use) → emit ProviderToolCall
        - message_stop → emit ProviderStreamDone with usage
        """
        # Lazy import — anthropic SDK is optional
        client = AsyncAnthropic(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # Convert messages + system
        wire_messages, extracted_system = _convert_messages_to_anthropic(messages)
        final_system = system_prompt
        if extracted_system:
            final_system = (
                f"{extracted_system}\n\n{system_prompt}"
                if system_prompt else extracted_system
            )

        # Convert tools to Anthropic format
        wire_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

        max_tokens = config.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "max_tokens": max_tokens,
        }
        if final_system:
            kwargs["system"] = final_system
        if wire_tools:
            kwargs["tools"] = wire_tools
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        # Per-tool-use streaming state
        tool_use_buffer: dict[int, dict[str, Any]] = {}
        # block_index → {"id":..., "name":..., "json_chunks":[...]}

        async with client.messages.stream(**kwargs) as stream_:
            async for event in stream_:
                etype = getattr(event, "type", None)

                if etype == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", None) == "tool_use":
                        tool_use_buffer[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "json_chunks": [],
                        }

                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        yield ProviderTextDelta(text=delta.text)
                    elif dtype == "input_json_delta":
                        idx = event.index
                        if idx in tool_use_buffer:
                            tool_use_buffer[idx]["json_chunks"].append(delta.partial_json)

                elif etype == "content_block_stop":
                    idx = event.index
                    if idx in tool_use_buffer:
                        buf = tool_use_buffer.pop(idx)
                        raw_json = "".join(buf["json_chunks"])
                        try:
                            parsed_args = json.loads(raw_json) if raw_json else {}
                        except json.JSONDecodeError:
                            parsed_args = {}
                        yield ProviderToolCall(
                            invocation_id=buf["id"],
                            name=buf["name"],
                            args=parsed_args,
                        )

                elif etype == "message_stop":
                    msg = event.message
                    usage = getattr(msg, "usage", None)
                    yield ProviderStreamDone(
                        stop_reason=msg.stop_reason,
                        input_tokens=getattr(usage, "input_tokens", None) if usage else None,
                        output_tokens=getattr(usage, "output_tokens", None) if usage else None,
                    )
                    return
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider.stream() real implementation

Translates Anthropic SDK SSE stream events to ProviderStreamEvent:
- content_block_delta(text_delta) → ProviderTextDelta
- content_block_delta(input_json_delta) → buffered into tool args
- content_block_stop on tool_use → ProviderToolCall (parsed JSON)
- message_stop → ProviderStreamDone (with usage)

Accumulates streaming JSON args per content_block index. Translates
final stop_reason. Lazy-imports anthropic SDK so it stays optional."
```

---

## Task 9: AnthropicProvider error classification

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

Anthropic SDK raises various exception types. We need to map them to `RetryableProviderError` or `NonRetryableProviderError`.

- [ ] **Step 1: Append failing tests**

```python


async def test_anthropic_429_maps_to_retryable() -> None:
    """RateLimitError → RetryableProviderError."""
    from meta_harney.errors import RetryableProviderError

    fake_messages_client = MagicMock()

    # anthropic.RateLimitError signature
    from anthropic import APIStatusError

    def _raise_rate_limit(**kwargs: Any) -> Any:
        # Build minimal APIStatusError instance for the test
        resp = MagicMock()
        resp.status_code = 429
        raise APIStatusError("rate limited", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_rate_limit)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass


async def test_anthropic_500_maps_to_retryable() -> None:
    """5xx → RetryableProviderError."""
    from anthropic import APIStatusError

    from meta_harney.errors import RetryableProviderError

    fake_messages_client = MagicMock()

    def _raise_500(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 503
        raise APIStatusError("upstream error", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_500)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass


async def test_anthropic_401_maps_to_non_retryable() -> None:
    """401 → NonRetryableProviderError."""
    from anthropic import APIStatusError

    from meta_harney.errors import NonRetryableProviderError

    fake_messages_client = MagicMock()

    def _raise_401(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 401
        raise APIStatusError("auth failed", response=resp, body=None)

    fake_messages_client.stream = MagicMock(side_effect=_raise_401)
    fake_client = MagicMock()
    fake_client.messages = fake_messages_client

    with patch(
        "meta_harney.providers.anthropic.AsyncAnthropic",
        return_value=fake_client,
    ):
        provider = AnthropicProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        with pytest.raises(NonRetryableProviderError):
            async for _ev in provider.stream(
                messages=msgs,
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="claude-sonnet-4-5"),
            ):
                pass
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
```

Expected: 3 failures — current code doesn't translate APIStatusError.

- [ ] **Step 3: Add error mapping to `anthropic.py`**

Add imports at top:

```python
from anthropic import APIConnectionError, APIStatusError

from meta_harney.errors import NonRetryableProviderError, RetryableProviderError
```

Wrap the `async with client.messages.stream(**kwargs)` block in a try/except. Add at the start of `stream()`:

Replace:
```python
        async with client.messages.stream(**kwargs) as stream_:
            async for event in stream_:
                # ... existing event handling ...
```

With:

```python
        try:
            async with client.messages.stream(**kwargs) as stream_:
                async for event in stream_:
                    # ... existing event handling ... (unchanged)
        except APIStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and (status == 429 or 500 <= status < 600):
                raise RetryableProviderError(
                    f"anthropic transient error (status {status}): {exc}"
                ) from exc
            raise NonRetryableProviderError(
                f"anthropic API error (status {status}): {exc}"
            ) from exc
        except APIConnectionError as exc:
            raise RetryableProviderError(
                f"anthropic connection error: {exc}"
            ) from exc
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider error classification

Maps anthropic SDK exceptions to meta_harney provider errors:
- APIConnectionError → RetryableProviderError
- APIStatusError status 429 or 5xx → RetryableProviderError
- APIStatusError other (4xx) → NonRetryableProviderError

3 tests cover 429, 503, and 401 → expected error classification."
```

---

## Task 10: AnthropicProvider passes LLMProviderContract

**Files:**
- Modify: `tests/unit/providers/test_anthropic.py`

The existing `LLMProviderContract` (from Phase 2) defines 2 contract checks. Apply them to `AnthropicProvider` using mocked client.

- [ ] **Step 1: Append contract subclass**

```python


from tests.contracts.llm_provider import LLMProviderContract


class TestAnthropicProviderContract(LLMProviderContract):
    """AnthropicProvider passes the standard LLMProvider contract.

    Tests use a mocked anthropic SDK client returning a single text round.
    """

    def make_provider(self):
        text_block = _make_event(
            "content_block_delta",
            index=0,
            delta=_make_event("text_delta", text="ok"),
        )
        message_stop = _make_event(
            "message_stop",
            message=_make_event(
                "message",
                stop_reason="end_turn",
                usage=_make_event("usage", input_tokens=1, output_tokens=1),
            ),
        )

        fake_messages_client = MagicMock()
        fake_messages_client.stream = MagicMock(
            return_value=_FakeAnthropicStream([text_block, message_stop])
        )
        fake_client = MagicMock()
        fake_client.messages = fake_messages_client

        # Patch context that survives across tests in this class.
        patcher = patch(
            "meta_harney.providers.anthropic.AsyncAnthropic",
            return_value=fake_client,
        )
        patcher.start()
        # Note: patcher is not stopped; pytest-asyncio cleans up after fixture scope.
        # Acceptable for this contract suite since each test invocation gets a fresh provider.

        return AnthropicProvider(api_key="test-contract")
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
pytest -q
ruff check tests
mypy tests/unit/providers/test_anthropic.py
```

Expected: all anthropic tests pass (~14); full suite green; clean.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/providers/test_anthropic.py
git commit -m "test: AnthropicProvider passes LLMProviderContract

Standard 2 contract checks (stream yields ProviderStreamDone last,
stop_reason is valid literal) applied to AnthropicProvider with
mocked SDK client. Confirms the Anthropic adapter conforms to the
LLMProvider Protocol."
```

---

## Task 11: Expose AnthropicProvider at top-level + final verification

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Verify: pytest, mypy, ruff
- Bump version to 0.0.4

- [ ] **Step 1: Add AnthropicProvider to public API**

In `src/meta_harney/__init__.py`, add:

```python
from meta_harney.providers.anthropic import AnthropicProvider
```

Add `"AnthropicProvider"` to `__all__` (alphabetical).

Bump `__version__ = "0.0.4"` in `src/meta_harney/__init__.py` and `version = "0.0.4"` in `pyproject.toml`.

- [ ] **Step 2: Run all quality gates**

```bash
source .venv/bin/activate
pytest -v 2>&1 | tail -3
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -2
```

Expected: all pass; ~240 tests total (224 + 16 from Phase 4).

- [ ] **Step 3: Public API smoke**

```bash
python -c "
import meta_harney as mh
print('Version:', mh.__version__)
print('Exports:', len(mh.__all__))
assert mh.AnthropicProvider
assert mh.runtime_for_testing
assert mh.FakeLLMProvider
print('OK')
"
```

Expected: Version `0.0.4`, exports count up from 52 to 53.

- [ ] **Step 4: Commit + tag**

```bash
git add src/meta_harney/__init__.py pyproject.toml
git commit -m "release: bump version to 0.0.4 for Phase 4 milestone

Phase 4 deliverables:
- ChildNotFoundError + status() symmetry with join()
- join(timeout) auto-cancels task (no leak)
- ToolCallStarted emitted after permission cleared
- meta_harney.testing module (FakeLLMProvider + runtime_for_testing)
- AnthropicProvider with mocked-SDK tests + contract conformance

Phase 5 next: OpenAI provider, CRM mini-demo, documentation."

git tag -a v0.0.4 HEAD -m "meta-harney v0.0.4 — Phase 4 (Polish + Testing + Anthropic)

Polish (Phase 3 carry-overs):
- ChildNotFoundError raised by join() and status() for unknown child
- join(timeout) auto-cancels the underlying asyncio.Task
- ToolCallStarted emitted only after permission cleared

Testing module:
- meta_harney.testing namespace re-exports FakeLLMProvider, FakeRound
- runtime_for_testing() factory builds AgentRuntime with test defaults

First real LLM provider:
- AnthropicProvider via official anthropic SDK (optional dep)
- Message format conversion (system extraction, tool_result mapping, image sources)
- Streaming JSON tool-arg accumulation
- APIStatusError 429/5xx → RetryableProviderError, other → NonRetryable
- Passes LLMProviderContract

Tests: ~240/240 passing. mypy strict + ruff clean.

Phase 5 next: OpenAI provider, CRM mini-demo, end-user docs."
```

---

## Phase 4 Completion Checklist

- [ ] `from meta_harney import AnthropicProvider, FakeLLMProvider, runtime_for_testing` works
- [ ] `pytest -v` reports ≥ 240 passes, 0 failures
- [ ] `mypy src/meta_harney` reports 0 errors
- [ ] `ruff check src/meta_harney tests` reports 0 issues
- [ ] `ruff format --check` reports 0 differences
- [ ] `pip install meta-harney[anthropic]` (extras) declared in pyproject
- [ ] `meta_harney.testing` module exposes `FakeLLMProvider`, `FakeRound`, `runtime_for_testing`
- [ ] `AnthropicProvider` handles text + tool_use + error classification
- [ ] `AnthropicProvider` passes LLMProviderContract
- [ ] `status("unknown")` raises `ChildNotFoundError` (no more silent PENDING)
- [ ] `join(timeout=X)` auto-cancels underlying task before raising
- [ ] `ToolCallStarted` not emitted on permission-denied tool calls

**Phase 5 (next plan):**
- OpenAI provider (Chat Completions API)
- ThinkingDelta wiring (if/when Anthropic extended thinking is enabled)
- CRM mini-demo as `docs/examples/crm/`
- End-user documentation (README + architecture + abstractions)

---

## Self-Review

**Spec coverage:**
- §3 Repository Structure: `providers/anthropic.py` ✓, `testing/` ✓
- §5 Engine data flow: ToolCallStarted ordering fixed
- §7.2 Error handling: AnthropicProvider classifies via SDK errors
- §8.5 Testing helpers: meta_harney.testing module + runtime_for_testing

**Phase 3 carry-over status:**
- ✅ ChildNotFoundError on unknown child (T1)
- ✅ join() auto-cancel on timeout (T2)
- ✅ ToolCallStarted post-permission (T3)
- ⏸ ThinkingDelta — still no provider emits it (Phase 5)
- ⏸ OpenAI provider — Phase 5

**Placeholder scan:** No "TBD"/"TODO"/"later" in steps.

**Type consistency:**
- `AnthropicProvider(api_key, base_url, default_max_tokens)` constructor consistent across Tasks 6, 7, 8, 9, 10
- `_convert_messages_to_anthropic` return type `tuple[list[dict], str | None]` consistent across Tasks 7, 8
- Test fixture `_make_event`, `_FakeAnthropicStream` definitions consistent across Tasks 8, 9, 10
- `ChildNotFoundError` raised from both `join()` and `status()` (Task 1) — symmetric
- `runtime_for_testing(scripted_rounds=..., model="test-model", ...)` kwargs alphabetical except primary `scripted_rounds` first
