# meta-harney Phase 3: AgentRuntime + MultiAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the Phase 2 `run_turn` engine in a top-level `AgentRuntime` class that exposes a clean SDK API (`create_session`, `invoke`, `stream`), and implement `InProcessMultiAgentBackend` so tools can spawn child agents that share the same engine. Also resolves three Phase 2 carry-over items (config passthrough, retry wiring, ToolContext extension for multi-agent).

**Architecture:** AgentRuntime is a thin facade — it holds all the service dependencies (provider, hooks, store, sink, etc.) and orchestrates calls to `run_turn` while threading `multi_agent` through `ToolContext`. InProcessMultiAgentBackend reuses `run_turn` for child agents with a `_ChildPromptBuilder` that overrides the system prompt with `AgentSpec.instructions`. No new abstractions — just composition.

**Tech Stack:**
- Python 3.10+
- Pydantic v2
- asyncio (Task, Lock)
- pytest + pytest-asyncio (testing)
- mypy strict + ruff (quality gates)

**Spec reference:** `docs/superpowers/specs/2026-05-13-meta-harney-design.md` §3 (runtime.py), §4.9 (MultiAgentBackend), §6.1 (Session lifecycle)

**Phase 2 status (already merged on `main` @ v0.0.2):**
- Engine + Provider layer complete
- `run_turn` orchestrator with full agent loop
- 184/184 tests pass; mypy strict + ruff clean

**Phase 3 carry-over items addressed:**
- ✅ T1: RuntimeConfig.max_tokens/temperature/retry_config + ProviderCallConfig passthrough
- ✅ T2: retry_with_backoff wired around provider.stream call
- ✅ T3: ToolContext gains optional `multi_agent` field (enabler for T11)
- ⏸ DEFERRED to Phase 4: ThinkingDelta wiring (needs Anthropic provider that emits thinking)
- ⏸ DEFERRED to Phase 4: ToolCallStarted ordering decision (semantic polish, not blocking)

---

## File Structure After Phase 3

```
src/meta_harney/
├── __init__.py                                    # MODIFIED — re-export AgentRuntime, MultiAgent
├── runtime.py                                     # NEW — AgentRuntime facade
│
├── abstractions/
│   └── tool.py                                    # MODIFIED — ToolContext + multi_agent
│
├── engine/
│   ├── config.py                                  # MODIFIED — + max_tokens, temperature, retry_config
│   └── loop.py                                    # MODIFIED — retry wrap + multi_agent passthrough
│
└── builtin/
    └── multi_agent/                               # NEW
        ├── __init__.py
        ├── in_process.py                          # InProcessMultiAgentBackend
        └── child_prompt.py                        # _ChildPromptBuilder wrapper

tests/
├── unit/
│   ├── test_runtime.py                            # NEW
│   ├── engine/
│   │   └── test_config.py                         # MODIFIED — new field tests
│   └── builtin/
│       └── multi_agent/                           # NEW
│           ├── __init__.py
│           └── test_in_process.py
├── contracts/
│   └── multi_agent_backend.py                     # NEW
└── integration/
    └── test_engine_e2e.py                         # MODIFIED — + AgentRuntime + multi-agent E2E
```

---

## Task 1: RuntimeConfig — add max_tokens, temperature, retry_config + ProviderCallConfig passthrough

**Files:**
- Modify: `src/meta_harney/engine/config.py`
- Modify: `src/meta_harney/engine/loop.py` (one line for ProviderCallConfig construction)
- Test: `tests/unit/engine/test_config.py` (add cases)

- [ ] **Step 1: Append failing tests to `tests/unit/engine/test_config.py`**

Read the existing file first, then append:

```python


from meta_harney.engine.retry import RetryConfig


def test_runtime_config_new_fields_defaults() -> None:
    c = RuntimeConfig(model="x")
    assert c.max_tokens is None
    assert c.temperature is None
    assert c.retry == RetryConfig()  # default retry config


def test_runtime_config_custom_provider_params() -> None:
    c = RuntimeConfig(
        model="x",
        max_tokens=4096,
        temperature=0.7,
    )
    assert c.max_tokens == 4096
    assert c.temperature == 0.7


def test_runtime_config_custom_retry() -> None:
    c = RuntimeConfig(
        model="x",
        retry=RetryConfig(max_attempts=5, initial_delay_s=0.5),
    )
    assert c.retry.max_attempts == 5
    assert c.retry.initial_delay_s == 0.5


def test_runtime_config_to_provider_call_config() -> None:
    """Helper produces a ProviderCallConfig with all relevant fields."""
    from meta_harney.providers.base import ProviderCallConfig

    c = RuntimeConfig(model="x", max_tokens=1024, temperature=0.5)
    pc = c.to_provider_call_config()
    assert isinstance(pc, ProviderCallConfig)
    assert pc.model == "x"
    assert pc.max_tokens == 1024
    assert pc.temperature == 0.5
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_config.py -v
```

Expected: 4 new failures.

- [ ] **Step 3: Modify `src/meta_harney/engine/config.py`**

Replace the file with this complete updated version:

```python
"""Engine runtime configuration: timeouts, retry, compaction trigger, provider params.

`tool_to_spec` converts a BaseTool subclass into a ToolSpec for the LLM
provider — derived from the tool's name, description, and Pydantic
input_schema.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import BaseTool
from meta_harney.engine.retry import RetryConfig
from meta_harney.providers.base import ProviderCallConfig, ToolSpec


class RuntimeConfig(BaseModel):
    """Engine runtime parameters (one-shot or per-runtime)."""

    model: str

    # Provider sampling parameters — passed through to ProviderCallConfig
    max_tokens: int | None = None
    temperature: float | None = None

    # Retry policy for transient provider errors
    retry: RetryConfig = Field(default_factory=RetryConfig)

    # Per-tool timeout resolution: overrides → tool.default_timeout → global → None
    tool_timeout_overrides: dict[str, float] = Field(default_factory=dict)
    global_default_timeout: float | None = 300.0

    # Loop bounds
    max_iterations: int = 10

    # Compaction
    context_window_tokens: int = 100_000
    compaction_trigger_tokens: int | None = None  # None ⇒ no compaction

    def resolve_tool_timeout(self, tool: BaseTool) -> float | None:
        """Resolution order per spec §7.5."""
        if tool.name in self.tool_timeout_overrides:
            return self.tool_timeout_overrides[tool.name]
        if tool.default_timeout is not None:
            return tool.default_timeout
        return self.global_default_timeout

    def to_provider_call_config(self) -> ProviderCallConfig:
        """Build a ProviderCallConfig snapshot for one LLM call."""
        return ProviderCallConfig(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )


def tool_to_spec(tool: BaseTool) -> ToolSpec:
    """Convert a BaseTool into a ToolSpec for LLM provider exposure."""
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema.model_json_schema(),
    )
```

- [ ] **Step 4: Modify `src/meta_harney/engine/loop.py` — use new helper**

In `loop.py`, find the line constructing `ProviderCallConfig` inside the `while not stop` loop (currently `config=ProviderCallConfig(model=config.model)`) and replace it with `config=config.to_provider_call_config()`.

The exact change: locate this block (it appears once):

```python
        async for ev in provider.stream(
            messages=list(session.messages),
            system_prompt=system_prompt,
            tools=tool_specs,
            config=ProviderCallConfig(model=config.model),
        ):
```

And replace `config=ProviderCallConfig(model=config.model),` with `config=config.to_provider_call_config(),`.

After the edit, also remove the now-unused `ProviderCallConfig` import in loop.py (ruff will flag it). The other `ProviderCallConfig`-using line is gone.

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_config.py -v
pytest -q  # full suite
ruff check src/meta_harney tests
mypy src/meta_harney
```

Expected: new 4 tests pass; existing 184 also pass (no regression); ruff/mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/engine/config.py src/meta_harney/engine/loop.py tests/unit/engine/test_config.py
git commit -m "feat(engine): RuntimeConfig provider param + retry passthrough

RuntimeConfig gains: max_tokens, temperature, retry (RetryConfig).
to_provider_call_config() helper builds ProviderCallConfig per call.
loop.py uses the helper instead of ad-hoc construction. Removes
unused ProviderCallConfig import.

Phase 2 carry-over item #3 addressed (config plumbing)."
```

---

## Task 2: Wire retry_with_backoff into loop's provider.stream call

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py` (add retry test)

The current loop calls `provider.stream(...)` directly. If the provider raises `RetryableProviderError`, the exception propagates. We need to wrap with `retry_with_backoff` so transient errors get retried per `config.retry`.

**Design challenge:** `provider.stream()` returns an `AsyncGenerator`. We can't simply `retry_with_backoff(lambda: provider.stream(...))` because `retry_with_backoff` calls and awaits the function, but a generator is iterated. We need to retry the ENTIRE stream consumption as a unit (since partial consumption can't be safely resumed).

Solution: collect the events in a helper that runs the stream to completion, returns a list. The helper is the unit of retry.

- [ ] **Step 1: Append failing test to `tests/integration/test_engine_e2e.py`**

Read the file, then append:

```python


from collections.abc import AsyncGenerator
from meta_harney.engine.retry import RetryConfig as _RetryConfig
from meta_harney.errors import (
    NonRetryableProviderError,
    RetryableProviderError,
)
from meta_harney.providers.base import ProviderStreamEvent as _PSE
from meta_harney.providers.base import ToolSpec as _TS


class _FlakyProvider:
    """Raises RetryableProviderError N times, then succeeds with one text round."""

    def __init__(self, fail_count: int, succeed_text: str = "ok eventually") -> None:
        self.fail_count = fail_count
        self.attempts = 0
        self.succeed_text = succeed_text

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[_TS],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[_PSE, None]:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RetryableProviderError(f"transient #{self.attempts}")
        yield ProviderTextDelta(text=self.succeed_text)
        yield ProviderStreamDone(stop_reason="end_turn")


