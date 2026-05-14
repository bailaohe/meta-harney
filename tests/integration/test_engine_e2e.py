"""End-to-end engine tests using FakeLLMProvider."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import BaseModel

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.abstractions.multi_agent import AgentSpec as _AgentSpec
from meta_harney.abstractions.session import Session
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.compaction.summarization import SummarizationCompactor
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import run_turn
from meta_harney.engine.retry import RetryConfig as _RetryConfig
from meta_harney.engine.stream_events import (
    StreamEvent,
    TextDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.errors import HookHaltError, NonRetryableProviderError, RetryableProviderError
from meta_harney.providers.base import (
    ProviderCallConfig as _PCC,
)
from meta_harney.providers.base import (
    ProviderStreamDone,
    ProviderTextDelta,
    ProviderToolCall,
)
from meta_harney.providers.base import (
    ProviderStreamEvent as _PSE,
)
from meta_harney.providers.base import (
    ToolSpec as _TS,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound
from meta_harney.runtime import AgentRuntime


async def _new_session(store: MemorySessionStore, session_id: str = "s1") -> Session:
    s = Session(id=session_id, created_at=datetime.now(timezone.utc))
    await store.save(s)
    return s


async def test_happy_path_text_only() -> None:
    """One user message → one LLM response, no tools."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="Hello!", stop_reason="end_turn"),
        ]
    )

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

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="inv-1",
                        name="echo",
                        args={"text": "world"},
                    )
                ],
                stop_reason="tool_use",
            ),
            FakeRound(text="The echo said 'world'.", stop_reason="end_turn"),
        ]
    )

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

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="inv-1",
                        name="echo",
                        args={"text": "blocked"},
                    )
                ],
                stop_reason="tool_use",
            ),
            FakeRound(text="Sorry, I'm not allowed.", stop_reason="end_turn"),
        ]
    )

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

    # ToolCallStarted should NOT have been emitted (permission denied before exec)
    started = [e for e in events if isinstance(e, ToolCallStarted)]
    assert len(started) == 0

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
        self.subscribed_events = kinds  # type: ignore[misc]
        self.received: list[HookEvent] = []

    async def handle(self, event: HookEvent) -> HookDecision:
        self.received.append(event)
        return HookDecision(allow=True)


