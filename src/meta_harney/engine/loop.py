"""Engine main loop: run_turn() orchestrator."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from meta_harney.abstractions._types import (
    ContentBlock,
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.multi_agent import MultiAgentBackend
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
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.engine.tool_dispatch import (
    _execute_after_permission,
    check_permission_for_tool,
)
from meta_harney.engine.tracing import emit_event, new_span_id
from meta_harney.errors import SessionNotFoundError
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderRedactedThinking,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingBlock,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
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
    tool_specs: list[ToolSpec],
    call_config: ProviderCallConfig,
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
    multi_agent: MultiAgentBackend | None = None,
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

        # Fire session_start hook
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

            # Fire pre_llm hook
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

            async def _call_provider(
                _msgs: list[Message] = stream_messages,
                _sp: str = system_prompt,
                _specs: list[ToolSpec] = tool_specs,
                _cfg: ProviderCallConfig = call_config,
            ) -> list[ProviderStreamEvent]:
                return await _collect_provider_stream(
                    provider,
                    _msgs,
                    _sp,
                    _specs,
                    _cfg,
                )

            provider_events = await retry_with_backoff(_call_provider, config.retry)

            text_chunks: list[str] = []
            tool_calls: list[ProviderToolCall] = []
            thinking_blocks_buf: list[ThinkingBlock | RedactedThinkingBlock] = []
            stop_reason = "end_turn"

            for ev in provider_events:
                if isinstance(ev, ProviderTextDelta):
                    text_chunks.append(ev.text)
                    yield TextDelta(text=ev.text)
                elif isinstance(ev, ProviderThinkingDelta):
                    # Passthrough: stream the thinking to the consumer, but do
                    # NOT append to text_chunks or assistant_blocks, and do not
                    # persist to session.messages.
                    yield ThinkingDelta(text=ev.text)
                elif isinstance(ev, ProviderThinkingBlock):
                    thinking_blocks_buf.append(ThinkingBlock(text=ev.text, signature=ev.signature))
                elif isinstance(ev, ProviderRedactedThinking):
                    thinking_blocks_buf.append(RedactedThinkingBlock(data=ev.data))
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
            for tblk in thinking_blocks_buf:
                assistant_blocks.append(tblk)
            if text_chunks:
                assistant_blocks.append(TextBlock(text="".join(text_chunks)))
            for tc in tool_calls:
                assistant_blocks.append(
                    ToolCallBlock(
                        invocation_id=tc.invocation_id,
                        name=tc.name,
                        args=tc.args,
                    )
                )
            session.messages.append(Message(role="assistant", content=assistant_blocks))

            # Fire post_llm hook
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

            # No tool calls? we're done
            if not tool_calls:
                stop = True
                yield IterationCompleted(iteration=iteration)
                iteration += 1
                break

            # Dispatch each tool call (pre_tool / post_tool fire inside _execute_after_permission)
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
                    # Tool not registered — no permission check, no ToolCallStarted
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

                tool_result_blocks.append(
                    ToolResultBlock(
                        invocation_id=inv.invocation_id,
                        success=result.success,
                        output=result.output,
                        error=result.error,
                    )
                )
                yield ToolCallCompleted(
                    tool_name=tc.name,
                    invocation_id=tc.invocation_id,
                    result=result,
                )

            session.messages.append(Message(role="tool", content=tool_result_blocks))

            # Tools may have independently persisted the session via
            # `ctx.session_store.save(...)` — e.g. todo_write writes
            # `session.attributes["todos"]`. That bumps the on-disk version
            # without touching our in-memory copy, so our final save at
            # end-of-turn would conflict. Reload from disk and pick up the
            # tool's `attributes` + the new `version`, while keeping the
            # engine's authoritative message history.
            fresh = await session_store.load(session_id)
            if fresh is not None and fresh.version > session.version:
                session.attributes = fresh.attributes
                session.version = fresh.version

            yield IterationCompleted(iteration=iteration)
            iteration += 1

            # Compaction check after each tool iteration
            if compaction is not None and config.compaction_trigger_tokens is not None:
                current_tokens = counter(session.messages)
                if current_tokens > config.compaction_trigger_tokens:
                    should = await compaction.should_compact(
                        session_id, current_tokens, config.context_window_tokens
                    )
                    if should:
                        before_n = len(session.messages)
                        before_tokens = current_tokens
                        # Persist current state so compactor can re-load it
                        await session_store.save(session)
                        # Re-load to refresh version after save
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
                            # Per spec §7.2: CompactionError fail-open, continue loop
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

        # Fire turn_complete hook
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

        # Fire session_end hook
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
    """Convert 'tool name not registered' into a ToolResult fed to the LLM."""
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
