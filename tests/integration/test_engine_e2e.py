"""End-to-end engine tests using FakeLLMProvider."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import BaseModel

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.abstractions.session import Session
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.compaction.summarization import SummarizationCompactor
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
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
from meta_harney.errors import HookHaltError
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


async def test_permission_denied_e2e() -> None:
    """LLM requests a tool, permission resolver denies, LLM sees the denial."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="inv-1",
                name="echo",
                args={"text": "blocked"},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="Sorry, I'm not allowed.", stop_reason="end_turn"),
    ])

    builder = MinimalPromptBuilder(session_store=store)

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="echo something")]),
        provider=provider,
        prompt_builder=builder,
        permission_resolver=DenyAllPermissionResolver(),
        tools={"echo": _EchoTool()},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="fake-model"),
    ):
        events.append(ev)

    # ToolCallCompleted indicates failure
    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert len(completed) == 1
    assert not completed[0].result.success
    assert "deny" in (completed[0].result.error or "").lower()

    # LLM was asked twice (initial + recovery)
    assert len(provider.calls) == 2

    # Session shows the deny propagated as tool result
    loaded = await store.load("s1")
    assert loaded is not None
    assistant_msgs = [m for m in loaded.messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1
    last_assistant_text = assistant_msgs[-1].content[0]
    assert isinstance(last_assistant_text, TextBlock)
    assert "not allowed" in last_assistant_text.text


class _RecordingHook(BaseHook):
    """Records every event it sees, in order."""

    def __init__(self, kinds: set[HookEventKind]) -> None:
        # Override ClassVar per-instance for test recording purposes.
        self.subscribed_events = kinds  # type: ignore[assignment]
        self.received: list[HookEvent] = []

    async def handle(self, event: HookEvent) -> HookDecision:
        self.received.append(event)
        return HookDecision(allow=True)


async def test_hook_firing_all_kinds() -> None:
    """Verify engine fires all 7 hook events during a turn with a tool call."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(
                invocation_id="i1", name="echo", args={"text": "hi"},
            )],
            stop_reason="tool_use",
        ),
        FakeRound(text="done", stop_reason="end_turn"),
    ])

    recorder = _RecordingHook({
        "session_start", "session_end",
        "pre_llm", "post_llm",
        "pre_tool", "post_tool",
        "turn_complete",
    })

    async for _ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        tools={"echo": _EchoTool()},
        hooks=[recorder],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="x"),
    ):
        pass

    kinds_seen = [e.kind for e in recorder.received]
    # session_start fires once at turn entry
    assert "session_start" in kinds_seen
    # pre_llm fires per iteration (2 here)
    assert kinds_seen.count("pre_llm") == 2
    assert kinds_seen.count("post_llm") == 2
    # pre_tool/post_tool fire once each (1 tool call)
    assert kinds_seen.count("pre_tool") == 1
    assert kinds_seen.count("post_tool") == 1
    # turn_complete + session_end fire once at exit
    assert "turn_complete" in kinds_seen
    assert "session_end" in kinds_seen


async def test_hook_halt_terminates_turn() -> None:
    """Hook raising HookHaltError stops the engine and propagates."""
    store = MemorySessionStore()
    await _new_session(store)

    class _HaltOnPreLlm(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"pre_llm"}

        async def handle(self, event: HookEvent) -> HookDecision:
            raise HookHaltError(reason="manual stop")

    provider = FakeLLMProvider(rounds=[FakeRound(text="never", stop_reason="end_turn")])

    with pytest.raises(HookHaltError, match="manual stop"):
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=provider,
            prompt_builder=MinimalPromptBuilder(session_store=store),
            permission_resolver=AllowAllPermissionResolver(),
            tools={},
            hooks=[_HaltOnPreLlm()],
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(model="x"),
        ):
            pass


class _SlowTool(BaseTool):
    name: ClassVar[str] = "slow"
    description: ClassVar[str] = "Sleeps too long."
    input_schema: ClassVar[type[BaseModel]] = _EchoInput
    default_timeout: ClassVar[float | None] = 0.05  # 50ms

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(1.0)
        return ToolResult(success=True, output="never")


async def test_tool_timeout_e2e() -> None:
    """Slow tool times out, LLM sees error, gives final answer."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(invocation_id="i1", name="slow", args={})],
            stop_reason="tool_use",
        ),
        FakeRound(text="Tool timed out.", stop_reason="end_turn"),
    ])

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="run slow")]),
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        tools={"slow": _SlowTool()},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="x"),
    ):
        events.append(ev)

    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert len(completed) == 1
    assert not completed[0].result.success
    assert "timed out" in (completed[0].result.error or "").lower()

    text_events = [e for e in events if isinstance(e, TextDelta)]
    assert any("timed out" in e.text.lower() for e in text_events)


