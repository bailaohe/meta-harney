"""Engine main loop: run_turn() orchestrator.

Phase 2 build-up:
  Task 9 (this one): minimal — one LLM call, no tools/hooks
  Task 10: + tool dispatch
  Task 11: + permission integration (via tool_dispatch)
  Task 12: + 7-event hook firing
  Task 13: + tool timeout (via tool_dispatch)
  Task 14: + compaction trigger
  Task 15: + cancellation-safe finally save
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from meta_harney.abstractions._types import ContentBlock, Message, TextBlock
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.stream_events import (
    StreamEvent,
    TextDelta,
    TurnCompleted,
)
from meta_harney.engine.tracing import emit_event, new_span_id
from meta_harney.errors import SessionNotFoundError
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderTextDelta,
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
    """Run one user→assistant turn. Yields StreamEvents; saves session at end."""
    turn_span = new_span_id()

    # Load session
    session = await session_store.load(session_id)
    if session is None:
        raise SessionNotFoundError(f"session {session_id!r} not found")

    # Append the user message
    session.messages.append(user_message)

    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="turn.started",
        span_id=turn_span,
        parent_span_id=None,
        payload={"user_message_role": user_message.role},
    )

    # Build prompt for the LLM
    system_prompt = await prompt_builder.build_system_prompt(session_id)
    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="prompt.built",
        span_id=new_span_id(),
        parent_span_id=turn_span,
        payload={"n_messages": len(session.messages)},
    )

    # Stream the LLM response
    llm_span = new_span_id()
    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="llm.requested",
        span_id=llm_span,
        parent_span_id=turn_span,
        payload={"model": config.model},
    )

    text_chunks: list[str] = []
    async for ev in provider.stream(
        messages=list(session.messages),
        system_prompt=system_prompt,
        tools=[],  # no tools in minimal version
        config=ProviderCallConfig(model=config.model),
    ):
        if isinstance(ev, ProviderTextDelta):
            text_chunks.append(ev.text)
            yield TextDelta(text=ev.text)
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
        # ProviderToolCall ignored in minimal version (tools = {} anyway)

    # Build assistant message from accumulated text
    assistant_blocks: list[ContentBlock] = []
    if text_chunks:
        assistant_blocks.append(TextBlock(text="".join(text_chunks)))
    assistant_msg = Message(role="assistant", content=assistant_blocks)
    session.messages.append(assistant_msg)

    # Save session
    await session_store.save(session)

    await emit_event(
        trace_sink,
        session_id=session_id,
        kind="turn.completed",
        span_id=new_span_id(),
        parent_span_id=turn_span,
        payload={"total_iterations": 1},
    )
    await trace_sink.flush()

    yield TurnCompleted(total_iterations=1)