async def test_retry_recovers_from_transient_failure() -> None:
    """RetryableProviderError raised by provider.stream is retried per config.retry."""
    from meta_harney.providers.base import ProviderStreamDone, ProviderTextDelta

    store = MemorySessionStore()
    await _new_session(store)

    provider = _FlakyProvider(fail_count=2, succeed_text="success on attempt 3")

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,  # type: ignore[arg-type]
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        tools={},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(
            model="x",
            retry=_RetryConfig(max_attempts=3, initial_delay_s=0.001),
        ),
    ):
        events.append(ev)

    # Provider was called 3 times (2 failures + 1 success)
    assert provider.attempts == 3

    # Turn completed; assistant message captured success text
    text_events = [e for e in events if isinstance(e, TextDelta)]
    assert any("success on attempt 3" in e.text for e in text_events)


async def test_retry_gives_up_after_max_attempts() -> None:
    """After config.retry.max_attempts retries, RetryableProviderError propagates."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = _FlakyProvider(fail_count=99)  # always fails

    with pytest.raises(RetryableProviderError):
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=provider,  # type: ignore[arg-type]
            prompt_builder=MinimalPromptBuilder(session_store=store),
            permission_resolver=AllowAllPermissionResolver(),
            tools={},
            hooks=[],
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(
                model="x",
                retry=_RetryConfig(max_attempts=2, initial_delay_s=0.001),
            ),
        ):
            pass

    assert provider.attempts == 2


async def test_non_retryable_propagates_immediately() -> None:
    """NonRetryableProviderError is NOT retried; raises on first attempt."""
    class _AuthFailProvider:
        attempts = 0
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[_TS],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[_PSE, None]:
            self.attempts += 1
            raise NonRetryableProviderError("auth failed")
            yield  # type: ignore[unreachable]

    store = MemorySessionStore()
    await _new_session(store)
    provider = _AuthFailProvider()

    with pytest.raises(NonRetryableProviderError):
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=provider,  # type: ignore[arg-type]
            prompt_builder=MinimalPromptBuilder(session_store=store),
            permission_resolver=AllowAllPermissionResolver(),
            tools={},
            hooks=[],
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(
                model="x",
                retry=_RetryConfig(max_attempts=5, initial_delay_s=0.001),
            ),
        ):
            pass

    assert provider.attempts == 1
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_retry_recovers_from_transient_failure -v
```

Expected: FAIL — without retry wrapping, provider exception propagates and run_turn doesn't retry.

- [ ] **Step 3: Modify `src/meta_harney/engine/loop.py` — wrap provider.stream in retry**

Replace the entire body of the `async for ev in provider.stream(...)` loop with a retry-wrapped version. The new approach: define a local helper that consumes the stream into a list, then use `retry_with_backoff` around the helper.

The change touches two areas:
1. Add `from meta_harney.engine.retry import retry_with_backoff` import
2. Replace the inline stream loop with a `_collect_stream` helper call

Here is the new file content for `src/meta_harney/engine/loop.py`. Replace the entire file:

```python
"""Engine main loop: run_turn() orchestrator."""
from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from meta_harney.abstractions._types import (
    ContentBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
from meta_harney.engine.hook_dispatch import dispatch_hooks
from meta_harney.engine.retry import retry_with_backoff
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.engine.tool_dispatch import execute_tool
from meta_harney.engine.tracing import emit_event, new_span_id
from meta_harney.errors import SessionNotFoundError
from meta_harney.providers.base import (
    LLMProvider,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
)


TokenCounter = Callable[[list[Message]], int]


def _default_token_counter(messages: list[Message]) -> int:
    """Heuristic: 1 token per 4 characters of text content."""
    total = 0
    for m in messages:
        for block in m.content:
            if isinstance(block, TextBlock):
                total += max(1, len(block.text) // 4)
            else:
                total += 10  # rough fixed cost for non-text blocks
    return total


async def _collect_provider_stream(
    provider: LLMProvider,
    messages: list[Message],
    system_prompt: str,
    tool_specs: list,  # type: list[ToolSpec], avoid forward ref
    call_config,  # ProviderCallConfig
) -> list[ProviderStreamEvent]:
    """Run provider.stream() to completion, return event list.

    This wraps a full stream consumption as a unit so retry_with_backoff
    can re-run the whole call if a RetryableProviderError occurs.
    Partial consumption cannot be safely resumed.
    """
    events: list[ProviderStreamEvent] = []
    async for ev in provider.stream(
        messages=messages,
        system_prompt=system_prompt,
        tools=tool_specs,
        config=call_config,
    ):
        events.append(ev)
    return events


async def run_turn(
    *,
    session_id: str,
    user_message: Message,
    provider: LLMProvider,
    prompt_builder: PromptBuilder,
    permission_resolver: PermissionResolver,
    tools: dict[str, BaseTool],
    hooks: list[BaseHook],
    session_store: SessionStore,
    trace_sink: TraceSink,
    config: RuntimeConfig,
    compaction: CompactionStrategy | None = None,
    token_counter: TokenCounter | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    turn_span = new_span_id()
    counter = token_counter or _default_token_counter

    session = await session_store.load(session_id)
    if session is None:
        raise SessionNotFoundError(f"session {session_id!r} not found")

    session.messages.append(user_message)

    saved = False
    iteration = 0
    try:
        await emit_event(
            trace_sink,
            session_id=session_id,
            kind="turn.started",
            span_id=turn_span,
            parent_span_id=None,
            payload={"user_message_role": user_message.role},
        )

        await dispatch_hooks(
            hooks,
            HookEvent(
                kind="session_start",
                session_id=session_id,
                payload={"user_message_role": user_message.role},
            ),
            trace_sink,
            turn_span,
        )

        tool_specs = [tool_to_spec(t) for t in tools.values()]
        stop = False

        while not stop and iteration < config.max_iterations:
            system_prompt = await prompt_builder.build_system_prompt(session_id)
            await emit_event(
                trace_sink,
                session_id=session_id,
                kind="prompt.built",
                span_id=new_span_id(),
                parent_span_id=turn_span,
                payload={"n_messages": len(session.messages), "iteration": iteration},
            )

            await dispatch_hooks(
                hooks,
                HookEvent(
                    kind="pre_llm",
                    session_id=session_id,
                    payload={"iteration": iteration, "n_messages": len(session.messages)},
                ),
                trace_sink,
                turn_span,
            )

            llm_span = new_span_id()
            await emit_event(
                trace_sink,
                session_id=session_id,
                kind="llm.requested",
                span_id=llm_span,
                parent_span_id=turn_span,
                payload={"model": config.model, "iteration": iteration},
            )

            # Snapshot inputs for retry — must not change between attempts
            stream_messages = list(session.messages)
            call_config = config.to_provider_call_config()

            async def _call_provider() -> list[ProviderStreamEvent]:
                return await _collect_provider_stream(
                    provider,
                    stream_messages,
                    system_prompt,
                    tool_specs,
                    call_config,
                )

            provider_events = await retry_with_backoff(_call_provider, config.retry)

            text_chunks: list[str] = []
            tool_calls: list[ProviderToolCall] = []
            stop_reason = "end_turn"

            for ev in provider_events:
                if isinstance(ev, ProviderTextDelta):
                    text_chunks.append(ev.text)
                    yield TextDelta(text=ev.text)
                elif isinstance(ev, ProviderToolCall):
                    tool_calls.append(ev)
                elif isinstance(ev, ProviderStreamDone):
                    stop_reason = ev.stop_reason
                    await emit_event(
                        trace_sink,
                        session_id=session_id,
                        kind="llm.completed",
                        span_id=new_span_id(),
                        parent_span_id=llm_span,
                        payload={
                            "stop_reason": ev.stop_reason,
                            "input_tokens": ev.input_tokens,
                            "output_tokens": ev.output_tokens,
                        },
                    )

            assistant_blocks: list[ContentBlock] = []
            if text_chunks:
                assistant_blocks.append(TextBlock(text="".join(text_chunks)))
            for tc in tool_calls:
                assistant_blocks.append(ToolCallBlock(
                    invocation_id=tc.invocation_id,
                    name=tc.name,
                    args=tc.args,
                ))
            session.messages.append(Message(role="assistant", content=assistant_blocks))

            await dispatch_hooks(
                hooks,
                HookEvent(
                    kind="post_llm",
                    session_id=session_id,
                    payload={
                        "iteration": iteration,
                        "stop_reason": stop_reason,
                        "n_tool_calls": len(tool_calls),
                    },
                ),
                trace_sink,
                turn_span,
            )

            if not tool_calls:
                stop = True
                yield IterationCompleted(iteration=iteration)
                iteration += 1
                break

            tool_result_blocks: list[ContentBlock] = []
            for tc in tool_calls:
                yield ToolCallStarted(
                    tool_name=tc.name,
                    invocation_id=tc.invocation_id,
                    args=tc.args,
                )

                inv = ToolInvocation(
                    name=tc.name,
                    args=tc.args,
                    invocation_id=tc.invocation_id,
                    session_id=session_id,
                )

                tool = tools.get(tc.name)
                if tool is None:
                    result = await _result_for_unknown_tool(
                        inv=inv,
                        sink=trace_sink,
                        parent_span=turn_span,
                    )
                else:
                    ctx = ToolContext(
                        session_store=session_store,
                        trace_sink=trace_sink,
                        current_span_id=turn_span,
                        new_span_id=new_span_id,
                    )
                    result = await execute_tool(
                        invocation=inv,
                        tool=tool,
                        permission_resolver=permission_resolver,
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

            session.messages.append(Message(role="tool", content=tool_result_blocks))
            yield IterationCompleted(iteration=iteration)
            iteration += 1

            # Compaction check
            if (
                compaction is not None
                and config.compaction_trigger_tokens is not None
            ):
                current_tokens = counter(session.messages)
                if current_tokens > config.compaction_trigger_tokens:
                    should = await compaction.should_compact(
                        session_id, current_tokens, config.context_window_tokens
                    )
                    if should:
                        before_n = len(session.messages)
                        before_tokens = current_tokens
                        await session_store.save(session)
                        fresh = await session_store.load(session_id)
                        assert fresh is not None
                        session = fresh
                        try:
                            new_messages = await compaction.compact(session_id)
                        except Exception as exc:
                            await emit_event(
                                trace_sink,
                                session_id=session_id,
                                kind="error.raised",
                                span_id=new_span_id(),
                                parent_span_id=turn_span,
                                payload={
                                    "source": "compaction",
                                    "exc_type": type(exc).__name__,
                                    "message": str(exc),
                                },
                            )
                            continue
                        session.messages = new_messages
                        after_n = len(session.messages)
                        after_tokens = counter(session.messages)
                        await emit_event(
                            trace_sink,
                            session_id=session_id,
                            kind="compaction.triggered",
                            span_id=new_span_id(),
                            parent_span_id=turn_span,
                            payload={
                                "before_msgs": before_n,
                                "after_msgs": after_n,
                                "before_tokens": before_tokens,
                                "after_tokens": after_tokens,
                            },
                        )

        await dispatch_hooks(
            hooks,
            HookEvent(
                kind="turn_complete",
                session_id=session_id,
                payload={"total_iterations": iteration},
            ),
            trace_sink,
            turn_span,
        )
        await dispatch_hooks(
            hooks,
            HookEvent(
                kind="session_end",
                session_id=session_id,
                payload={"total_iterations": iteration},
            ),
            trace_sink,
            turn_span,
        )

        await session_store.save(session)
        saved = True

        await emit_event(
            trace_sink,
            session_id=session_id,
            kind="turn.completed",
            span_id=new_span_id(),
            parent_span_id=turn_span,
            payload={"total_iterations": iteration},
        )
        try:
            await trace_sink.flush()
        except Exception:
            pass

        yield TurnCompleted(total_iterations=iteration)

    finally:
        if not saved:
            try:
                await session_store.save(session)
            except Exception as save_exc:
                try:
                    await emit_event(
                        trace_sink,
                        session_id=session_id,
                        kind="error.raised",
                        span_id=new_span_id(),
                        parent_span_id=turn_span,
                        payload={
                            "source": "engine_finally",
                            "exc_type": type(save_exc).__name__,
                            "message": str(save_exc),
                        },
                    )
                except Exception:
                    pass
        try:
            await trace_sink.flush()
        except Exception:
            pass


async def _result_for_unknown_tool(
    inv: ToolInvocation,
    sink: TraceSink,
    parent_span: str,
) -> ToolResult:
    await emit_event(
        sink,
        session_id=inv.session_id,
        kind="error.raised",
        span_id=new_span_id(),
        parent_span_id=parent_span,
        payload={
            "source": "engine",
            "exc_type": "ToolNotFoundError",
            "message": f"tool {inv.name!r} not registered",
        },
    )
    return ToolResult(
        success=False,
        error=f"tool {inv.name!r} not registered",
    )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
pytest -q  # full suite
ruff check src/meta_harney tests
mypy src/meta_harney
```

Expected: all retry tests pass + existing 184 also pass; ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): wire retry_with_backoff into provider.stream call

Engine now wraps the entire provider.stream() consumption in
retry_with_backoff(config.retry). _collect_provider_stream() helper
buffers the full stream so retries can re-run cleanly (partial
consumption isn't safe to resume).

Stream-snapshot strategy: messages + system_prompt + tool_specs +
call_config are captured before the first attempt and reused on retry,
so transient failures don't see drifting input.

E2E: retry_recovers_from_transient_failure, retry_gives_up_after_max,
non_retryable_propagates_immediately.

Phase 2 carry-over item #1 addressed."
```

---

## Task 3: Extend `ToolContext` with optional `multi_agent` field

**Files:**
- Modify: `src/meta_harney/abstractions/tool.py`
- Modify: `tests/unit/abstractions/test_tool.py`

This is a small enabler for Task 11 (AgentRuntime wires multi_agent through ToolContext). Tools that need to spawn child agents call `ctx.multi_agent.spawn(...)`.

- [ ] **Step 1: Append failing test to `tests/unit/abstractions/test_tool.py`**

Read the file, then append:

```python


def test_tool_context_multi_agent_field_defaults_to_none() -> None:
    """ToolContext gains optional multi_agent field for child-agent spawning."""
    import uuid as _uuid

    ctx = ToolContext(
        session_store=object(),  # type: ignore[arg-type]
        trace_sink=object(),  # type: ignore[arg-type]
        current_span_id="x",
        new_span_id=lambda: _uuid.uuid4().hex[:16],
    )
    # New field exists with default None
    assert ctx.multi_agent is None


def test_tool_context_multi_agent_field_accepts_backend() -> None:
    """When provided, multi_agent is exposed verbatim to tools."""
    import uuid as _uuid

    class FakeBackend:
        async def spawn(self, spec, initial_message, parent_session_id, mode="blocking"):
            raise NotImplementedError

        async def join(self, child_session_id, timeout=None):
            raise NotImplementedError

        async def status(self, child_session_id):
            raise NotImplementedError

        async def cancel(self, child_session_id):
            raise NotImplementedError

    backend = FakeBackend()
    ctx = ToolContext(
        session_store=object(),  # type: ignore[arg-type]
        trace_sink=object(),  # type: ignore[arg-type]
        current_span_id="x",
        new_span_id=lambda: _uuid.uuid4().hex[:16],
        multi_agent=backend,  # type: ignore[arg-type]
    )
    assert ctx.multi_agent is backend
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_tool.py -v
```

Expected: TypeError or AttributeError — ToolContext doesn't have `multi_agent` yet.

- [ ] **Step 3: Modify `src/meta_harney/abstractions/tool.py`**

In the TYPE_CHECKING block, add `MultiAgentBackend` import. Then add the `multi_agent` field to the `ToolContext` dataclass.

Read the current file, then make these edits:

1. In the `TYPE_CHECKING` block, add the import:

```python
if TYPE_CHECKING:
    from meta_harney.abstractions.multi_agent import MultiAgentBackend
    from meta_harney.abstractions.session import SessionStore
    from meta_harney.abstractions.trace import TraceSink
```

2. In the `ToolContext` dataclass, add the field at the end with a `None` default:

```python
@dataclass
class ToolContext:
    """Runtime services exposed to tools at execute() time.

    Business tools may subclass to inject additional services (e.g., DB session).
    The engine constructs ToolContext per invocation.
    """

    session_store: SessionStore
    trace_sink: TraceSink
    current_span_id: str
    new_span_id: Callable[[], str]
    multi_agent: MultiAgentBackend | None = None
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_tool.py -v
pytest -q  # full suite — no regression in tool_dispatch / loop tests
ruff check src/meta_harney/abstractions tests/unit/abstractions
mypy src/meta_harney/abstractions/tool.py
```

Expected: new tests pass + all 187+ existing pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/tool.py tests/unit/abstractions/test_tool.py
git commit -m "feat(abstractions): ToolContext gains optional multi_agent field

Optional MultiAgentBackend reference on ToolContext lets tools spawn
child agents (when AgentRuntime is configured with a multi-agent
backend in Phase 3 Task 11).

Default: None. Tools that need it check 'if ctx.multi_agent is None'
and surface a clear error. Default ToolContext construction paths
(engine, tests) don't need changes — they get the default."
```

---

## Task 4: AgentRuntime scaffold + `create_session`

**Files:**
- Create: `src/meta_harney/runtime.py`
- Test: `tests/unit/test_runtime.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for AgentRuntime — top-level SDK entry point."""
from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.providers.fake import FakeLLMProvider, FakeRound
from meta_harney.runtime import AgentRuntime