async def _fake_summarize(messages: list[Message]) -> str:
    return f"summary-of-{len(messages)}"


async def test_compaction_triggered_e2e() -> None:
    """After a tool round, engine triggers compaction; session.messages shrinks."""
    store = MemorySessionStore()
    await _new_session(store)
    # Pre-populate session with many messages to make compaction trigger
    pre_session = await store.load("s1")
    assert pre_session is not None
    for i in range(25):
        pre_session.messages.append(
            Message(role="user", content=[TextBlock(text=f"old-{i}")])
        )
        pre_session.messages.append(
            Message(role="assistant", content=[TextBlock(text=f"reply-{i}")])
        )
    await store.save(pre_session)

    provider = FakeLLMProvider(rounds=[
        FakeRound(
            tool_calls=[ProviderToolCall(invocation_id="i1", name="echo", args={"text": "x"})],
            stop_reason="tool_use",
        ),
        FakeRound(text="done", stop_reason="end_turn"),
    ])

    # Mock token counter: each message contributes 1000 tokens
    def counter(msgs: list[Message]) -> int:
        return len(msgs) * 1000

    compactor = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        keep_recent=5,
    )

    async for _ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="now")]),
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        tools={"echo": _EchoTool()},
        hooks=[],
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(
            model="x",
            context_window_tokens=10_000,
            compaction_trigger_tokens=5000,
        ),
        compaction=compactor,
        token_counter=counter,
    ):
        pass

    loaded = await store.load("s1")
    assert loaded is not None
    # After compaction: many fewer messages
    assert len(loaded.messages) < 20
    # A summary message exists
    has_summary = any(
        m.role == "system"
        and m.content
        and isinstance(m.content[0], TextBlock)
        and "summary-of" in m.content[0].text
        for m in loaded.messages
    )
    assert has_summary


async def test_cancellation_preserves_session() -> None:
    """If caller cancels mid-turn, session is saved with partial state."""
    from collections.abc import AsyncGenerator

    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamEvent,
        ToolSpec,
    )

    store = MemorySessionStore()
    await _new_session(store)

    class _BlockingProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncGenerator[ProviderStreamEvent, None]:
            await asyncio.sleep(10.0)  # will be cancelled
            # unreachable yield to make it a generator
            if False:
                yield  # type: ignore[unreachable]

    async def runner() -> None:
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=_BlockingProvider(),  # type: ignore[arg-type]
            prompt_builder=MinimalPromptBuilder(session_store=store),
            permission_resolver=AllowAllPermissionResolver(),
            tools={},
            hooks=[],
            session_store=store,
            trace_sink=NullSink(),
            config=RuntimeConfig(model="x"),
        ):
            pass

    task = asyncio.create_task(runner())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Session should be saved with user message (half-baked turn)
    loaded = await store.load("s1")
    assert loaded is not None
    user_msgs = [m for m in loaded.messages if m.role == "user"]
    assert len(user_msgs) >= 1
    last_user = user_msgs[-1].content[0]
    assert isinstance(last_user, TextBlock)
    assert last_user.text == "hi"