async def test_hook_firing_all_kinds() -> None:
    """Verify engine fires all 7 hook events during a turn with a tool call."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="i1",
                        name="echo",
                        args={"text": "hi"},
                    )
                ],
                stop_reason="tool_use",
            ),
            FakeRound(text="done", stop_reason="end_turn"),
        ]
    )

    recorder = _RecordingHook(
        {
            "session_start",
            "session_end",
            "pre_llm",
            "post_llm",
            "pre_tool",
            "post_tool",
            "turn_complete",
        }
    )

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

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[ProviderToolCall(invocation_id="i1", name="slow", args={})],
                stop_reason="tool_use",
            ),
            FakeRound(text="Tool timed out.", stop_reason="end_turn"),
        ]
    )

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
        pre_session.messages.append(Message(role="user", content=[TextBlock(text=f"old-{i}")]))
        pre_session.messages.append(
            Message(role="assistant", content=[TextBlock(text=f"reply-{i}")])
        )
    await store.save(pre_session)

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[ProviderToolCall(invocation_id="i1", name="echo", args={"text": "x"})],
                stop_reason="tool_use",
            ),
            FakeRound(text="done", stop_reason="end_turn"),
        ]
    )

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
            # unreachable yield to make this an async generator
            if False:
                yield

    async def runner() -> None:
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=_BlockingProvider(),
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


class _BrokenSink:
    """Sink that raises on every emit/flush — verifies engine isolation."""

    def __init__(self) -> None:
        self.emit_calls = 0
        self.flush_calls = 0

    async def emit(self, event: object) -> None:
        self.emit_calls += 1
        raise RuntimeError(f"broken sink emit #{self.emit_calls}")

    async def flush(self) -> None:
        self.flush_calls += 1
        raise RuntimeError("broken sink flush")


async def test_trace_sink_failure_does_not_break_turn() -> None:
    """Per spec §7.2 rule 2: observability MUST NOT kill business.

    A TraceSink that raises on every call must not affect the engine's
    ability to complete a turn end-to-end.
    """
    store = MemorySessionStore()
    await _new_session(store)

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="ok despite broken sink", stop_reason="end_turn"),
        ]
    )

    broken_sink = _BrokenSink()

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        tools={},
        hooks=[],
        session_store=store,
        trace_sink=broken_sink,
        config=RuntimeConfig(model="x"),
    ):
        events.append(ev)

    # Turn completed normally despite many trace failures
    assert any(isinstance(e, TurnCompleted) for e in events)
    text_events = [e for e in events if isinstance(e, TextDelta)]
    assert any("ok despite broken sink" in e.text for e in text_events)

    # Session was saved (the user message survived)
    loaded = await store.load("s1")
    assert loaded is not None
    assert len(loaded.messages) == 2

    # Sink was called multiple times (every emit call attempt was rejected)
    assert broken_sink.emit_calls >= 5


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
        config: _PCC,
    ) -> AsyncGenerator[_PSE, None]:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RetryableProviderError(f"transient #{self.attempts}")
        yield ProviderTextDelta(text=self.succeed_text)
        yield ProviderStreamDone(stop_reason="end_turn")


async def test_retry_recovers_from_transient_failure() -> None:
    """RetryableProviderError raised by provider.stream is retried per config.retry."""
    store = MemorySessionStore()
    await _new_session(store)

    provider = _FlakyProvider(fail_count=2, succeed_text="success on attempt 3")

    events: list[StreamEvent] = []
    async for ev in run_turn(
        session_id="s1",
        user_message=Message(role="user", content=[TextBlock(text="hi")]),
        provider=provider,
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
            provider=provider,
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
            config: _PCC,
        ) -> AsyncGenerator[_PSE, None]:
            self.attempts += 1
            raise NonRetryableProviderError("auth failed")
            yield  # unreachable — needed to make this an async generator

    store = MemorySessionStore()
    await _new_session(store)
    provider = _AuthFailProvider()

    with pytest.raises(NonRetryableProviderError):
        async for _ev in run_turn(
            session_id="s1",
            user_message=Message(role="user", content=[TextBlock(text="hi")]),
            provider=provider,
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


async def test_runtime_drives_full_turn_e2e() -> None:
    """AgentRuntime composes services and drives a multi-message conversation."""
    store = MemorySessionStore()
    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="i1",
                        name="echo",
                        args={"text": "world"},
                    )
                ],
                stop_reason="tool_use",
            ),
            FakeRound(text="Got it.", stop_reason="end_turn"),
        ]
    )

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
        spec = _AgentSpec(
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
    """Parent agent calls delegate_to_helper tool → child agent runs → result returns."""
    store = MemorySessionStore()

    parent_provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="i1",
                        name="delegate_to_helper",
                        args={"question": "what is 2+2?"},
                    )
                ],
                stop_reason="tool_use",
            ),
            FakeRound(text="The helper says 4.", stop_reason="end_turn"),
        ]
    )

    child_provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="4", stop_reason="end_turn"),
        ]
    )

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


async def test_e2e_detached_child_status_then_join() -> None:
    """Parent spawns a detached child, polls status, then joins."""

    class _SlowChildProvider:
        """Sleeps briefly, then emits one text round."""

        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[_TS],
            config: _PCC,
        ) -> AsyncGenerator[_PSE, None]:
            await asyncio.sleep(0.3)
            yield ProviderTextDelta(text="slow child done")
            yield ProviderStreamDone(stop_reason="end_turn")

    store = MemorySessionStore()

    backend = InProcessMultiAgentBackend(
        provider=_SlowChildProvider(),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="child"),
        all_tools={},
        hooks=[],
    )

    parent_id = "parent-detach-e2e"
    await store.save(Session(id=parent_id, created_at=datetime.now(timezone.utc)))

    spec = _AgentSpec(name="bg", instructions="background helper", allowed_tools=[])
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


async def test_thinking_delta_passthrough_and_not_in_history() -> None:
    """ThinkingDelta flows from provider → runtime stream; never enters session.messages."""
    from meta_harney.engine.stream_events import ThinkingDelta
    from meta_harney.testing import FakeRound, runtime_for_testing

    rt = runtime_for_testing(
        scripted_rounds=[
            FakeRound(
                thinking="reasoning step 1",
                text="Final answer.",
                stop_reason="end_turn",
            ),
        ],
    )
    session = await rt.create_session()

    thinking_events: list[ThinkingDelta] = []
    async for ev in rt.stream(session.id, "What's 2+2?"):
        if isinstance(ev, ThinkingDelta):
            thinking_events.append(ev)

    # Stream consumer saw the ThinkingDelta
    assert len(thinking_events) == 1
    assert thinking_events[0].text == "reasoning step 1"

    # But session.messages does NOT contain "reasoning step 1" anywhere
    refreshed = await rt._session_store.load(session.id)
    assert refreshed is not None
    for msg in refreshed.messages:
        for block in msg.content:
            text = getattr(block, "text", "")
            assert "reasoning step 1" not in text, (
                f"thinking leaked into message {msg.role}: {text!r}"
            )

    # The assistant message should still contain "Final answer."
    assistant_msgs = [m for m in refreshed.messages if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert "Final answer." in assistant_msgs[0].content[0].text  # type: ignore[union-attr]


async def test_tool_error_recovery_e2e() -> None:
    """Tool exception → ToolResult(success=False) → LLM recovers in next round.

    Spec §8.4 #2: agent calls a tool that raises; engine catches and feeds
    error back to LLM; LLM apologizes / gives a recovery response.
    """
    from meta_harney.testing import FakeRound, runtime_for_testing

    class _QueryInput(BaseModel):
        q: str

    class FlakyDBTool(BaseTool):
        name: ClassVar[str] = "query_db"
        description: ClassVar[str] = "Query the database."
        input_schema: ClassVar[type[BaseModel]] = _QueryInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            raise RuntimeError("DB unreachable")

    rt = runtime_for_testing(
        scripted_rounds=[
            # Round 1: assistant calls the tool
            FakeRound(
                tool_calls=[
                    ProviderToolCall(
                        invocation_id="t1",
                        name="query_db",
                        args={"q": "SELECT 1"},
                    ),
                ],
                stop_reason="tool_use",
            ),
            # Round 2: assistant sees the error and recovers
            FakeRound(
                text="DB connection failed, please retry later.",
                stop_reason="end_turn",
            ),
        ],
        tools={"query_db": FlakyDBTool()},
    )

    session = await rt.create_session()
    final = await rt.invoke(session.id, "Run SELECT 1")

    # Assistant's final message contains the recovery text
    assert "retry later" in final.content[0].text  # type: ignore[union-attr]

    # session.messages role sequence: user, assistant(tool_call), tool(error), assistant(recovery)
    refreshed = await rt._session_store.load(session.id)
    assert refreshed is not None
    roles = [m.role for m in refreshed.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]

    # The tool result block records the error
    tool_msg = refreshed.messages[2]
    tool_block = tool_msg.content[0]
    assert getattr(tool_block, "success", True) is False
    assert "DB unreachable" in (getattr(tool_block, "error", "") or "")


async def test_multi_turn_session_e2e() -> None:
    """Two consecutive invoke() calls share history (spec §8.4 #4).

    - Turn 1: user asks Q1, assistant answers A1
    - Turn 2: user asks Q2; provider sees [Q1, A1, Q2] as messages
    - Final session.messages = [user(Q1), assistant(A1), user(Q2), assistant(A2)]
    """
    from meta_harney.testing import runtime_for_testing

    rounds = [
        FakeRound(text="4", stop_reason="end_turn"),
        FakeRound(text="8", stop_reason="end_turn"),
    ]
    provider = FakeLLMProvider(rounds=rounds)

    # Build the runtime via the test factory, then swap in our hand-built provider
    # so we can inspect provider.calls after the turns
    rt = runtime_for_testing(scripted_rounds=rounds)
    rt._provider = provider

    session = await rt.create_session()

    final1 = await rt.invoke(session.id, "What's 2+2?")
    assert "4" in final1.content[0].text  # type: ignore[union-attr]

    final2 = await rt.invoke(session.id, "And then double it?")
    assert "8" in final2.content[0].text  # type: ignore[union-attr]

    # Final session state has the full history
    refreshed = await rt._session_store.load(session.id)
    assert refreshed is not None
    roles = [m.role for m in refreshed.messages]
    assert roles == ["user", "assistant", "user", "assistant"]

    # Provider's second call saw the first turn's user+assistant in messages
    assert len(provider.calls) == 2
    second_call_roles = [m.role for m in provider.calls[1].messages]
    # Second call's messages must include Q1 and A1
    assert "user" in second_call_roles
    assert "assistant" in second_call_roles
    # And the second turn's user message ("And then double it?") is also there
    assert second_call_roles.count("user") >= 2


async def test_thinking_plus_tool_use_multi_turn_persistence_e2e() -> None:
    """End-to-end: thinking_blocks persist to session.messages and get
    round-tripped to the provider on the next turn (Phase 7 full mode)."""
    from meta_harney.abstractions._types import ThinkingBlock
    from meta_harney.testing import FakeRound, runtime_for_testing

    class _LookupInput(BaseModel):
        q: str

    class LookupTool(BaseTool):
        name = "lookup"
        description = "Look something up."
        input_schema = _LookupInput

        async def execute(
            self, inv: ToolInvocation, ctx: ToolContext
        ) -> ToolResult:
            return ToolResult(success=True, output={"answer": 42})

    rounds = [
        FakeRound(
            thinking_blocks=[
                ThinkingBlock(text="let me check the DB", signature="sig1"),
            ],
            tool_calls=[
                ProviderToolCall(
                    invocation_id="t1",
                    name="lookup",
                    args={"q": "ultimate answer"},
                ),
            ],
            stop_reason="tool_use",
        ),
        FakeRound(text="The answer is 42.", stop_reason="end_turn"),
    ]
    provider = FakeLLMProvider(rounds=rounds)
    rt = runtime_for_testing(scripted_rounds=rounds, tools={"lookup": LookupTool()})
    rt._provider = provider

    session = await rt.create_session()
    final = await rt.invoke(session.id, "What is the ultimate answer?")
    assert "42" in final.content[0].text  # type: ignore[union-attr]

    # session.messages role sequence:
    # [user, assistant(thinking + tool_call), tool(result), assistant(final text)]
    refreshed = await rt._session_store.load(session.id)
    assert refreshed is not None
    roles = [m.role for m in refreshed.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]

    # First assistant message has ThinkingBlock (signature preserved)
    first_assistant = refreshed.messages[1]
    thinking_in_msg = [
        b for b in first_assistant.content if isinstance(b, ThinkingBlock)
    ]
    assert len(thinking_in_msg) == 1
    assert thinking_in_msg[0].text == "let me check the DB"
    assert thinking_in_msg[0].signature == "sig1"

    # Second provider.calls receives the first turn's ThinkingBlock
    assert len(provider.calls) == 2
    second_call_msgs = provider.calls[1].messages
    assistant_msgs = [m for m in second_call_msgs if m.role == "assistant"]
    assert any(
        any(isinstance(b, ThinkingBlock) for b in m.content) for m in assistant_msgs
    ), "second turn should include ThinkingBlock in history"