def _runtime(store: MemorySessionStore | None = None) -> AgentRuntime:
    s = store or MemorySessionStore()
    return AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="ok", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=s),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=s,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )


async def test_create_session_returns_unique_session() -> None:
    rt = _runtime()
    s1 = await rt.create_session()
    s2 = await rt.create_session()
    assert s1.id != s2.id
    # Both persisted
    assert await rt._session_store.load(s1.id) is not None
    assert await rt._session_store.load(s2.id) is not None


async def test_create_session_with_explicit_id() -> None:
    rt = _runtime()
    s = await rt.create_session(session_id="my-explicit-id")
    assert s.id == "my-explicit-id"


async def test_create_session_with_tenant_user_attrs() -> None:
    rt = _runtime()
    s = await rt.create_session(
        tenant_id="acme",
        user_id="u-1",
        attributes={"customer_id": "C-001"},
        metadata={"source": "api"},
    )
    assert s.tenant_id == "acme"
    assert s.user_id == "u-1"
    assert s.attributes["customer_id"] == "C-001"
    assert s.metadata["source"] == "api"


async def test_create_session_duplicate_id_raises() -> None:
    """Explicit session_id that already exists raises (don't silently clobber)."""
    import pytest

    from meta_harney.errors import SessionConflictError

    rt = _runtime()
    await rt.create_session(session_id="dup")
    with pytest.raises(SessionConflictError):
        await rt.create_session(session_id="dup")
```

Save to `tests/unit/test_runtime.py`.

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/meta_harney/runtime.py`**

