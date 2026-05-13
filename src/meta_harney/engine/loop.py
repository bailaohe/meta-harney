"""Engine main loop: run_turn() orchestrator."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from meta_harney.abstractions._types import (
    ContentBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
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
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderTextDelta,
    ProviderToolCall,
)


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
) -> AsyncGenerator[StreamEvent, None]:
    turn_span = new_span_id()

    session = await session_store.load(session_id)
    if session is None:
        raise SessionNotFoundError(f"session {session_id!r} not found")

    session.messages.append(user_message)

    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="turn.started",
        span_id=turn_span,
        parent_span_id=None,
        payload={"user_message_role": user_message.role},
    )

    tool_specs = [tool_to_spec(t) for t in tools.values()]
    iteration = 0
    stop = False

    while not stop and iteration < config.max_iterations:
        # Build prompt
        system_prompt = await prompt_builder.build_system_prompt(session_id)
        await emit_event(
            trace_sink,
            session_id=session_id,
            kind="prompt.built",
            span_id=new_span_id(),
            parent_span_id=turn_span,
            payload={"n_messages": len(session.messages), "iteration": iteration},
        )

        # Call LLM
        llm_span = new_span_id()
        await emit_event(
            trace_sink,
            session_id=session_id,
            kind="llm.requested",
            span_id=llm_span,
            parent_span_id=turn_span,
            payload={"model": config.model, "iteration": iteration},
        )

        text_chunks: list[str] = []
        tool_calls: list[ProviderToolCall] = []

        async for ev in provider.stream(
            messages=list(session.messages),
            system_prompt=system_prompt,
            tools=tool_specs,
            config=ProviderCallConfig(model=config.model),
        ):
            if isinstance(ev, ProviderTextDelta):
                text_chunks.append(ev.text)
                yield TextDelta(text=ev.text)
            elif isinstance(ev, ProviderToolCall):
                tool_calls.append(ev)
            elif isinstance(ev, ProviderStreamDone):
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
                break

        # Assemble assistant message
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

        # No tool calls? we're done
        if not tool_calls:
            stop = True
            yield IterationCompleted(iteration=iteration)
            iteration += 1
            break

        # Dispatch each tool call
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

    await session_store.save(session)

    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="turn.completed",
        span_id=new_span_id(),
        parent_span_id=turn_span,
        payload={"total_iterations": iteration},
    )
    await trace_sink.flush()

    yield TurnCompleted(total_iterations=iteration)


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
