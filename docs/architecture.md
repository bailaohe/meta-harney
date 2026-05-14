# meta-harney Architecture

> System-level overview of how the runtime composes abstractions, providers,
> and the agent loop to drive multi-turn conversations.

## High-level diagram

```
                                  AgentRuntime (facade)
                                          │
                       ┌──────────────────┼──────────────────┐
                       │                  │                  │
              SessionStore        engine.run_turn       MultiAgentBackend
              (persistence)       (the agent loop)        (child agents)
                                          │
        ┌─────────────┬────────────┬──────┴──────┬─────────────┬────────────┐
        │             │            │             │             │            │
   PromptBuilder  LLMProvider  Hook chain   PermissionResolver Tools     TraceSink
   (sys+context)  (Anthropic/  (7 events)   (allow/deny/ask)  (BaseTool) (events)
                   OpenAI/...)
```

## Agent turn lifecycle

A single `runtime.invoke(session_id, "...")` call runs one **turn**:

1. **Load session** from `SessionStore`
2. **Append user message** to session history
3. Fire `session_start` hook
4. **Iterate** (bounded by `config.max_iterations`):
   1. Build system prompt + load context messages via `PromptBuilder`
   2. Fire `pre_llm` hook (can transform/halt)
   3. Call `LLMProvider.stream()` (wrapped in retry on transient errors)
   4. Collect assistant text + tool call requests
   5. Append assistant message
   6. Fire `post_llm` hook
   7. If no tool calls: break
   8. For each tool call:
      - `PermissionResolver.resolve()` (skip if deny → ToolResult error)
      - Yield `ToolCallStarted` (only if permission cleared)
      - Fire `pre_tool` hook (can transform args)
      - `BaseTool.execute()` (bounded by per-tool timeout)
      - Fire `post_tool` hook
      - Yield `ToolCallCompleted`
   9. Append tool-result message
   10. Compaction check (if `CompactionStrategy` enabled)
5. Fire `turn_complete`, `session_end` hooks
6. **Save session** to `SessionStore`
7. Yield `TurnCompleted`

## Two event streams

The runtime emits **two distinct streams** of events:

| Stream | Consumer | Purpose | Path |
|---|---|---|---|
| `StreamEvent` (text_delta, tool_call_*, turn_completed) | App code, UI | "What is the agent saying/doing?" | `runtime.stream()` |
| `TraceEvent` (turn.started, llm.completed, hook.fired, etc.) | Observability | "What is the engine doing internally?" | `TraceSink.emit()` |

Keep them separate: business code subscribes to `StreamEvent`; operators
subscribe to `TraceEvent` via the configured `TraceSink`.

## Error handling

- **Provider errors** (rate limit, 5xx) — `LLMProvider` raises
  `RetryableProviderError`; engine retries via exponential backoff (configured
  by `RuntimeConfig.retry`). After `max_attempts`, propagates.
- **Tool exceptions** — caught inside the dispatcher; converted to
  `ToolResult(success=False, error=str(exc))` and fed back to the LLM. Loop
  continues.
- **Permission deny** — converted to `ToolResult(success=False)`, no
  `ToolCallStarted` emitted, `tool.denied` trace fired.
- **Hook halt** — `HookHaltError` from any hook propagates out of `invoke`.
- **Cancellation** — `asyncio.CancelledError` triggers `finally` block that
  saves the half-baked session and flushes the trace sink.

## Multi-agent

`InProcessMultiAgentBackend.spawn()` creates a child `Session` linked to the
parent (`parent_session_id`, `tenant_id`, `user_id` inherited) and runs
`engine.run_turn` with a `_ChildPromptBuilder` that overrides the system prompt
with `AgentSpec.instructions`. Tools available to the child are filtered to
`spec.allowed_tools`.

- **Blocking mode** — `spawn()` awaits the child to completion, caches result
  in `_results[child_session_id]`.
- **Detached mode** — `spawn()` creates an `asyncio.Task`, returns immediately.
  Use `join(child_session_id, timeout=...)` to await; `status()` to poll;
  `cancel()` to interrupt.

Child agents access their backend through `ToolContext.multi_agent` — a tool
can `await ctx.multi_agent.spawn(...)` to delegate sub-questions.

## Dependency layering

```
abstractions/    ← no dependencies on engine/, builtin/, providers/
builtin/         ← depends on abstractions/
engine/          ← depends on abstractions/, providers/ (LLMProvider Protocol)
providers/       ← depends on abstractions/
runtime.py       ← depends on all the above
testing/         ← depends on runtime, providers/fake
```

This means **business code can write a custom tool, hook, or session store**
using only the `abstractions/` namespace — no need to import the engine.
