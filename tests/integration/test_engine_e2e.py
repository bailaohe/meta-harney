"""End-to-end engine tests using FakeLLMProvider."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import run_turn
from meta_harney.engine.stream_events import (
    StreamEvent,
    TextDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound, ProviderToolCall


async def _new_session(store: MemorySessionStore, session_id: str = "s1") -> Session:
    s = Session(id=session_id, created_at=datetime.now(timezone.utc))
    await store.save(s)
    return s


async def test_happy_path_text_only() -> None:
    """One user message → one LLM response, no tools."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(text="Hello!", stop_reason="end_turn"),
    ])

    builder = MinimalPromptBuilder(session_store=store)

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,
        prompt_builder=builder,
        permission_resolver=AllowAllPermissionResolver(),
        tools={},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake-model"),
    ):
        events.append(ev)

    # Last event is TurnCompleted
    assert isinstance(events[-1], TurnCompleted)
    # At least one TextDelta
    assert any(isinstance(e, TextDelta) and e.text == "Hello!" for e in events)

    # Session updated: user msg + assistant msg
    loaded = await store.load("s1")
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"
    text_block = loaded.messages[1].content[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "Hello!"


class _EchoInput(BaseModel):
    text: str = ""


class _EchoTool(BaseTool):
    name: ClassVar[str] = "echo"
    description: ClassVar[str] = "Echoes text."
    input_schema: ClassVar[type[BaseModel]] = _EchoInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output={"echoed": inv.args.get("text", "")})


async def test_tool_call_cycle() -> None:
    """LLM emits tool call → tool runs → LLM sees result → final text response."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="inv-1",
                name="echo",
                args={"text": "world"},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="The echo said 'world'.", stop_reason="end_turn"),
    ])

    builder = MinimalPromptBuilder(session_store=store)

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="echo world")]),
        provider=provider,
        prompt_builder=builder,
        permission_resolver=AllowAllPermissionResolver(),
        tools={"echo": _EchoTool()},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake-model"),
    ):
        events.append(ev)

    # We expect tool started + completed events
    started = [e for e in events if isinstance(e, ToolCallStarted)]
    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert len(started) == 1
    assert started[0].tool_name == "echo"
    assert len(completed) == 1
    assert completed[0].result.success

    # Final message text from round 2
    text_events = [e for e in events if isinstance(e, TextDelta)]
    assert any("echo said 'world'" in e.text for e in text_events)

    # Session has 4 messages: user, assistant(tool_call), tool_result, assistant(final)
    loaded = await store.load("s1")
    assert loaded is not None
    assert len(loaded.messages) == 4
    assert loaded.messages[-1].role == "assistant"

    # Provider was called twice (initial + post-tool)
    assert len(provider.calls) == 2