```python
"""AgentRuntime — top-level SDK entry point.

Wraps the engine.run_turn primitive with session lifecycle management,
service composition, and a clean two-method API (invoke + stream).

Phase 3 scope: create_session + invoke + stream. Multi-agent backend is
wired in (Phase 3 Task 11) so tools can spawn child agents.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import MultiAgentBackend
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.tool import BaseTool
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import TokenCounter
from meta_harney.errors import SessionConflictError
from meta_harney.providers.base import LLMProvider


class AgentRuntime:
    """Top-level SDK facade for running agent turns.

    Holds all service dependencies as immutable attributes. Provides:
      - create_session(): create + persist a new Session
      - invoke(): run one turn, return final assistant message (blocking)
      - stream(): run one turn, yield StreamEvents
    """

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_builder: PromptBuilder,
        permission_resolver: PermissionResolver,
        session_store: SessionStore,
        trace_sink: TraceSink,
        config: RuntimeConfig,
        tools: dict[str, BaseTool] | None = None,
        hooks: list[BaseHook] | None = None,
        compaction: CompactionStrategy | None = None,
        token_counter: TokenCounter | None = None,
        multi_agent: MultiAgentBackend | None = None,
    ) -> None:
        self._provider = provider
        self._prompt_builder = prompt_builder
        self._permission_resolver = permission_resolver
        self._session_store = session_store
        self._trace_sink = trace_sink
        self._config = config
        self._tools = tools or {}
        self._hooks = hooks or []
        self._compaction = compaction
        self._token_counter = token_counter
        self._multi_agent = multi_agent

    async def create_session(
        self,
        *,
        session_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create and persist a new session.

        - `session_id`: if omitted, a UUID hex is generated.
        - If the id already exists in the store, raises SessionConflictError.
        """
        sid = session_id or uuid.uuid4().hex
        existing = await self._session_store.load(sid)
        if existing is not None:
            raise SessionConflictError(
                session_id=sid, expected_version=0, found_version=existing.version
            )
        s = Session(
            id=sid,
            tenant_id=tenant_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            attributes=dict(attributes) if attributes else {},
            metadata=dict(metadata) if metadata else {},
        )
        await self._session_store.save(s)
        return s
```

(Note: `invoke` and `stream` come in Task 5. This task is just the scaffold + `create_session`.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py -v
ruff check src/meta_harney/runtime.py tests/unit/test_runtime.py
mypy src/meta_harney/runtime.py
```

Expected: 4 tests pass, clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/runtime.py tests/unit/test_runtime.py
git commit -m "feat(runtime): AgentRuntime scaffold + create_session

AgentRuntime holds all service dependencies (provider, prompt_builder,
permission_resolver, session_store, trace_sink, config, optional
tools/hooks/compaction/token_counter/multi_agent).

create_session() creates a new Session with a UUID (or explicit id),
sets tenant_id/user_id/attributes/metadata, persists via session_store.
Duplicate explicit id raises SessionConflictError (don't silently
clobber existing state).

invoke + stream methods land in Task 5."
```

---

## Task 5: AgentRuntime.stream + invoke

**Files:**
- Modify: `src/meta_harney/runtime.py`
- Modify: `tests/unit/test_runtime.py`

- [ ] **Step 1: Append failing tests to `tests/unit/test_runtime.py`**

```python


from meta_harney.engine.stream_events import StreamEvent, TextDelta, TurnCompleted
from meta_harney.providers.fake import FakeRound


async def test_stream_yields_events() -> None:
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="hello from stream", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    session = await rt.create_session()

    events: list[StreamEvent] = []
    async for ev in rt.stream(session.id, "hi"):
        events.append(ev)

    assert any(isinstance(e, TurnCompleted) for e in events)
    assert any(isinstance(e, TextDelta) and "hello from stream" in e.text for e in events)


async def test_stream_accepts_string_or_message() -> None:
    """stream() accepts a plain string (creates user TextBlock) OR a full Message."""
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="a", stop_reason="end_turn"),
            FakeRound(text="b", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    s = await rt.create_session()

    # String input
    async for _ in rt.stream(s.id, "first"):
        pass
    # Message input
    msg = Message(role="user", content=[TextBlock(text="second")])
    async for _ in rt.stream(s.id, msg):
        pass

    loaded = await store.load(s.id)
    assert loaded is not None
    user_msgs = [m for m in loaded.messages if m.role == "user"]
    user_texts = [m.content[0].text for m in user_msgs if isinstance(m.content[0], TextBlock)]
    assert user_texts == ["first", "second"]


async def test_invoke_returns_final_assistant_message() -> None:
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="The answer is 42.", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    session = await rt.create_session()
    result = await rt.invoke(session.id, "what is the answer?")

    assert result.role == "assistant"
    assert isinstance(result.content[0], TextBlock)
    assert "answer is 42" in result.content[0].text


async def test_invoke_returns_empty_assistant_on_no_text() -> None:
    """When LLM emits no text, return assistant message with empty content."""
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=FakeLLMProvider(rounds=[
            FakeRound(text="", stop_reason="end_turn"),
        ]),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
    )
    s = await rt.create_session()
    result = await rt.invoke(s.id, "hi")
    assert result.role == "assistant"
    # No TextBlocks expected
    assert all(not isinstance(b, TextBlock) for b in result.content)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py -v
```

Expected: AttributeError on `rt.stream` or `rt.invoke`.

- [ ] **Step 3: Add `stream` and `invoke` methods to `AgentRuntime`**

Append these to the `AgentRuntime` class in `src/meta_harney/runtime.py`:

```python
    async def stream(
        self,
        session_id: str,
        message: Message | str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run one turn, yielding StreamEvents.

        `message` may be a string (wrapped as user TextBlock) or a full Message.
        """
        from meta_harney.abstractions._types import TextBlock as _TB

        if isinstance(message, str):
            user_msg = Message(role="user", content=[_TB(text=message)])
        else:
            user_msg = message

        from meta_harney.engine.loop import run_turn as _run_turn

        async for ev in _run_turn(
            session_id=session_id,
            user_message=user_msg,
            provider=self._provider,
            prompt_builder=self._prompt_builder,
            permission_resolver=self._permission_resolver,
            tools=self._tools,
            hooks=self._hooks,
            session_store=self._session_store,
            trace_sink=self._trace_sink,
            config=self._config,
            compaction=self._compaction,
            token_counter=self._token_counter,
        ):
            yield ev

    async def invoke(
        self,
        session_id: str,
        message: Message | str,
    ) -> Message:
        """Run one turn, return the final assistant message.

        Convenience wrapper around stream(): drains events, then loads the
        session and returns the last assistant message.
        """
        async for _ev in self.stream(session_id, message):
            pass
        s = await self._session_store.load(session_id)
        assert s is not None, "session unexpectedly missing after invoke"
        # Return the last assistant message
        for m in reversed(s.messages):
            if m.role == "assistant":
                return m
        # No assistant message: return an empty one (edge case)
        return Message(role="assistant", content=[])
```

Add these to the file imports at top:

```python
from collections.abc import AsyncGenerator
from meta_harney.engine.stream_events import StreamEvent
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py -v
pytest -q
ruff check src/meta_harney/runtime.py tests/unit/test_runtime.py
mypy src/meta_harney/runtime.py
```

Expected: 8 runtime tests pass (4 from T4 + 4 from T5); full suite green; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/runtime.py tests/unit/test_runtime.py
git commit -m "feat(runtime): AgentRuntime.stream + invoke

stream(session_id, msg) → AsyncGenerator[StreamEvent, None]: forwards
to engine.run_turn with all configured services. Accepts plain string
(wrapped as user TextBlock) or full Message.

invoke(session_id, msg) → Message: drains stream(), returns the last
assistant message from the session. Returns empty assistant message
if LLM produced no content (edge case)."
```

---

## Task 6: AgentRuntime E2E test

**Files:**
- Modify: `tests/integration/test_engine_e2e.py` (add an AgentRuntime-driven scenario)

- [ ] **Step 1: Append failing test**

```python


from meta_harney.runtime import AgentRuntime


async def test_runtime_drives_full_turn_e2e() -> None:
    """AgentRuntime composes services and drives a multi-message conversation."""
    store = MemorySessionStore()
    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="i1", name="echo", args={"text": "world"},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="Got it.", stop_reason="end_turn"),
    ])

    rt = AgentRuntime(
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="x"),
        tools={"echo": _EchoTool()},
        hooks=[],
    )

    session = await rt.create_session(tenant_id="acme")
    final = await rt.invoke(session.id, "echo world please")

    assert final.role == "assistant"
    assert isinstance(final.content[0], TextBlock)
    assert "Got it" in final.content[0].text

    # Session state: 4 messages (user, assistant w/ tool call, tool, assistant final)
    loaded = await store.load(session.id)
    assert loaded is not None
    assert loaded.tenant_id == "acme"
    assert len(loaded.messages) == 4
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_runtime_drives_full_turn_e2e -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(runtime): AgentRuntime e2e — tool cycle via create+invoke

End-to-end via the public API: create_session(tenant_id) → invoke().
Verifies tool call cycle + final assistant message + tenant_id
preservation + correct session message count."
```

---

## Task 7: `_ChildPromptBuilder` + `InProcessMultiAgentBackend` scaffold

**Files:**
- Create: `src/meta_harney/builtin/multi_agent/__init__.py` (empty)
- Create: `src/meta_harney/builtin/multi_agent/child_prompt.py`
- Create: `src/meta_harney/builtin/multi_agent/in_process.py` (scaffold only — methods are `NotImplementedError`)
- Test: `tests/unit/builtin/multi_agent/__init__.py` (empty)
- Test: `tests/unit/builtin/multi_agent/test_in_process.py`

- [ ] **Step 1: Create empty package dirs**

```bash
mkdir -p src/meta_harney/builtin/multi_agent
mkdir -p tests/unit/builtin/multi_agent
touch src/meta_harney/builtin/multi_agent/__init__.py
touch tests/unit/builtin/multi_agent/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/builtin/multi_agent/test_in_process.py`:

```python
"""Tests for InProcessMultiAgentBackend (Phase 3)."""
from __future__ import annotations

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.multi_agent import AgentSpec
from meta_harney.abstractions.session import Session
from meta_harney.builtin.multi_agent.child_prompt import _ChildPromptBuilder
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.providers.fake import FakeLLMProvider, FakeRound


async def test_child_prompt_builder_returns_instructions() -> None:
    """_ChildPromptBuilder overrides system prompt with AgentSpec.instructions."""
    store = MemorySessionStore()
    builder = _ChildPromptBuilder(
        instructions="You are a billing specialist.",
        session_store=store,
    )
    sp = await builder.build_system_prompt("any-session-id")
    assert sp == "You are a billing specialist."


async def test_child_prompt_builder_returns_session_messages() -> None:
    """_ChildPromptBuilder loads context from the session store like Minimal."""
    from datetime import datetime, timezone

    store = MemorySessionStore()
    s = Session(
        id="s1",
        created_at=datetime.now(timezone.utc),
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    await store.save(s)

    builder = _ChildPromptBuilder(
        instructions="be helpful",
        session_store=store,
    )
    msgs = await builder.build_context_messages("s1")
    assert len(msgs) == 1
    assert isinstance(msgs[0].content[0], TextBlock)


def test_in_process_backend_constructs() -> None:
    """Scaffold: constructor accepts all service deps."""
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
    # Just verify the object exists with the expected interface
    assert hasattr(backend, "spawn")
    assert hasattr(backend, "join")
    assert hasattr(backend, "status")
    assert hasattr(backend, "cancel")
```

- [ ] **Step 3: RED**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `src/meta_harney/builtin/multi_agent/child_prompt.py`**

```python
"""Child agent prompt builder.

Wraps a SessionStore + overrides system prompt with AgentSpec.instructions.
Used by InProcessMultiAgentBackend to give each child agent a different
system prompt than the parent.
"""
from __future__ import annotations

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.session import SessionStore


class _ChildPromptBuilder:
    """PromptBuilder for child agents — instructions override system prompt."""

    def __init__(
        self,
        instructions: str,
        session_store: SessionStore,
    ) -> None:
        self._instructions = instructions
        self._session_store = session_store

    async def build_system_prompt(self, session_id: str) -> str:
        return self._instructions

    async def build_context_messages(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None:
            return []
        return list(s.messages)
```

- [ ] **Step 5: Implement scaffold `src/meta_harney/builtin/multi_agent/in_process.py`**

```python
"""InProcessMultiAgentBackend — child agents run in the same process.

Each spawn() creates a fresh Session linked to the parent, then runs
engine.run_turn with a _ChildPromptBuilder. Blocking mode awaits the
result; detached mode creates an asyncio.Task and stores it.

Task 8 implements spawn() blocking mode.
Task 9 implements spawn() detached + join + status + cancel.
"""
from __future__ import annotations

import asyncio
from typing import Any

from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import AgentSpec, SpawnHandle
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import BaseTool, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import TokenCounter
from meta_harney.providers.base import LLMProvider


class InProcessMultiAgentBackend:
    """Multi-agent backend that runs children in the same asyncio loop."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        permission_resolver: PermissionResolver,
        session_store: SessionStore,
        trace_sink: TraceSink,
        config: RuntimeConfig,
        all_tools: dict[str, BaseTool],
        hooks: list[BaseHook],
        compaction: CompactionStrategy | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._provider = provider
        self._permission_resolver = permission_resolver
        self._session_store = session_store
        self._trace_sink = trace_sink
        self._config = config
        self._all_tools = all_tools
        self._hooks = hooks
        self._compaction = compaction
        self._token_counter = token_counter

        # Detached-mode bookkeeping
        self._tasks: dict[str, asyncio.Task[ToolResult]] = {}
        self._results: dict[str, ToolResult] = {}

    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: str = "blocking",
    ) -> SpawnHandle:
        raise NotImplementedError("Task 8 implements blocking; Task 9 detached")

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        raise NotImplementedError("Task 9")

    async def status(self, child_session_id: str) -> TaskState:
        raise NotImplementedError("Task 9")

    async def cancel(self, child_session_id: str) -> None:
        raise NotImplementedError("Task 9")
```

- [ ] **Step 6: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
ruff check src/meta_harney/builtin/multi_agent tests/unit/builtin/multi_agent
mypy src/meta_harney/builtin/multi_agent
```

Expected: 3 tests pass (child prompt × 2 + scaffold construct), clean.

- [ ] **Step 7: Commit**

```bash
git add src/meta_harney/builtin/multi_agent/ tests/unit/builtin/multi_agent/
git commit -m "feat(builtin): multi-agent scaffold + _ChildPromptBuilder

_ChildPromptBuilder: PromptBuilder for child agents — system prompt
is the AgentSpec.instructions string; context is loaded from session
store (same as MinimalPromptBuilder).

InProcessMultiAgentBackend: holds parent's full toolset + service
deps. spawn/join/status/cancel are NotImplementedError stubs (filled
in Tasks 8-9). Detached-mode bookkeeping fields ready (_tasks, _results)."
```

---

## Task 8: `InProcessMultiAgentBackend.spawn()` blocking mode

**Files:**
- Modify: `src/meta_harney/builtin/multi_agent/in_process.py`
- Modify: `tests/unit/builtin/multi_agent/test_in_process.py`

- [ ] **Step 1: Append failing test**

```python


async def test_spawn_blocking_returns_handle_with_result() -> None:
    """Blocking spawn awaits the child to completion and returns the handle."""
    store = MemorySessionStore()
    # Pre-create parent session
    from datetime import datetime, timezone
    parent = Session(id="parent-1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[
        FakeRound(text="child output text", stop_reason="end_turn"),
    ])

    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    spec = AgentSpec(
        name="helper",
        instructions="You are a helpful child agent.",
        allowed_tools=[],
    )
    handle = await backend.spawn(
        spec=spec,
        initial_message="please help",
        parent_session_id="parent-1",
        mode="blocking",
    )

    assert handle.mode == "blocking"
    assert handle.child_session_id  # non-empty

    # Child session was created with parent linkage
    child = await store.load(handle.child_session_id)
    assert child is not None
    assert child.parent_session_id == "parent-1"
    # Child has user msg + assistant msg
    assert len(child.messages) == 2


async def test_spawn_blocking_filters_tools_by_allowed_list() -> None:
    """Children only see tools listed in spec.allowed_tools."""
    from typing import ClassVar
    from pydantic import BaseModel as _BM
    from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult

    class _DummyInput(_BM):
        pass

    class _AvailTool(BaseTool):
        name: ClassVar[str] = "avail"
        description: ClassVar[str] = "available to child"
        input_schema: ClassVar[type] = _DummyInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output="ok")

    class _ForbiddenTool(BaseTool):
        name: ClassVar[str] = "forbidden"
        description: ClassVar[str] = "not allowed for child"
        input_schema: ClassVar[type] = _DummyInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output="should not run")

    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-2", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="ok", stop_reason="end_turn")])

    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={"avail": _AvailTool(), "forbidden": _ForbiddenTool()},
        hooks=[],
    )

    spec = AgentSpec(
        name="helper",
        instructions="be helpful",
        allowed_tools=["avail"],  # forbidden excluded
    )
    handle = await backend.spawn(
        spec=spec,
        initial_message="hi",
        parent_session_id="parent-2",
        mode="blocking",
    )
    # Provider was called once (no tool call requested) — verify by
    # asserting the recorded call only exposed the "avail" tool.
    assert len(provider.calls) == 1
    tool_names = [t.name for t in provider.calls[0].tools]
    assert tool_names == ["avail"]


async def test_spawn_unknown_mode_raises() -> None:
    """Invalid mode arg raises ValueError."""
    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-3", created_at=datetime.now(timezone.utc))
    await store.save(parent)
    backend = InProcessMultiAgentBackend(
        provider=FakeLLMProvider(rounds=[]),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )
    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    with pytest.raises(ValueError, match="mode"):
        await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="parent-3",
            mode="bogus",
        )
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
```

Expected: 3 new tests fail with NotImplementedError or other.

- [ ] **Step 3: Implement `spawn()` blocking path**

In `src/meta_harney/builtin/multi_agent/in_process.py`, replace the `spawn`/`join`/`status`/`cancel` block with this expanded implementation:

```python
    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: str = "blocking",
    ) -> SpawnHandle:
        if mode not in ("blocking", "detached"):
            raise ValueError(f"unknown spawn mode: {mode!r}")

        # Create child session linked to parent
        from datetime import datetime, timezone
        from meta_harney.abstractions.session import Session
        import uuid as _uuid

        parent = await self._session_store.load(parent_session_id)
        child_id = f"child-{_uuid.uuid4().hex[:12]}"
        child = Session(
            id=child_id,
            tenant_id=parent.tenant_id if parent else None,
            user_id=parent.user_id if parent else None,
            parent_session_id=parent_session_id,
            created_at=datetime.now(timezone.utc),
        )
        await self._session_store.save(child)

        # Filter parent's toolset to those allowed in the spec
        child_tools = {
            name: tool
            for name, tool in self._all_tools.items()
            if name in spec.allowed_tools
        }

        # Build a config that respects spec.max_iters
        child_config = self._config.model_copy(update={"max_iterations": spec.max_iters})

        # Run the child agent and capture the final assistant text as ToolResult
        if mode == "blocking":
            result = await self._run_child(
                child_id=child_id,
                initial_message=initial_message,
                instructions=spec.instructions,
                child_tools=child_tools,
                child_config=child_config,
            )
            self._results[child_id] = result
            return SpawnHandle(child_session_id=child_id, mode="blocking")

        # detached — Task 9 implements this; for now, raise
        raise NotImplementedError("detached mode lands in Task 9")

    async def _run_child(
        self,
        *,
        child_id: str,
        initial_message: str,
        instructions: str,
        child_tools: dict[str, BaseTool],
        child_config: RuntimeConfig,
    ) -> ToolResult:
        """Run one child agent turn; return final assistant text as ToolResult."""
        from meta_harney.abstractions._types import Message, TextBlock
        from meta_harney.builtin.multi_agent.child_prompt import _ChildPromptBuilder
        from meta_harney.engine.loop import run_turn
        from meta_harney.engine.stream_events import TextDelta

        child_builder = _ChildPromptBuilder(
            instructions=instructions,
            session_store=self._session_store,
        )
        user_msg = Message(role="user", content=[TextBlock(text=initial_message)])
        assistant_text_chunks: list[str] = []

        async for ev in run_turn(
            session_id=child_id,
            user_message=user_msg,
            provider=self._provider,
            prompt_builder=child_builder,
            permission_resolver=self._permission_resolver,
            tools=child_tools,
            hooks=self._hooks,
            session_store=self._session_store,
            trace_sink=self._trace_sink,
            config=child_config,
            compaction=self._compaction,
            token_counter=self._token_counter,
        ):
            if isinstance(ev, TextDelta):
                assistant_text_chunks.append(ev.text)

        final_text = "".join(assistant_text_chunks)
        return ToolResult(success=True, output=final_text)
```

(Keep the existing scaffold `join`, `status`, `cancel` methods as `NotImplementedError` stubs.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
ruff check src/meta_harney/builtin/multi_agent
mypy src/meta_harney/builtin/multi_agent
```

Expected: 6 tests pass total in this file (3 prior + 3 new); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/builtin/multi_agent/in_process.py tests/unit/builtin/multi_agent/test_in_process.py
git commit -m "feat(multi-agent): InProcessMultiAgentBackend.spawn() blocking mode

Blocking spawn creates a child session linked to the parent (tenant_id,
user_id, parent_session_id inherited), filters parent's toolset by
spec.allowed_tools, builds child config with spec.max_iters, runs
engine.run_turn with _ChildPromptBuilder. Accumulates assistant text
into a ToolResult cached by child_session_id.

Detached mode (mode='detached') still NotImplementedError — Task 9.
Invalid mode raises ValueError."
```

---

## Task 9: spawn() detached + join + status + cancel

**Files:**
- Modify: `src/meta_harney/builtin/multi_agent/in_process.py`
- Modify: `tests/unit/builtin/multi_agent/test_in_process.py`

- [ ] **Step 1: Append failing tests**

```python


import asyncio
from meta_harney.abstractions.task import TaskState


async def test_spawn_detached_returns_handle_immediately() -> None:
    """Detached spawn returns SpawnHandle without waiting for child."""
    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-d1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="result", stop_reason="end_turn")])
    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    handle = await backend.spawn(
        spec=spec,
        initial_message="go",
        parent_session_id="parent-d1",
        mode="detached",
    )
    assert handle.mode == "detached"

    # Join to await completion
    result = await backend.join(handle.child_session_id)
    assert result.success
    assert "result" in str(result.output)


async def test_status_for_completed_child() -> None:
    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-s1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    provider = FakeLLMProvider(rounds=[FakeRound(text="done", stop_reason="end_turn")])
    backend = InProcessMultiAgentBackend(
        provider=provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-s1",
        mode="detached",
    )
    # Await completion
    await backend.join(handle.child_session_id)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.SUCCEEDED


async def test_status_for_running_child() -> None:
    """While the child is still running, status is RUNNING."""
    from collections.abc import AsyncGenerator
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamDone,
        ProviderStreamEvent,
        ProviderTextDelta,
        ToolSpec,
    )

    class _SlowProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            await asyncio.sleep(0.5)
            yield ProviderTextDelta(text="slow")
            yield ProviderStreamDone(stop_reason="end_turn")

    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-r1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_SlowProvider(),  # type: ignore[arg-type]
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-r1",
        mode="detached",
    )
    # Status before join (race-safe: provider sleeps 500ms)
    await asyncio.sleep(0.05)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.RUNNING

    # Then await
    result = await backend.join(handle.child_session_id)
    assert result.success


async def test_cancel_detached_child() -> None:
    """cancel() interrupts a running detached child task."""
    from collections.abc import AsyncGenerator
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamEvent,
        ToolSpec,
    )

    class _BlockingProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            await asyncio.sleep(10.0)
            yield  # type: ignore[unreachable]

    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-c1", created_at=datetime.now(timezone.utc))
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
        initial_message="go",
        parent_session_id="parent-c1",
        mode="detached",
    )
    await asyncio.sleep(0.05)
    await backend.cancel(handle.child_session_id)
    s = await backend.status(handle.child_session_id)
    assert s == TaskState.CANCELLED


async def test_join_unknown_child_raises() -> None:
    """Joining a child that was never spawned raises."""
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
    with pytest.raises(KeyError, match="no such child"):
        await backend.join("nonexistent-id")


async def test_join_timeout_raises_child_timeout_error() -> None:
    """join(timeout=...) raises ChildTimeoutError if exceeded."""
    from collections.abc import AsyncGenerator
    from meta_harney.errors import ChildTimeoutError
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamEvent,
        ToolSpec,
    )

    class _SlowProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            await asyncio.sleep(10.0)
            yield  # type: ignore[unreachable]

    store = MemorySessionStore()
    from datetime import datetime, timezone
    parent = Session(id="parent-t1", created_at=datetime.now(timezone.utc))
    await store.save(parent)

    backend = InProcessMultiAgentBackend(
        provider=_SlowProvider(),  # type: ignore[arg-type]
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        all_tools={},
        hooks=[],
    )

    handle = await backend.spawn(
        spec=AgentSpec(name="x", instructions="y", allowed_tools=[]),
        initial_message="go",
        parent_session_id="parent-t1",
        mode="detached",
    )
    with pytest.raises(ChildTimeoutError):
        await backend.join(handle.child_session_id, timeout=0.1)

    # Cleanup the still-running task
    await backend.cancel(handle.child_session_id)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
```

Expected: 6 new tests fail with NotImplementedError.

- [ ] **Step 3: Implement detached + join + status + cancel**

Replace the entire body of `spawn`, `join`, `status`, `cancel` in `in_process.py` with:

```python
    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: str = "blocking",
    ) -> SpawnHandle:
        if mode not in ("blocking", "detached"):
            raise ValueError(f"unknown spawn mode: {mode!r}")

        from datetime import datetime, timezone
        from meta_harney.abstractions.session import Session
        import uuid as _uuid

        parent = await self._session_store.load(parent_session_id)
        child_id = f"child-{_uuid.uuid4().hex[:12]}"
        child = Session(
            id=child_id,
            tenant_id=parent.tenant_id if parent else None,
            user_id=parent.user_id if parent else None,
            parent_session_id=parent_session_id,
            created_at=datetime.now(timezone.utc),
        )
        await self._session_store.save(child)

        child_tools = {
            name: tool
            for name, tool in self._all_tools.items()
            if name in spec.allowed_tools
        }
        child_config = self._config.model_copy(update={"max_iterations": spec.max_iters})

        if mode == "blocking":
            result = await self._run_child(
                child_id=child_id,
                initial_message=initial_message,
                instructions=spec.instructions,
                child_tools=child_tools,
                child_config=child_config,
            )
            self._results[child_id] = result
            return SpawnHandle(child_session_id=child_id, mode="blocking")

        # detached
        coro = self._run_child(
            child_id=child_id,
            initial_message=initial_message,
            instructions=spec.instructions,
            child_tools=child_tools,
            child_config=child_config,
        )
        task = asyncio.create_task(coro)
        self._tasks[child_id] = task
        return SpawnHandle(child_session_id=child_id, mode="detached")

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        # Already-completed blocking child?
        if child_session_id in self._results:
            return self._results[child_session_id]

        task = self._tasks.get(child_session_id)
        if task is None:
            raise KeyError(f"no such child: {child_session_id!r}")

        from meta_harney.errors import ChildTimeoutError

        try:
            if timeout is None:
                result = await task
            else:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ChildTimeoutError(
                f"child {child_session_id!r} did not complete within {timeout}s"
            ) from exc
        self._results[child_session_id] = result
        return result

    async def status(self, child_session_id: str) -> TaskState:
        if child_session_id in self._results:
            return TaskState.SUCCEEDED
        task = self._tasks.get(child_session_id)
        if task is None:
            return TaskState.PENDING  # unknown child — treat as not yet started
        if task.cancelled():
            return TaskState.CANCELLED
        if task.done():
            if task.exception() is not None:
                return TaskState.FAILED
            return TaskState.SUCCEEDED
        return TaskState.RUNNING

    async def cancel(self, child_session_id: str) -> None:
        task = self._tasks.get(child_session_id)
        if task is None or task.done():
            return
        task.cancel()
        # Drain the cancellation
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
```

(Keep `_run_child` unchanged from Task 8.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py -v
ruff check src/meta_harney/builtin/multi_agent
mypy src/meta_harney/builtin/multi_agent
```

Expected: 12 tests pass total in this file (6 prior + 6 new); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/builtin/multi_agent/in_process.py tests/unit/builtin/multi_agent/test_in_process.py
git commit -m "feat(multi-agent): detached mode + join + status + cancel

Detached spawn creates an asyncio.Task wrapping _run_child and returns
SpawnHandle(mode='detached') immediately. join() awaits the task with
optional timeout (ChildTimeoutError on exceed). status() maps task state
to TaskState enum (PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED). cancel()
calls task.cancel() and drains the exception.

asyncio.shield used in join() to prevent timeout from cancelling the
underlying task — that's cancel()'s responsibility."
```

---

## Task 10: MultiAgentBackend contract test + apply to InProcess

**Files:**
- Create: `tests/contracts/multi_agent_backend.py`
- Modify: `tests/unit/builtin/multi_agent/test_in_process.py` (add contract subclass)

- [ ] **Step 1: Write `tests/contracts/multi_agent_backend.py`**

```python
"""Contract tests for MultiAgentBackend implementations."""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions.multi_agent import AgentSpec, MultiAgentBackend
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


class MultiAgentBackendContract:
    """Contract tests every MultiAgentBackend must pass.

    Subclass provides:
      - make_backend_and_store() -> tuple of (backend, store)
    """

    @abstractmethod
    def make_backend_and_store(self) -> tuple[MultiAgentBackend, SessionStore]: ...

    async def test_blocking_spawn_returns_handle(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-1", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-1",
            mode="blocking",
        )
        assert handle.mode == "blocking"
        assert handle.child_session_id

    async def test_detached_spawn_returns_handle(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-2", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-2",
            mode="detached",
        )
        assert handle.mode == "detached"
        # Await completion to clean up
        await backend.join(handle.child_session_id)

    async def test_join_returns_tool_result(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-3", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-3",
            mode="detached",
        )
        result = await backend.join(handle.child_session_id)
        assert isinstance(result, ToolResult)

    async def test_status_succeeded_after_join(self) -> None:
        backend, store = self.make_backend_and_store()
        await store.save(
            Session(id="p-4", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id="p-4",
            mode="detached",
        )
        await backend.join(handle.child_session_id)
        s = await backend.status(handle.child_session_id)
        assert s == TaskState.SUCCEEDED

    async def test_child_session_links_to_parent(self) -> None:
        backend, store = self.make_backend_and_store()
        parent_id = "p-5"
        await store.save(
            Session(id=parent_id, tenant_id="acme", created_at=datetime.now(timezone.utc))
        )
        spec = AgentSpec(name="t", instructions="be helpful", allowed_tools=[])
        handle = await backend.spawn(
            spec=spec,
            initial_message="hi",
            parent_session_id=parent_id,
            mode="blocking",
        )
        child = await store.load(handle.child_session_id)
        assert child is not None
        assert child.parent_session_id == parent_id
        # Tenant id inherited
        assert child.tenant_id == "acme"
```

- [ ] **Step 2: Append contract subclass to `tests/unit/builtin/multi_agent/test_in_process.py`**

```python


from tests.contracts.multi_agent_backend import MultiAgentBackendContract


class TestInProcessMultiAgentBackendContract(MultiAgentBackendContract):
    """Inherits all standard MultiAgentBackend contract tests."""

    def make_backend_and_store(self):
        store = MemorySessionStore()
        backend = InProcessMultiAgentBackend(
            provider=FakeLLMProvider(rounds=[
                FakeRound(text="contract test result", stop_reason="end_turn"),
                FakeRound(text="contract test result", stop_reason="end_turn"),
                FakeRound(text="contract test result", stop_reason="end_turn"),
                FakeRound(text="contract test result", stop_reason="end_turn"),
                FakeRound(text="contract test result", stop_reason="end_turn"),
            ]),
            permission_resolver=AllowAllPermissionResolver(),
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(model="fake"),
            all_tools={},
            hooks=[],
        )
        return backend, store
```

(Note: FakeLLMProvider needs enough rounds for all 5 contract tests' spawns — each test does at minimum 1 spawn.)

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/multi_agent/test_in_process.py tests/contracts/multi_agent_backend.py -v
ruff check tests/contracts/multi_agent_backend.py
mypy tests/contracts/multi_agent_backend.py
```

Expected: 17 tests pass in test_in_process (12 prior + 5 contract); clean.

- [ ] **Step 4: Commit**

```bash
git add tests/contracts/multi_agent_backend.py tests/unit/builtin/multi_agent/test_in_process.py
git commit -m "test: MultiAgentBackendContract + apply to InProcess

Contract suite verifies: blocking spawn returns handle, detached spawn
returns handle (then join cleans up), join returns ToolResult, status
shows SUCCEEDED after join, child session linked to parent + tenant
inherited. InProcessMultiAgentBackend passes 5 contract checks plus
its 12 specific tests."
```

---

## Task 11: AgentRuntime threads `multi_agent` into ToolContext

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `src/meta_harney/runtime.py`
- Modify: `tests/unit/test_runtime.py`

The engine's `run_turn` currently constructs `ToolContext` without a `multi_agent` field. To expose multi_agent capability to tools (added in T3), the engine needs to accept and pass it through.

- [ ] **Step 1: Append failing test to `tests/unit/test_runtime.py`**

```python


from typing import ClassVar
from pydantic import BaseModel as _PBM

from meta_harney.abstractions.multi_agent import MultiAgentBackend
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend


class _MultiAgentInput(_PBM):
    pass


class _ProbeMultiAgentTool(BaseTool):
    """Reads ctx.multi_agent and returns whether it was set."""
    name: ClassVar[str] = "probe_multi_agent"
    description: ClassVar[str] = "Reports whether ctx.multi_agent is set."
    input_schema: ClassVar[type[_PBM]] = _MultiAgentInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            success=True,
            output={"multi_agent_present": ctx.multi_agent is not None},
        )


async def test_runtime_threads_multi_agent_into_tool_context() -> None:
    """If AgentRuntime was constructed with multi_agent, tools see it via ctx."""
    from meta_harney.providers.base import ProviderToolCall

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

    # Main runtime: LLM calls the probe tool, then ends turn
    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="i1", name="probe_multi_agent", args={},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="done", stop_reason="end_turn"),
    ])

    rt = AgentRuntime(
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        tools={"probe_multi_agent": _ProbeMultiAgentTool()},
        multi_agent=backend,
    )

    session = await rt.create_session()
    async for ev in rt.stream(session.id, "probe"):
        if hasattr(ev, "result"):
            # ToolCallCompleted
            assert ev.result.success
            assert ev.result.output == {"multi_agent_present": True}


async def test_runtime_without_multi_agent_tool_sees_none() -> None:
    """If AgentRuntime was NOT given multi_agent, ctx.multi_agent is None."""
    from meta_harney.providers.base import ProviderToolCall

    store = MemorySessionStore()
    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="i1", name="probe_multi_agent", args={},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="done", stop_reason="end_turn"),
    ])

    rt = AgentRuntime(
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake"),
        tools={"probe_multi_agent": _ProbeMultiAgentTool()},
        # No multi_agent kwarg
    )

    session = await rt.create_session()
    seen = []
    async for ev in rt.stream(session.id, "probe"):
        if hasattr(ev, "result"):
            seen.append(ev.result.output)
    assert seen == [{"multi_agent_present": False}]
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py::test_runtime_threads_multi_agent_into_tool_context tests/unit/test_runtime.py::test_runtime_without_multi_agent_tool_sees_none -v
```

Expected: First test FAILS (multi_agent is None in ctx because engine doesn't thread it).
Second test PASSES (default None).

- [ ] **Step 3: Modify `src/meta_harney/engine/loop.py` — add `multi_agent` kwarg to `run_turn`**

Find these lines in `loop.py`:

```python
                else:
                    ctx = ToolContext(
                        session_store=session_store,
                        trace_sink=trace_sink,
                        current_span_id=turn_span,
                        new_span_id=new_span_id,
                    )
```

Replace with:

```python
                else:
                    ctx = ToolContext(
                        session_store=session_store,
                        trace_sink=trace_sink,
                        current_span_id=turn_span,
                        new_span_id=new_span_id,
                        multi_agent=multi_agent,
                    )
```

And add `multi_agent: MultiAgentBackend | None = None` to the `run_turn` signature. Also add `from meta_harney.abstractions.multi_agent import MultiAgentBackend` import at top.

The updated `run_turn` signature:

```python
async def run_turn(
    *,
    session_id: str,
    user_message: Message,
    provider: LLMProvider,
    prompt_builder: PromptBuilder,
    permission_resolver: PermissionResolver,
    tools: dict[str, BaseTool],
    hooks: list[BaseHook],
    session_store: SessionStore,
    trace_sink: TraceSink,
    config: RuntimeConfig,
    compaction: CompactionStrategy | None = None,
    token_counter: TokenCounter | None = None,
    multi_agent: MultiAgentBackend | None = None,
) -> AsyncGenerator[StreamEvent, None]:
```

- [ ] **Step 4: Modify `src/meta_harney/runtime.py` — pass `multi_agent` to `run_turn`**

In `AgentRuntime.stream()`, find the call to `_run_turn(...)` and add `multi_agent=self._multi_agent,` as a kwarg.

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime.py -v
pytest -q
ruff check src/meta_harney tests
mypy src/meta_harney
```

Expected: 10 runtime tests pass (8 prior + 2 new); full suite green; clean.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/engine/loop.py src/meta_harney/runtime.py tests/unit/test_runtime.py
git commit -m "feat(engine): run_turn forwards multi_agent into ToolContext

run_turn gains a 'multi_agent' kwarg (default None). When constructing
ToolContext per tool invocation, the engine threads multi_agent
through so tools can call ctx.multi_agent.spawn() to delegate work
to child agents.

AgentRuntime.stream() passes self._multi_agent. Tools that don't need
it just leave ctx.multi_agent as None.

E2E: probe tool reads ctx.multi_agent and reports presence/absence."
```

---

## Task 12: E2E — parent spawns blocking child via tool call

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

- [ ] **Step 1: Append failing test**

```python


from meta_harney.abstractions.multi_agent import AgentSpec
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.runtime import AgentRuntime


class _DelegateInput(BaseModel):
    question: str


class _DelegateTool(BaseTool):
    """Spawns a child agent to handle a sub-question, returns its output."""
    name: ClassVar[str] = "delegate_to_helper"
    description: ClassVar[str] = "Delegate to a helper agent."
    input_schema: ClassVar[type[BaseModel]] = _DelegateInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        if ctx.multi_agent is None:
            return ToolResult(success=False, error="multi-agent not configured")
        spec = AgentSpec(
            name="helper",
            instructions="You are a focused helper agent.",
            allowed_tools=[],
        )
        question = inv.args.get("question", "")
        handle = await ctx.multi_agent.spawn(
            spec=spec,
            initial_message=question,
            parent_session_id=inv.session_id,
            mode="blocking",
        )
        result = await ctx.multi_agent.join(handle.child_session_id)
        return ToolResult(
            success=True,
            output={"child_session_id": handle.child_session_id, "answer": str(result.output)},
        )


async def test_e2e_parent_spawns_blocking_child() -> None:
    """Parent agent calls delegate_to_helper tool → child agent runs → result returns to parent."""
    store = MemorySessionStore()

    # Parent runs 2 LLM rounds: (1) tool call, (2) final synthesis
    parent_provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="i1",
                name="delegate_to_helper",
                args={"question": "what is 2+2?"},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="The helper says 4.", stop_reason="end_turn"),
    ])

    # Child agent: 1 round
    child_provider = FakeLLMProvider(rounds=[
        FakeRound(text="4", stop_reason="end_turn"),
    ])

    backend = InProcessMultiAgentBackend(
        provider=child_provider,
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="child-model"),
        all_tools={},
        hooks=[],
    )

    rt = AgentRuntime(
        provider=parent_provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="parent-model"),
        tools={"delegate_to_helper": _DelegateTool()},
        multi_agent=backend,
    )

    session = await rt.create_session(tenant_id="acme")
    final = await rt.invoke(session.id, "ask the helper")

    assert isinstance(final.content[0], TextBlock)
    assert "helper says 4" in final.content[0].text.lower()

    # Verify a child session exists with parent linkage
    all_sessions = await store.list()
    children = [s for s in all_sessions if s.parent_session_id == session.id]
    assert len(children) == 1
    assert children[0].tenant_id == "acme"  # tenant inherited
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_e2e_parent_spawns_blocking_child -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(multi-agent): e2e — parent spawns blocking child

Parent agent has a delegate_to_helper tool that calls ctx.multi_agent
.spawn(mode='blocking') and join()s the child. Child agent runs in
the same process with its own AgentSpec.instructions (overridden via
_ChildPromptBuilder), no tools, single LLM round. Result flows back
to parent which synthesizes a final response.

Verifies: ctx.multi_agent threading works, child session is created
with parent_session_id link, tenant_id inheritance, end-to-end flow."
```

---

## Task 13: E2E — detached child + status polling

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

- [ ] **Step 1: Append failing test**

```python


async def test_e2e_detached_child_status_then_join() -> None:
    """Parent spawns a detached child, polls status, then joins."""
    from collections.abc import AsyncGenerator
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamDone,
        ProviderStreamEvent,
        ProviderTextDelta,
        ToolSpec,
    )

    class _SlowChildProvider:
        """Sleeps briefly, then emits one text round."""
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            await asyncio.sleep(0.3)
            yield ProviderTextDelta(text="slow child done")
            yield ProviderStreamDone(stop_reason="end_turn")

    store = MemorySessionStore()

    backend = InProcessMultiAgentBackend(
        provider=_SlowChildProvider(),  # type: ignore[arg-type]
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="child"),
        all_tools={},
        hooks=[],
    )

    # Create parent session manually (no parent agent run for this test)
    from datetime import datetime, timezone
    parent_id = "parent-detach-e2e"
    await store.save(Session(id=parent_id, created_at=datetime.now(timezone.utc)))

    spec = AgentSpec(name="bg", instructions="background helper", allowed_tools=[])
    handle = await backend.spawn(
        spec=spec,
        initial_message="run",
        parent_session_id=parent_id,
        mode="detached",
    )

    # Status check immediately after spawn (still running)
    await asyncio.sleep(0.05)
    status = await backend.status(handle.child_session_id)
    assert status == TaskState.RUNNING

    # Join awaits completion
    result = await backend.join(handle.child_session_id)
    assert result.success
    assert "slow child done" in str(result.output)

    # Final status SUCCEEDED
    final_status = await backend.status(handle.child_session_id)
    assert final_status == TaskState.SUCCEEDED
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_e2e_detached_child_status_then_join -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(multi-agent): e2e — detached child + status polling + join

Backend.spawn(mode='detached') returns immediately. status() reports
RUNNING while child sleeps 300 ms in provider stream, then join()
awaits completion. final status() reports SUCCEEDED."
```

---

## Task 14: Public API + final verification

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Run: `pytest`, `mypy`, `ruff check`, `ruff format`

- [ ] **Step 1: Add Phase 3 symbols to `src/meta_harney/__init__.py`**

Read the current file. Add these imports + `__all__` entries (preserve alphabetical order for ruff RUF022):

```python
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.runtime import AgentRuntime
```

Add `"AgentRuntime"` and `"InProcessMultiAgentBackend"` to `__all__` (in alphabetical position).

- [ ] **Step 2: Smoke test the new exports**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
assert mh.AgentRuntime
assert mh.InProcessMultiAgentBackend
print(f'Exports: {len(mh.__all__)}')
print('OK')
"
```

Expected: `OK`, exports up from 47 to 49.

- [ ] **Step 3: Full quality gates**

```bash
source .venv/bin/activate
pytest -v
mypy src/meta_harney
ruff check src/meta_harney tests
ruff format --check src/meta_harney tests
```

Expected: all clean. Test count should be ~210+ (Phase 2 ended at 184; Phase 3 adds ~30 unit tests + 3 E2E + 5 contract = ~38).

- [ ] **Step 4: If any fixes were needed above, commit them**

```bash
git status
```

If modified:
```bash
git add -A
git commit -m "chore: phase 3 final verification

Full test suite green, mypy strict + ruff clean. AgentRuntime and
InProcessMultiAgentBackend exposed at meta_harney top level."
```

If nothing changed, skip the commit.

Otherwise commit just the __init__.py changes:

```bash
git add src/meta_harney/__init__.py
git commit -m "feat: expose AgentRuntime + InProcessMultiAgentBackend at top level

Public API additions for Phase 3:
  - meta_harney.AgentRuntime: top-level facade for running agent turns
  - meta_harney.InProcessMultiAgentBackend: same-process multi-agent backend"
```

---

## Phase 3 Completion Checklist

- [ ] `from meta_harney import AgentRuntime, InProcessMultiAgentBackend` works
- [ ] `pytest -v` reports ≥ 215 tests passing, 0 failures
- [ ] `mypy src/meta_harney` reports 0 errors
- [ ] `ruff check src/meta_harney tests` reports 0 issues
- [ ] `ruff format --check` reports 0 differences
- [ ] AgentRuntime exposes: `create_session`, `invoke`, `stream`
- [ ] InProcessMultiAgentBackend exposes: `spawn` (blocking + detached), `join`, `status`, `cancel`
- [ ] 5 new integration scenarios pass:
  - test_retry_recovers_from_transient_failure
  - test_retry_gives_up_after_max_attempts
  - test_non_retryable_propagates_immediately
  - test_runtime_drives_full_turn_e2e
  - test_e2e_parent_spawns_blocking_child
  - test_e2e_detached_child_status_then_join
- [ ] MultiAgentBackendContract suite applied to InProcessMultiAgentBackend
- [ ] retry_with_backoff wired into engine.run_turn's provider.stream call (Phase 2 carry-over #1 ✓)
- [ ] RuntimeConfig.max_tokens/temperature passed through to ProviderCallConfig (#3 ✓)
- [ ] ToolContext.multi_agent field added (enabler for ctx.multi_agent.spawn() in tools)

**Phase 4 (next plan):**
- Real LLM providers: Anthropic, OpenAI
- ThinkingDelta wiring (Anthropic extended thinking)
- `meta_harney.testing` module (runtime_for_testing helper per spec §8.5)
- Additional E2E scenarios per spec §8.4 (multi-turn-session)
- ToolCallStarted ordering decision

---

## Self-Review

**Spec coverage:**

- §3 Repository Structure: `runtime.py` (Task 4-5), `builtin/multi_agent/` (Tasks 7-9), `testing/` (deferred to Phase 4)
- §4.9 MultiAgentBackend Protocol: `InProcessMultiAgentBackend` implements all 4 methods (Tasks 7-9) + contract test (Task 10)
- §5.1 Engine data flow: unchanged from Phase 2; multi_agent added to ToolContext only (Task 3, 11)
- §5.3 Retry: `retry_with_backoff` now wired (Task 2)
- §6.1 Session lifecycle: `AgentRuntime.create_session` enforces explicit creation + duplicate-id detection (Task 4)
- §7.5 Tool timeout: unchanged from Phase 2

**Carry-over from Phase 2:**
- ✅ retry wiring (Task 2)
- ✅ max_tokens/temperature passthrough (Task 1)
- ✅ ToolContext multi_agent field (Task 3)
- ⏸ ThinkingDelta wiring — deferred (needs Anthropic provider)
- ⏸ ToolCallStarted ordering — deferred (semantic polish, not blocking)

**Placeholder scan:** No "TBD"/"TODO"/"later"/"add appropriate" found.

**Type consistency:**
- `AgentRuntime` constructor kwargs match Phase 1/2 abstraction names exactly (provider, prompt_builder, permission_resolver, session_store, trace_sink, config, tools, hooks, compaction, token_counter, multi_agent)
- `InProcessMultiAgentBackend` constructor mirrors `AgentRuntime` (but uses `all_tools` not `tools` to clarify it filters per AgentSpec.allowed_tools)
- `spawn()` mode literal `"blocking" | "detached"` consistent across Tasks 7, 8, 9, 10
- `RuntimeConfig.retry: RetryConfig` field name consistent with `engine.retry.RetryConfig` class
- `to_provider_call_config()` method name consistent across Task 1 (definition) and Task 2 (usage)
