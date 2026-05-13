# meta-harney Phase 2: Engine + Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent loop (`run_turn`) and LLM provider abstraction on top of Phase 1's 9 abstractions, so one end-to-end agent conversation can be driven via a `FakeLLMProvider` with all loop responsibilities exercised (LLM call, tool dispatch, permission check, hooks, timeout, compaction, cancellation).

**Architecture:** Provider layer first (independent of engine). Then engine support modules (stream events, retry, tracing, runtime config). Then two dispatcher helpers (`hook_dispatch`, `tool_dispatch`). Then `engine/loop.py::run_turn` built up incrementally (LLM-only → +tools → +permission → +hooks → +timeout → +compaction → +cancellation), each step driven by a new integration test against the `FakeLLMProvider`.

**Tech Stack:**
- Python 3.10+
- Pydantic v2 (data contracts)
- pytest + pytest-asyncio (testing)
- asyncio (concurrency)
- mypy strict + ruff (quality gates)

**Spec reference:** `docs/superpowers/specs/2026-05-13-meta-harney-design.md` §5 (data flow), §7 (error handling), §4 (interfaces).

**Phase 1 status (foundation already merged):**
- 9 abstractions in `src/meta_harney/abstractions/`
- 5 builtin defaults in `src/meta_harney/builtin/`
- 5 contract suites in `tests/contracts/`
- 122/122 tests pass; mypy strict + ruff clean
- Initial commit on `main` branch

---

## File Structure After Phase 2

```
src/meta_harney/
├── engine/                                    # NEW
│   ├── __init__.py
│   ├── stream_events.py                       # StreamEvent types (6 kinds, spec §5.2)
│   ├── tracing.py                             # new_span_id() + emit helper
│   ├── retry.py                               # RetryConfig + retry_with_backoff
│   ├── config.py                              # RuntimeConfig + ToolSpec
│   ├── hook_dispatch.py                       # fire_hooks(event, hooks, ...) helper
│   ├── tool_dispatch.py                       # execute_tool(inv, tool, ctx, ...) helper
│   └── loop.py                                # run_turn() orchestrator
│
└── providers/                                 # NEW
    ├── __init__.py
    ├── base.py                                # LLMProvider Protocol + ProviderStreamEvent
    └── fake.py                                # FakeLLMProvider for tests

tests/
├── unit/
│   ├── engine/                                # NEW
│   │   ├── test_stream_events.py
│   │   ├── test_tracing.py
│   │   ├── test_retry.py
│   │   ├── test_config.py
│   │   ├── test_hook_dispatch.py
│   │   └── test_tool_dispatch.py
│   └── providers/                             # NEW
│       ├── test_base.py
│       └── test_fake.py
├── contracts/
│   └── llm_provider.py                        # NEW
└── integration/                               # NEW
    └── test_engine_e2e.py                     # All e2e scenarios in one file
```

---

## Task 1: `providers/base.py` — LLMProvider Protocol + Types

**Files:**
- Create: `src/meta_harney/providers/__init__.py` (empty)
- Create: `src/meta_harney/providers/base.py`
- Test: `tests/unit/providers/__init__.py` (empty)
- Test: `tests/unit/providers/test_base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/providers/__init__.py` (empty file) and `tests/unit/providers/test_base.py`:

```python
"""Tests for LLMProvider Protocol + ProviderStreamEvent + ToolSpec."""
from __future__ import annotations

from collections.abc import AsyncIterator

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)


def test_tool_spec_fields():
    spec = ToolSpec(
        name="echo",
        description="Echoes input.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    assert spec.name == "echo"
    assert spec.input_schema["type"] == "object"


def test_provider_text_delta():
    ev = ProviderTextDelta(text="hello")
    assert ev.type == "text_delta"
    assert ev.text == "hello"


def test_provider_tool_call():
    ev = ProviderToolCall(invocation_id="inv1", name="echo", args={"text": "hi"})
    assert ev.type == "tool_call"
    assert ev.invocation_id == "inv1"
    assert ev.name == "echo"
    assert ev.args == {"text": "hi"}


def test_provider_stream_done_minimal():
    ev = ProviderStreamDone(stop_reason="end_turn")
    assert ev.type == "stream_done"
    assert ev.stop_reason == "end_turn"
    assert ev.input_tokens is None


def test_provider_stream_done_with_usage():
    ev = ProviderStreamDone(stop_reason="tool_use", input_tokens=100, output_tokens=50)
    assert ev.input_tokens == 100
    assert ev.output_tokens == 50


def test_provider_call_config_defaults():
    cfg = ProviderCallConfig(model="gpt-test")
    assert cfg.model == "gpt-test"
    assert cfg.max_tokens is None
    assert cfg.temperature is None


async def test_protocol_duck_typing():
    class FakeProvider:
        async def stream(
            self,
            messages: list[Message],
            system_prompt: str,
            tools: list[ToolSpec],
            config: ProviderCallConfig,
        ) -> AsyncIterator[ProviderStreamEvent]:
            yield ProviderTextDelta(text="ok")
            yield ProviderStreamDone(stop_reason="end_turn")

    p: LLMProvider = FakeProvider()
    events = []
    async for e in p.stream(
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        system_prompt="you help",
        tools=[],
        config=ProviderCallConfig(model="gpt-test"),
    ):
        events.append(e)
    assert len(events) == 2
    assert events[0].type == "text_delta"
    assert events[1].type == "stream_done"
```

- [ ] **Step 2: Run test to confirm fail**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_base.py -v
```
Expected: ModuleNotFoundError on `meta_harney.providers.base`.

- [ ] **Step 3: Create the package + base module**

Create `src/meta_harney/providers/__init__.py` (empty).

Create `src/meta_harney/providers/base.py`:

```python
"""LLM provider abstraction: LLMProvider Protocol + ProviderStreamEvent + ToolSpec.

Provider implementations (Anthropic, OpenAI, etc.) plug in here. The engine
calls `provider.stream(...)` once per LLM round and consumes the async
iterator of ProviderStreamEvent until ProviderStreamDone is yielded.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, Union

from pydantic import BaseModel, Field

from meta_harney.abstractions._types import Message


class ToolSpec(BaseModel):
    """Description of a tool exposed to the LLM.

    Engine derives ToolSpec from a registered BaseTool's name, description,
    and input_schema before calling provider.stream(...).
    """

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ProviderCallConfig(BaseModel):
    """Per-call provider parameters."""

    model: str
    max_tokens: int | None = None
    temperature: float | None = None


class _ProviderStreamEventBase(BaseModel):
    type: str


class ProviderTextDelta(_ProviderStreamEventBase):
    """Incremental text chunk emitted by the LLM."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ProviderToolCall(_ProviderStreamEventBase):
    """A completed tool call request from the LLM.

    Provider implementations should buffer streaming JSON tool args internally
    and yield this event only when the full tool call is ready.
    """

    type: Literal["tool_call"] = "tool_call"
    invocation_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ProviderStreamDone(_ProviderStreamEventBase):
    """Terminal event for a single LLM round."""

    type: Literal["stream_done"] = "stream_done"
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"]
    input_tokens: int | None = None
    output_tokens: int | None = None


ProviderStreamEvent = Union[ProviderTextDelta, ProviderToolCall, ProviderStreamDone]


class LLMProvider(Protocol):
    """Streams one LLM completion. Yields ProviderStreamEvents.

    Implementations MUST:
    - yield at least one ProviderStreamDone as the final event
    - raise RetryableProviderError on 429/5xx/network errors
    - raise NonRetryableProviderError on auth/4xx/invalid-request errors
    """

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncIterator[ProviderStreamEvent]: ...
```

- [ ] **Step 4: Run tests to verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_base.py -v
```
Expected: 7 tests pass.

- [ ] **Step 5: Lint + type**

```bash
ruff check src/meta_harney/providers tests/unit/providers
mypy src/meta_harney/providers tests/unit/providers
```
Expected: 0 issues / 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/providers/__init__.py src/meta_harney/providers/base.py tests/unit/providers/__init__.py tests/unit/providers/test_base.py
git commit -m "feat(providers): LLMProvider Protocol + stream event types

ToolSpec carries name/description/JSON-schema for tool exposition.
ProviderCallConfig holds model + sampling params.
ProviderStreamEvent union: TextDelta | ToolCall | StreamDone.
LLMProvider Protocol: async stream(messages, system_prompt, tools, config)
yielding ProviderStreamEvents."
```

---

## Task 2: `providers/fake.py` — FakeLLMProvider for Testing

**Files:**
- Create: `src/meta_harney/providers/fake.py`
- Test: `tests/unit/providers/test_fake.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/providers/test_fake.py`:

```python
"""Tests for FakeLLMProvider — scripted responses for engine tests."""
from __future__ import annotations

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderTextDelta,
    ProviderToolCall,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound


async def _drain(provider, **kwargs):
    out = []
    async for ev in provider.stream(
        messages=kwargs.get("messages", []),
        system_prompt=kwargs.get("system_prompt", ""),
        tools=kwargs.get("tools", []),
        config=kwargs.get("config", ProviderCallConfig(model="fake")),
    ):
        out.append(ev)
    return out


async def test_single_text_round():
    provider = FakeLLMProvider(
        rounds=[FakeRound(text="Hello, world!", stop_reason="end_turn")]
    )
    events = await _drain(provider)
    assert len(events) == 2
    assert events[0].type == "text_delta"
    assert events[0].text == "Hello, world!"
    assert events[1].type == "stream_done"
    assert events[1].stop_reason == "end_turn"


async def test_text_chunked():
    provider = FakeLLMProvider(
        rounds=[FakeRound(text="ab|cd|ef", stop_reason="end_turn", split_on="|")]
    )
    events = await _drain(provider)
    text_events = [e for e in events if e.type == "text_delta"]
    assert [e.text for e in text_events] == ["ab", "cd", "ef"]


async def test_tool_call_round():
    provider = FakeLLMProvider(
        rounds=[FakeRound(
            tool_calls=[ProviderToolCall(invocation_id="inv1", name="echo", args={"x": 1})],
            stop_reason="tool_use",
        )]
    )
    events = await _drain(provider)
    assert any(e.type == "tool_call" for e in events)
    done = [e for e in events if e.type == "stream_done"][0]
    assert done.stop_reason == "tool_use"


async def test_multi_round_sequential():
    """Each call to stream() consumes the next scripted round."""
    provider = FakeLLMProvider(
        rounds=[
            FakeRound(text="first", stop_reason="end_turn"),
            FakeRound(text="second", stop_reason="end_turn"),
        ]
    )
    e1 = await _drain(provider)
    e2 = await _drain(provider)
    assert [x for x in e1 if x.type == "text_delta"][0].text == "first"
    assert [x for x in e2 if x.type == "text_delta"][0].text == "second"


async def test_exhausted_script_raises():
    provider = FakeLLMProvider(rounds=[FakeRound(text="only", stop_reason="end_turn")])
    await _drain(provider)
    with pytest.raises(RuntimeError, match="script exhausted"):
        await _drain(provider)


async def test_records_calls():
    """FakeLLMProvider records args for assertion in tests."""
    provider = FakeLLMProvider(
        rounds=[FakeRound(text="x", stop_reason="end_turn")]
    )
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    await _drain(provider, messages=msgs, system_prompt="be helpful")
    assert len(provider.calls) == 1
    assert provider.calls[0].system_prompt == "be helpful"
    assert provider.calls[0].messages == msgs
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_fake.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `providers/fake.py`**

Create `src/meta_harney/providers/fake.py`:

```python
"""FakeLLMProvider — scripted, deterministic provider for testing the engine.

Each call to stream() consumes one FakeRound from the script. The round can
emit text (optionally chunked via split_on), tool calls, or both, followed
by a stop_reason. The provider records all calls in `provider.calls` for
test assertions.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from meta_harney.abstractions._types import Message
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)


class FakeRound(BaseModel):
    """One scripted LLM response."""

    text: str = ""
    split_on: str | None = None  # if set, text is split and each chunk emitted as a delta
    tool_calls: list[ProviderToolCall] = []
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class RecordedCall:
    """A snapshot of the inputs to one stream() call."""

    messages: list[Message]
    system_prompt: str
    tools: list[ToolSpec]
    config: ProviderCallConfig


@dataclass
class FakeLLMProvider:
    """LLMProvider impl that returns pre-scripted rounds in order."""

    rounds: list[FakeRound]
    calls: list[RecordedCall] = field(default_factory=list)
    _index: int = 0

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(RecordedCall(
            messages=list(messages),
            system_prompt=system_prompt,
            tools=list(tools),
            config=config,
        ))

        if self._index >= len(self.rounds):
            raise RuntimeError(
                f"FakeLLMProvider script exhausted: {len(self.rounds)} rounds, "
                f"caller requested round {self._index + 1}"
            )
        round_ = self.rounds[self._index]
        self._index += 1

        # Emit text (chunked if split_on set)
        if round_.text:
            if round_.split_on:
                for chunk in round_.text.split(round_.split_on):
                    yield ProviderTextDelta(text=chunk)
            else:
                yield ProviderTextDelta(text=round_.text)

        # Emit tool calls
        for tc in round_.tool_calls:
            yield tc

        # Always end with stream_done
        yield ProviderStreamDone(
            stop_reason=round_.stop_reason,
            input_tokens=round_.input_tokens,
            output_tokens=round_.output_tokens,
        )
```

- [ ] **Step 4: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_fake.py -v
ruff check src/meta_harney/providers tests/unit/providers
mypy src/meta_harney/providers tests/unit/providers
```
Expected: 6 tests pass, ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/fake.py tests/unit/providers/test_fake.py
git commit -m "feat(providers): FakeLLMProvider for deterministic engine tests

Scripted rounds emit text (optionally chunked), tool calls, and a
terminal stream_done. Calls are recorded for test assertions on prompts,
messages, and tool specs. Raises if script is exhausted."
```

---

## Task 3: LLMProvider Contract Test

**Files:**
- Create: `tests/contracts/llm_provider.py`
- Modify: `tests/unit/providers/test_fake.py` (add contract subclass)

- [ ] **Step 1: Write `tests/contracts/llm_provider.py`**

```python
"""Contract tests for LLMProvider implementations."""
from __future__ import annotations

from abc import abstractmethod

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
)


class LLMProviderContract:
    """Contract tests every LLMProvider must pass.

    Subclass and implement `make_provider()`. The provider must be scripted
    or otherwise set up to respond to a single text-only round.
    """

    @abstractmethod
    def make_provider(self) -> LLMProvider: ...

    async def test_stream_yields_terminal_stream_done(self) -> None:
        provider = self.make_provider()
        events = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="x"),
        ):
            events.append(ev)
        assert len(events) >= 1
        assert isinstance(events[-1], ProviderStreamDone), (
            f"last event must be ProviderStreamDone, got {type(events[-1]).__name__}"
        )

    async def test_stream_stop_reason_is_valid(self) -> None:
        provider = self.make_provider()
        events = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="x"),
        ):
            events.append(ev)
        done = [e for e in events if isinstance(e, ProviderStreamDone)][-1]
        assert done.stop_reason in {"end_turn", "tool_use", "max_tokens", "error"}
```

- [ ] **Step 2: Update `tests/unit/providers/test_fake.py` — append at end**

Append this to the END of `tests/unit/providers/test_fake.py` (do NOT delete existing tests):

```python


from meta_harney.providers.base import LLMProvider as _LLMProvider
from tests.contracts.llm_provider import LLMProviderContract


class TestFakeLLMProviderContract(LLMProviderContract):
    def make_provider(self) -> _LLMProvider:
        return FakeLLMProvider(
            rounds=[FakeRound(text="ok", stop_reason="end_turn")]
        )
```

- [ ] **Step 3: Run tests + lint**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_fake.py tests/contracts/llm_provider.py -v
ruff check tests/contracts/llm_provider.py
mypy tests/contracts/llm_provider.py
```
Expected: 8 tests pass (6 existing + 2 contract via subclass), ruff/mypy clean.

- [ ] **Step 4: Commit**

```bash
git add tests/contracts/llm_provider.py tests/unit/providers/test_fake.py
git commit -m "test: LLMProviderContract + apply to FakeLLMProvider

Contract enforces: stream() yields terminal ProviderStreamDone; stop_reason
is one of the 4 valid literals. FakeLLMProvider passes 2 contract checks
on top of its 6 specific tests."
```

---

## Task 4: `engine/stream_events.py`

**Files:**
- Create: `src/meta_harney/engine/__init__.py` (empty)
- Create: `src/meta_harney/engine/stream_events.py`
- Test: `tests/unit/engine/__init__.py` (empty)
- Test: `tests/unit/engine/test_stream_events.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/engine/__init__.py` (empty). Then create `tests/unit/engine/test_stream_events.py`:

```python
"""Tests for engine StreamEvent types (the engine-level event stream emitted to callers)."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolResult
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)


def test_text_delta():
    ev = TextDelta(text="hello")
    assert ev.kind == "text_delta"
    assert ev.text == "hello"


def test_thinking_delta():
    ev = ThinkingDelta(text="reasoning...")
    assert ev.kind == "thinking_delta"


def test_tool_call_started():
    ev = ToolCallStarted(
        tool_name="echo",
        invocation_id="inv-1",
        args={"x": 1},
    )
    assert ev.kind == "tool_call_started"
    assert ev.tool_name == "echo"


def test_tool_call_completed():
    ev = ToolCallCompleted(
        tool_name="echo",
        invocation_id="inv-1",
        result=ToolResult(success=True, output={"x": 1}),
    )
    assert ev.kind == "tool_call_completed"
    assert ev.result.success


def test_iteration_completed():
    ev = IterationCompleted(iteration=0)
    assert ev.kind == "iteration_completed"
    assert ev.iteration == 0


def test_turn_completed():
    ev = TurnCompleted(total_iterations=3)
    assert ev.kind == "turn_completed"
    assert ev.total_iterations == 3


def test_stream_event_union():
    events: list[StreamEvent] = [
        TextDelta(text="a"),
        ThinkingDelta(text="b"),
        ToolCallStarted(tool_name="t", invocation_id="i", args={}),
        ToolCallCompleted(
            tool_name="t",
            invocation_id="i",
            result=ToolResult(success=True, output=None),
        ),
        IterationCompleted(iteration=0),
        TurnCompleted(total_iterations=1),
    ]
    assert len(events) == 6
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_stream_events.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `engine/stream_events.py`**

Create `src/meta_harney/engine/__init__.py` (empty).

Create `src/meta_harney/engine/stream_events.py`:

```python
"""Engine-level StreamEvent types.

These are emitted by `engine.loop.run_turn()` to the caller. They are
HIGHER level than ProviderStreamEvent: they describe "what the agent did",
not "what the LLM said". See spec §5.2 for the StreamEvent vs TraceEvent
distinction.

Six kinds:
- text_delta: incremental assistant text
- thinking_delta: incremental extended-thinking text
- tool_call_started: a tool was invoked (permission cleared, executing)
- tool_call_completed: a tool returned (success or failure)
- iteration_completed: one LLM-round + optional tool-batch is done
- turn_completed: the whole agent turn is done
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import ToolResult


class _StreamEventBase(BaseModel):
    kind: str


class TextDelta(_StreamEventBase):
    kind: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(_StreamEventBase):
    kind: Literal["thinking_delta"] = "thinking_delta"
    text: str


class ToolCallStarted(_StreamEventBase):
    kind: Literal["tool_call_started"] = "tool_call_started"
    tool_name: str
    invocation_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolCallCompleted(_StreamEventBase):
    kind: Literal["tool_call_completed"] = "tool_call_completed"
    tool_name: str
    invocation_id: str
    result: ToolResult


class IterationCompleted(_StreamEventBase):
    kind: Literal["iteration_completed"] = "iteration_completed"
    iteration: int


class TurnCompleted(_StreamEventBase):
    kind: Literal["turn_completed"] = "turn_completed"
    total_iterations: int


StreamEvent = Union[
    TextDelta,
    ThinkingDelta,
    ToolCallStarted,
    ToolCallCompleted,
    IterationCompleted,
    TurnCompleted,
]
```

- [ ] **Step 4: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_stream_events.py -v
ruff check src/meta_harney/engine tests/unit/engine
mypy src/meta_harney/engine tests/unit/engine
```
Expected: 7 pass, ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/__init__.py src/meta_harney/engine/stream_events.py tests/unit/engine/__init__.py tests/unit/engine/test_stream_events.py
git commit -m "feat(engine): StreamEvent types (6 kinds per spec §5.2)

TextDelta, ThinkingDelta, ToolCallStarted, ToolCallCompleted,
IterationCompleted, TurnCompleted. Engine-level events emitted to
caller. Distinct from ProviderStreamEvent (raw LLM stream) and
TraceEvent (observability stream)."
```

---

## Task 5: `engine/tracing.py` + `engine/retry.py`

**Files:**
- Create: `src/meta_harney/engine/tracing.py`
- Create: `src/meta_harney/engine/retry.py`
- Test: `tests/unit/engine/test_tracing.py`
- Test: `tests/unit/engine/test_retry.py`

- [ ] **Step 1: Write `tests/unit/engine/test_tracing.py`**

```python
"""Tests for engine.tracing helpers."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.tracing import emit_event, new_span_id


def test_new_span_id_returns_short_hex_string():
    sid = new_span_id()
    assert isinstance(sid, str)
    assert len(sid) == 16
    # Each call gives a unique id
    assert new_span_id() != sid


async def test_emit_event_calls_sink():
    class CollectingSink:
        def __init__(self):
            self.events: list[TraceEvent] = []

        async def emit(self, event):
            self.events.append(event)

        async def flush(self):
            pass

    sink = CollectingSink()
    await emit_event(
        sink,
        session_id="s1",
        kind="turn.started",
        span_id="span-1",
        parent_span_id=None,
        payload={"user_message_id": "m1"},
    )
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.session_id == "s1"
    assert ev.kind == "turn.started"
    assert ev.span_id == "span-1"
    assert ev.payload == {"user_message_id": "m1"}
    assert isinstance(ev.ts, datetime)


async def test_emit_event_swallows_sink_exceptions():
    """Sink exceptions MUST NOT propagate — observability shouldn't kill business."""
    class BrokenSink:
        async def emit(self, event):
            raise RuntimeError("kaboom")

        async def flush(self):
            pass

    # Should not raise.
    await emit_event(
        BrokenSink(),
        session_id="s1",
        kind="x",
        span_id="sp",
        parent_span_id=None,
        payload={},
    )


async def test_emit_event_with_duration_ms():
    class CollectingSink:
        def __init__(self):
            self.events: list[TraceEvent] = []

        async def emit(self, event):
            self.events.append(event)

        async def flush(self):
            pass

    sink = CollectingSink()
    await emit_event(
        sink,
        session_id="s",
        kind="tool.completed",
        span_id="x",
        parent_span_id="y",
        payload={},
        duration_ms=42.5,
    )
    assert sink.events[0].duration_ms == 42.5
```

- [ ] **Step 2: Write `tests/unit/engine/test_retry.py`**

```python
"""Tests for engine.retry helpers."""
from __future__ import annotations

import pytest

from meta_harney.engine.retry import RetryConfig, compute_backoff, retry_with_backoff
from meta_harney.errors import NonRetryableProviderError, RetryableProviderError


def test_retry_config_defaults():
    c = RetryConfig()
    assert c.max_attempts == 3
    assert c.initial_delay_s == 1.0
    assert c.backoff_multiplier == 2.0
    assert c.max_delay_s == 30.0


def test_compute_backoff_exponential():
    c = RetryConfig(initial_delay_s=1.0, backoff_multiplier=2.0, max_delay_s=100.0)
    assert compute_backoff(c, attempt=1) == 1.0
    assert compute_backoff(c, attempt=2) == 2.0
    assert compute_backoff(c, attempt=3) == 4.0


def test_compute_backoff_clamped_by_max():
    c = RetryConfig(initial_delay_s=1.0, backoff_multiplier=10.0, max_delay_s=5.0)
    assert compute_backoff(c, attempt=1) == 1.0
    assert compute_backoff(c, attempt=2) == 5.0  # clamped
    assert compute_backoff(c, attempt=3) == 5.0  # still clamped


async def test_retry_with_backoff_returns_on_success():
    async def f():
        return "ok"

    result = await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert result == "ok"


async def test_retry_with_backoff_retries_retryable():
    attempts = []

    async def f():
        attempts.append(1)
        if len(attempts) < 2:
            raise RetryableProviderError("transient")
        return "eventually"

    result = await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert result == "eventually"
    assert len(attempts) == 2


async def test_retry_with_backoff_gives_up_after_max():
    async def f():
        raise RetryableProviderError("always fails")

    with pytest.raises(RetryableProviderError):
        await retry_with_backoff(
            f, RetryConfig(max_attempts=3, initial_delay_s=0.0)
        )


async def test_retry_with_backoff_does_not_retry_nonretryable():
    attempts = []

    async def f():
        attempts.append(1)
        raise NonRetryableProviderError("auth fail")

    with pytest.raises(NonRetryableProviderError):
        await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert len(attempts) == 1  # NOT retried
```

- [ ] **Step 3: Run failing tests**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_tracing.py tests/unit/engine/test_retry.py -v
```
Expected: ModuleNotFoundError on tracing AND retry.

- [ ] **Step 4: Write `src/meta_harney/engine/tracing.py`**

```python
"""Tracing helpers for the engine: span_id generation + safe sink emission.

The engine uses these directly; tools/hooks receive `current_span_id` and a
`new_span_id` callable via ToolContext to emit their own child spans.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def new_span_id() -> str:
    """Generate a short (16 hex chars) span id."""
    return uuid.uuid4().hex[:16]


async def emit_event(
    sink: TraceSink,
    *,
    session_id: str,
    kind: str,
    span_id: str,
    parent_span_id: str | None,
    payload: dict[str, Any],
    duration_ms: float | None = None,
) -> None:
    """Emit a TraceEvent to the sink, swallowing any sink exceptions.

    Per spec §7.2 rule ②: observability MUST NOT kill business. If the
    sink raises, the engine logs to stderr and continues.
    """
    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id=session_id,
        kind=kind,
        span_id=span_id,
        parent_span_id=parent_span_id,
        payload=payload,
        duration_ms=duration_ms,
    )
    try:
        await sink.emit(event)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[meta_harney] trace sink failed for kind={kind!r}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
```

- [ ] **Step 5: Write `src/meta_harney/engine/retry.py`**

```python
"""Retry helpers for transient provider errors.

The engine wraps `provider.stream()` calls in `retry_with_backoff(...)`.
Only RetryableProviderError triggers retry; NonRetryableProviderError
propagates immediately (per spec §7.2).
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

from meta_harney.errors import RetryableProviderError


T = TypeVar("T")


class RetryConfig(BaseModel):
    """Exponential-backoff retry configuration."""

    max_attempts: int = 3
    initial_delay_s: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_s: float = 30.0


def compute_backoff(config: RetryConfig, *, attempt: int) -> float:
    """Compute the delay before `attempt`. attempt is 1-indexed."""
    delay = config.initial_delay_s * (config.backoff_multiplier ** (attempt - 1))
    return min(delay, config.max_delay_s)


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig,
) -> T:
    """Call fn() with exponential backoff on RetryableProviderError.

    NonRetryableProviderError propagates immediately. Other exceptions
    also propagate without retry — the engine wraps them at higher level.
    """
    last_exc: RetryableProviderError | None = None
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await fn()
        except RetryableProviderError as exc:
            last_exc = exc
            if attempt < config.max_attempts:
                await asyncio.sleep(compute_backoff(config, attempt=attempt))
            else:
                break
    assert last_exc is not None  # invariant: only break path
    raise last_exc
```

- [ ] **Step 6: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_tracing.py tests/unit/engine/test_retry.py -v
ruff check src/meta_harney/engine/tracing.py src/meta_harney/engine/retry.py tests/unit/engine
mypy src/meta_harney/engine/tracing.py src/meta_harney/engine/retry.py
```
Expected: 11 pass (4 tracing + 7 retry), ruff/mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/meta_harney/engine/tracing.py src/meta_harney/engine/retry.py tests/unit/engine/test_tracing.py tests/unit/engine/test_retry.py
git commit -m "feat(engine): tracing + retry helpers

tracing: new_span_id() generates 16-hex strings; emit_event() catches
sink exceptions and logs to stderr (observability never kills business).
retry: RetryConfig + compute_backoff() (capped exponential) +
retry_with_backoff() (only retries RetryableProviderError, propagates
NonRetryable immediately)."
```

---

## Task 6: `engine/config.py` — RuntimeConfig + ToolSpec Helper

**Files:**
- Create: `src/meta_harney/engine/config.py`
- Test: `tests/unit/engine/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for RuntimeConfig + ToolSpec helpers."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from pydantic import BaseModel

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.engine.config import RuntimeConfig, tool_to_spec


class _EchoInput(BaseModel):
    text: str


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes input."
    input_schema = _EchoInput
    default_timeout = 5.0

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output=inv.args)


def test_runtime_config_defaults():
    c = RuntimeConfig(model="gpt-test")
    assert c.model == "gpt-test"
    assert c.tool_timeout_overrides == {}
    assert c.global_default_timeout == 300.0
    assert c.max_iterations == 10
    assert c.compaction_trigger_tokens is None
    assert c.context_window_tokens == 100_000


def test_tool_timeout_resolution_uses_override():
    c = RuntimeConfig(
        model="x",
        tool_timeout_overrides={"echo": 1.5},
    )
    assert c.resolve_tool_timeout(_EchoTool()) == 1.5


def test_tool_timeout_resolution_uses_tool_default():
    c = RuntimeConfig(model="x")
    assert c.resolve_tool_timeout(_EchoTool()) == 5.0


def test_tool_timeout_resolution_falls_back_to_global():
    class _NoTimeoutTool(BaseTool):
        name = "nt"
        description = "no timeout"
        input_schema = _EchoInput

        async def execute(self, inv, ctx) -> ToolResult:
            return ToolResult(success=True, output=None)

    c = RuntimeConfig(model="x", global_default_timeout=42.0)
    assert c.resolve_tool_timeout(_NoTimeoutTool()) == 42.0


def test_tool_timeout_resolution_none_when_all_unset():
    class _NoTimeoutTool(BaseTool):
        name = "nt"
        description = "no timeout"
        input_schema = _EchoInput

        async def execute(self, inv, ctx) -> ToolResult:
            return ToolResult(success=True, output=None)

    c = RuntimeConfig(model="x", global_default_timeout=None)
    assert c.resolve_tool_timeout(_NoTimeoutTool()) is None


def test_tool_to_spec_basic():
    spec = tool_to_spec(_EchoTool())
    assert spec.name == "echo"
    assert spec.description == "Echoes input."
    assert "properties" in spec.input_schema
    assert "text" in spec.input_schema["properties"]
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_config.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `engine/config.py`**

```python
"""Engine runtime configuration: timeouts, retry, compaction trigger.

`tool_to_spec` converts a BaseTool subclass into a ToolSpec for the LLM
provider — derived from the tool's name, description, and Pydantic
input_schema.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import BaseTool
from meta_harney.providers.base import ToolSpec


class RuntimeConfig(BaseModel):
    """Engine runtime parameters (one-shot or per-runtime)."""

    model: str

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


def tool_to_spec(tool: BaseTool) -> ToolSpec:
    """Convert a BaseTool into a ToolSpec for LLM provider exposure."""
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema.model_json_schema(),
    )
```

- [ ] **Step 4: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_config.py -v
ruff check src/meta_harney/engine/config.py tests/unit/engine/test_config.py
mypy src/meta_harney/engine/config.py
```
Expected: 6 pass, clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/config.py tests/unit/engine/test_config.py
git commit -m "feat(engine): RuntimeConfig + tool_to_spec helper

RuntimeConfig holds model, per-tool timeout overrides + global default,
max iterations, context window + compaction trigger threshold.
resolve_tool_timeout() implements per-spec resolution order.
tool_to_spec() converts BaseTool → ToolSpec via input_schema's JSON schema."
```

---

## Task 7: `engine/hook_dispatch.py`

**Files:**
- Create: `src/meta_harney/engine/hook_dispatch.py`
- Test: `tests/unit/engine/test_hook_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for hook dispatch helpers."""
from __future__ import annotations

import pytest

from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.hook_dispatch import dispatch_hooks
from meta_harney.errors import HookHaltError


class _AllowHook(BaseHook):
    subscribed_events: set[HookEventKind] = {"pre_tool", "post_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(allow=True)


class _DenyHook(BaseHook):
    subscribed_events: set[HookEventKind] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(allow=False, reason="policy")


class _HaltHook(BaseHook):
    subscribed_events: set[HookEventKind] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        raise HookHaltError(reason="user-requested stop")


class _TransformHook(BaseHook):
    subscribed_events: set[HookEventKind] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(transform={"args": {"x": 42}})


class _RaiseHook(BaseHook):
    subscribed_events: set[HookEventKind] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        raise RuntimeError("hook bug")


async def test_dispatch_skips_non_subscribed():
    class _SessionHook(BaseHook):
        subscribed_events: set[HookEventKind] = {"session_start"}
        async def handle(self, event):
            return HookDecision(allow=False)

    result = await dispatch_hooks(
        hooks=[_SessionHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is True  # default when no hook fires
    assert result.transform is None


async def test_dispatch_all_allow():
    result = await dispatch_hooks(
        hooks=[_AllowHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is True


async def test_dispatch_first_deny_short_circuits():
    result = await dispatch_hooks(
        hooks=[_DenyHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is False
    assert result.reason == "policy"


async def test_dispatch_halt_propagates():
    with pytest.raises(HookHaltError, match="user-requested stop"):
        await dispatch_hooks(
            hooks=[_HaltHook()],
            event=HookEvent(kind="pre_tool", session_id="s", payload={}),
            sink=NullSink(),
            current_span_id="parent",
        )


async def test_dispatch_transform_pre_event_returned():
    """transform on pre_* events is returned in the merged decision."""
    result = await dispatch_hooks(
        hooks=[_TransformHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.transform == {"args": {"x": 42}}


async def test_dispatch_transform_on_post_ignored():
    """transform on post_* is ignored per spec (engine warns via trace)."""
    class _PostTransform(BaseHook):
        subscribed_events: set[HookEventKind] = {"post_tool"}
        async def handle(self, event):
            return HookDecision(transform={"foo": "bar"})

    result = await dispatch_hooks(
        hooks=[_PostTransform()],
        event=HookEvent(kind="post_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.transform is None  # ignored


async def test_dispatch_swallows_random_hook_exception():
    """Non-Halt exceptions in hooks are logged via trace and execution continues (fail-open)."""
    result = await dispatch_hooks(
        hooks=[_RaiseHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    # _RaiseHook fail-open, _AllowHook proceeds
    assert result.allow is True
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_hook_dispatch.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `engine/hook_dispatch.py`**

```python
"""Hook event dispatch for the engine.

Filters subscribed hooks, dispatches in order, merges decisions:
- First deny short-circuits (returns immediately)
- HookHaltError propagates to caller (terminates run_turn)
- Other exceptions are logged to trace and execution continues (fail-open)
- `transform` is only honored on pre_* events; ignored on post_* events
"""
from __future__ import annotations

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
    merged_transform: dict | None = None
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
        except Exception as exc:  # noqa: BLE001
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
```

- [ ] **Step 4: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_hook_dispatch.py -v
ruff check src/meta_harney/engine/hook_dispatch.py tests/unit/engine/test_hook_dispatch.py
mypy src/meta_harney/engine/hook_dispatch.py
```
Expected: 7 pass, ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/hook_dispatch.py tests/unit/engine/test_hook_dispatch.py
git commit -m "feat(engine): hook_dispatch helper

dispatch_hooks() filters subscribed hooks, executes in order, merges
decisions. First deny short-circuits. HookHaltError propagates.
Other exceptions logged via trace (fail-open). transform honored
on pre_* only; ignored on post_* with warning trace."
```

---

## Task 8: `engine/tool_dispatch.py`

**Files:**
- Create: `src/meta_harney/engine/tool_dispatch.py`
- Test: `tests/unit/engine/test_tool_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for tool dispatch helper."""
from __future__ import annotations

import asyncio

from pydantic import BaseModel

from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.tool_dispatch import execute_tool
from meta_harney.engine.tracing import new_span_id


class _EchoInput(BaseModel):
    text: str = ""


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes."
    input_schema = _EchoInput
    default_timeout = 5.0

    async def execute(self, inv, ctx):
        return ToolResult(success=True, output={"echoed": inv.args.get("text", "")})


class _RaiseTool(BaseTool):
    name = "raise"
    description = "Always raises."
    input_schema = _EchoInput

    async def execute(self, inv, ctx):
        raise ValueError("boom")


class _SlowTool(BaseTool):
    name = "slow"
    description = "Sleeps too long."
    input_schema = _EchoInput
    default_timeout = 0.01  # 10ms — easy to exceed

    async def execute(self, inv, ctx):
        await asyncio.sleep(1.0)
        return ToolResult(success=True, output="never")


async def _make_ctx():
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id=new_span_id(),
        new_span_id=new_span_id,
    )


async def test_execute_tool_happy_path():
    ctx = await _make_ctx()
    inv = ToolInvocation(name="echo", args={"text": "hi"}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert result.success
    assert result.output == {"echoed": "hi"}


async def test_execute_tool_permission_denied():
    ctx = await _make_ctx()
    inv = ToolInvocation(name="echo", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=DenyAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "deny" in (result.error or "").lower()


async def test_execute_tool_exception_becomes_failure():
    ctx = await _make_ctx()
    inv = ToolInvocation(name="raise", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_RaiseTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "boom" in (result.error or "")


async def test_execute_tool_timeout():
    ctx = await _make_ctx()
    inv = ToolInvocation(name="slow", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_SlowTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "timed out" in (result.error or "").lower()


async def test_execute_tool_pre_hook_can_transform_args():
    class _OverrideArgs(BaseHook):
        subscribed_events: set[HookEventKind] = {"pre_tool"}
        async def handle(self, event):
            return HookDecision(transform={"args": {"text": "OVERRIDE"}})

    ctx = await _make_ctx()
    inv = ToolInvocation(name="echo", args={"text": "original"}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[_OverrideArgs()],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert result.output == {"echoed": "OVERRIDE"}


async def test_execute_tool_pre_hook_deny():
    class _Block(BaseHook):
        subscribed_events: set[HookEventKind] = {"pre_tool"}
        async def handle(self, event):
            return HookDecision(allow=False, reason="hook-blocked")

    ctx = await _make_ctx()
    inv = ToolInvocation(name="echo", args={}, invocation_id="i1", session_id="s1")
    result = await execute_tool(
        invocation=inv,
        tool=_EchoTool(),
        permission_resolver=AllowAllPermissionResolver(),
        hooks=[_Block()],
        ctx=ctx,
        config=RuntimeConfig(model="x"),
        parent_span_id=ctx.current_span_id,
    )
    assert not result.success
    assert "hook-blocked" in (result.error or "")
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_tool_dispatch.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `engine/tool_dispatch.py`**

```python
"""Tool dispatch helper.

Wraps a single ToolInvocation execution with:
  1. Permission check
  2. Pre-tool hooks (with possible args transform via HookDecision.transform)
  3. Timeout-bounded tool execution
  4. Post-tool hooks
  5. Trace events at each step

Returns a ToolResult — never raises (except HookHaltError, which propagates).
"""
from __future__ import annotations

import asyncio
import time

from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.hook_dispatch import dispatch_hooks
from meta_harney.engine.tracing import emit_event


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
    """Run one tool invocation. Returns a ToolResult.

    All errors (permission deny, hook deny, exception, timeout) are
    converted to ToolResult(success=False, error=...). Only HookHaltError
    propagates (per spec §7 rule 3).
    """
    sink = ctx.trace_sink

    # 1. Permission check
    perm_span = ctx.new_span_id()
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
            span_id=ctx.new_span_id(),
            parent_span_id=parent_span_id,
            payload={"tool_name": invocation.name, "reason": perm.reason or "denied"},
        )
        return ToolResult(success=False, error=f"permission denied: {perm.reason or 'no reason'}")

    # 2. pre_tool hooks
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

    # 3. Execute with timeout
    timeout = config.resolve_tool_timeout(tool)
    tool_span = ctx.new_span_id()
    invoke_ctx = ToolContext(
        session_store=ctx.session_store,
        trace_sink=ctx.trace_sink,
        current_span_id=tool_span,
        new_span_id=ctx.new_span_id,
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
    except Exception as exc:  # noqa: BLE001
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

    # 4. post_tool hooks
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
```

- [ ] **Step 4: Verify pass**

```bash
source .venv/bin/activate
pytest tests/unit/engine/test_tool_dispatch.py -v
ruff check src/meta_harney/engine/tool_dispatch.py tests/unit/engine/test_tool_dispatch.py
mypy src/meta_harney/engine/tool_dispatch.py
```
Expected: 6 pass, ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/tool_dispatch.py tests/unit/engine/test_tool_dispatch.py
git commit -m "feat(engine): tool_dispatch helper

execute_tool() runs the full per-tool pipeline:
  permission check → pre_tool hooks → timeout-bounded execute →
  post_tool hooks
All failure modes (deny, hook block, exception, timeout) converted
to ToolResult(success=False, error=...). HookHaltError propagates.
Trace events emitted at each transition: permission.resolved,
tool.denied, tool.invoked, tool.completed, tool.timed_out, error.raised."
```

---

## Task 9: `engine/loop.py` — Minimal `run_turn` (LLM-only happy path)

**Files:**
- Create: `src/meta_harney/engine/loop.py`
- Test: `tests/integration/__init__.py` (empty)
- Test: `tests/integration/test_engine_e2e.py` (first scenario)

This task introduces the minimal viable run_turn: builds prompt, calls LLM once, appends assistant message, saves session, returns final message. No tools, no hooks, no compaction, no cancellation handling. Subsequent tasks add layers.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/__init__.py` (empty).

Create `tests/integration/test_engine_e2e.py`:

```python
"""End-to-end engine tests using FakeLLMProvider."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import run_turn
from meta_harney.engine.stream_events import (
    StreamEvent,
    TextDelta,
    TurnCompleted,
)
from meta_harney.providers.fake import FakeLLMProvider, FakeRound


async def _new_session(store, session_id="s1"):
    s = Session(id=session_id, created_at=datetime.now(timezone.utc))
    await store.save(s)
    return s


async def test_happy_path_text_only():
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
    assert loaded.messages[1].content[0].text == "Hello!"
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
```
Expected: ImportError on `meta_harney.engine.loop`.

- [ ] **Step 3: Implement minimal `engine/loop.py`**

```python
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

from collections.abc import AsyncIterator
from typing import Any

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
    ThinkingDelta,
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
) -> AsyncIterator[StreamEvent]:
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
    # Note: at this point session.messages includes the just-appended user_message,
    # but the in-store version doesn't (we save at end). To keep the LLM seeing
    # the latest user msg, we pass session.messages directly instead of relying
    # on build_context_messages (which loads from store).
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
```

- [ ] **Step 4: Run test to verify pass**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py tests/integration
mypy src/meta_harney/engine/loop.py
```
Expected: 1 test pass, ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/__init__.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): minimal run_turn (LLM-only happy path)

Initial run_turn implementation: loads session, appends user msg, calls
provider once, accumulates text, appends assistant msg, saves session,
yields TextDelta + TurnCompleted. No tools/hooks/compaction/cancellation
yet — those land in Tasks 10-15.

E2E test: happy_path_text_only."
```

---

## Task 10: Add Tool Dispatch to `run_turn`

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py` (add tool-call scenario)

This task adds iteration logic: when the LLM emits tool calls, execute them via `tool_dispatch.execute_tool`, append results, and loop back to the LLM. Permission integration is automatic (via execute_tool).

- [ ] **Step 1: Append failing test to `tests/integration/test_engine_e2e.py`**

Append:

```python


from pydantic import BaseModel

from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.engine.stream_events import ToolCallCompleted, ToolCallStarted
from meta_harney.providers.fake import ProviderToolCall


class _EchoInput(BaseModel):
    text: str = ""


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes text."
    input_schema = _EchoInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output={"echoed": inv.args.get("text", "")})


async def test_tool_call_cycle():
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
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_tool_call_cycle -v
```
Expected: FAIL — minimal run_turn doesn't handle tool calls.

- [ ] **Step 3: Rewrite `src/meta_harney/engine/loop.py` with iteration + tool dispatch**

Replace the ENTIRE file content with:

```python
"""Engine main loop: run_turn() orchestrator."""
from __future__ import annotations

from collections.abc import AsyncIterator

from meta_harney.abstractions._types import ContentBlock, Message, TextBlock, ToolCallBlock, ToolResultBlock
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation
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
from meta_harney.errors import SessionNotFoundError, ToolNotFoundError
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
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
) -> AsyncIterator[StreamEvent]:
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
        stop_reason = "end_turn"

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
                # Engine-level failure: tool not registered
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


async def _result_for_unknown_tool(inv, sink, parent_span):
    """Convert 'tool name not registered' into a ToolResult fed to the LLM."""
    from meta_harney.abstractions.tool import ToolResult

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

- [ ] **Step 4: Run tests to verify pass**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```
Expected: 2 tests pass (happy + tool cycle), ruff/mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): tool dispatch in run_turn

Iteration loop: detect tool_calls from provider stream → assemble
assistant message with ToolCallBlocks → execute each tool via
tool_dispatch.execute_tool → append ToolResultBlocks as 'tool' role
message → loop back to LLM. Bounded by config.max_iterations.

Unknown tool name (LLM hallucinated) yields ToolResult(success=False,
error=...) fed back to LLM.

E2E: test_tool_call_cycle (2 LLM rounds, 1 tool call, final text)."
```

---

## Task 11: Add Permission Integration E2E (verify tool_dispatch wiring)

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

The permission check is already wired (it's inside `tool_dispatch.execute_tool`). This task just adds an E2E scenario to verify the end-to-end path.

- [ ] **Step 1: Append test to `tests/integration/test_engine_e2e.py`**

```python


from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver


async def test_permission_denied_e2e():
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

    events = []
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
    # Last assistant msg is the recovery text
    assistant_msgs = [m for m in loaded.messages if m.role == "assistant"]
    assert "not allowed" in assistant_msgs[-1].content[0].text
```

- [ ] **Step 2: Run test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_permission_denied_e2e -v
```
Expected: PASS (permission integration is via tool_dispatch which already exists).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(engine): permission denial e2e

When PermissionResolver returns deny, tool_dispatch converts to
ToolResult(success=False, error='permission denied: ...') which the
engine appends as ToolResultBlock. The LLM sees the denial and
adapts (e.g., explains to the user). 2-round conversation completes."
```

---

## Task 12: Add Hook Firing at 7 Event Points

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py`

Engine fires hooks at: session_start, session_end, pre_llm, post_llm, turn_complete (pre_tool / post_tool already fired inside tool_dispatch).

- [ ] **Step 1: Append failing tests to `tests/integration/test_engine_e2e.py`**

```python


from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.errors import HookHaltError


class _RecordingHook(BaseHook):
    """Records every event it sees, in order."""

    def __init__(self, kinds: set[HookEventKind]):
        self.subscribed_events: set[HookEventKind] = kinds
        self.received: list[HookEvent] = []

    async def handle(self, event: HookEvent) -> HookDecision:
        self.received.append(event)
        return HookDecision(allow=True)


async def test_hook_firing_all_kinds():
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


async def test_hook_halt_terminates_turn():
    """Hook raising HookHaltError stops the engine and propagates."""
    store = MemorySessionStore()
    await _new_session(store)

    class _HaltOnPreLlm(BaseHook):
        subscribed_events: set[HookEventKind] = {"pre_llm"}
        async def handle(self, event):
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
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_hook_firing_all_kinds tests/integration/test_engine_e2e.py::test_hook_halt_terminates_turn -v
```
Expected: FAIL — hooks not yet fired in run_turn.

- [ ] **Step 3: Modify `src/meta_harney/engine/loop.py` — add hook firing**

Replace the file with this updated version (adds dispatch_hooks calls at 5 new event points; pre_tool/post_tool are already inside execute_tool):

```python
"""Engine main loop: run_turn() orchestrator."""
from __future__ import annotations

from collections.abc import AsyncIterator

from meta_harney.abstractions._types import ContentBlock, Message, TextBlock, ToolCallBlock, ToolResultBlock
from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
from meta_harney.engine.hook_dispatch import dispatch_hooks
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
    ProviderStreamEvent,
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
) -> AsyncIterator[StreamEvent]:
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
        stop_reason = "end_turn"

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

        # Dispatch each tool call (pre_tool / post_tool fire inside execute_tool)
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

    # Fire turn_complete + session_end hooks
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


async def _result_for_unknown_tool(inv, sink, parent_span):
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

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```
Expected: 5 tests pass (happy + tool cycle + perm denied + hook firing + hook halt), clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): fire all 7 lifecycle hooks in run_turn

Engine fires session_start (turn entry), pre_llm + post_llm (per iter),
turn_complete + session_end (turn exit). pre_tool/post_tool already
fire inside tool_dispatch.execute_tool.

HookHaltError raised from any hook propagates to caller and stops loop.

E2E: test_hook_firing_all_kinds (verify all 7 events delivered);
test_hook_halt_terminates_turn (HookHaltError propagation)."
```

---

## Task 13: Add Tool Timeout E2E

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

Tool timeout is already implemented in `tool_dispatch.execute_tool`. This task adds an E2E scenario verifying the end-to-end path through the engine.

- [ ] **Step 1: Append failing test**

```python


import asyncio


class _SlowTool(BaseTool):
    name = "slow"
    description = "Sleeps too long."
    input_schema = _EchoInput
    default_timeout = 0.05  # 50ms

    async def execute(self, inv, ctx):
        await asyncio.sleep(1.0)
        return ToolResult(success=True, output="never")


async def test_tool_timeout_e2e():
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

    events = []
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
```

- [ ] **Step 2: Run test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_tool_timeout_e2e -v
```
Expected: PASS (timeout already wired through tool_dispatch).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(engine): tool timeout e2e

Slow tool (1s execute, 50ms timeout) → asyncio.TimeoutError caught in
tool_dispatch → ToolResult(success=False, error='timed out...') fed
back to LLM → LLM acknowledges in final response."
```

---

## Task 14: Add Compaction Trigger

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py`

Engine checks compaction trigger after each iteration if `config.compaction_trigger_tokens` is set and a `CompactionStrategy` is provided.

- [ ] **Step 1: Append failing test**

```python


from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.builtin.compaction.summarization import SummarizationCompactor


async def _fake_summarize(messages):
    return f"summary-of-{len(messages)}"


async def test_compaction_triggered_e2e():
    """After tool round, engine triggers compaction; session.messages shrinks."""
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

    provider = FakeLLMProvider(rounds=[FakeRound(text="ok", stop_reason="end_turn")])

    # Mock token counter: each message contributes 1000 tokens
    def counter(msgs):
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
        tools={},
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
    # After compaction: << 50 messages
    assert len(loaded.messages) < 20
    # A summary message exists
    has_summary = any(
        m.role == "system"
        and m.content
        and "summary-of" in m.content[0].text
        for m in loaded.messages
    )
    assert has_summary
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_compaction_triggered_e2e -v
```
Expected: FAIL — `run_turn` doesn't yet accept compaction/token_counter args.

- [ ] **Step 3: Modify `run_turn` signature and add compaction logic**

In `src/meta_harney/engine/loop.py`, modify the `run_turn` function signature and add post-iteration compaction. Show only the changed parts — the rest of the function stays identical to Task 12.

Replace the file with this complete version:

```python
"""Engine main loop: run_turn() orchestrator."""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from meta_harney.abstractions._types import ContentBlock, Message, TextBlock, ToolCallBlock, ToolResultBlock
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook, HookEvent
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
from meta_harney.engine.hook_dispatch import dispatch_hooks
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
from meta_harney.errors import CompactionError, SessionNotFoundError
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderTextDelta,
    ProviderToolCall,
)


TokenCounter = Callable[[list[Message]], int]


def _default_token_counter(messages: list[Message]) -> int:
    """Heuristic: 1 token per 4 characters of text content."""
    total = 0
    for m in messages:
        for block in m.content:
            if hasattr(block, "text") and isinstance(block.text, str):
                total += max(1, len(block.text) // 4)
            else:
                total += 10  # rough fixed cost for non-text blocks
    return total


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
) -> AsyncIterator[StreamEvent]:
    turn_span = new_span_id()
    token_counter = token_counter or _default_token_counter

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
    iteration = 0
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

        text_chunks: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        stop_reason = "end_turn"

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
                break

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

        # Compaction check after each iteration
        if (
            compaction is not None
            and config.compaction_trigger_tokens is not None
        ):
            current_tokens = token_counter(session.messages)
            if current_tokens > config.compaction_trigger_tokens:
                should = await compaction.should_compact(
                    session_id, current_tokens, config.context_window_tokens
                )
                if should:
                    before_n = len(session.messages)
                    before_tokens = current_tokens
                    # Persist current state so compactor can re-load it
                    await session_store.save(session)
                    # Re-load to refresh version after save (save increments version)
                    fresh = await session_store.load(session_id)
                    assert fresh is not None
                    session = fresh
                    try:
                        new_messages = await compaction.compact(session_id)
                    except Exception as exc:  # noqa: BLE001
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
                    after_tokens = token_counter(session.messages)
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


async def _result_for_unknown_tool(inv, sink, parent_span):
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

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```
Expected: 7 tests pass (all previous + compaction), clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): compaction trigger after each iteration

When config.compaction_trigger_tokens is set and a CompactionStrategy is
provided, engine checks token count after each iteration. If exceeded
AND strategy.should_compact() returns True, engine saves current state,
calls strategy.compact(), replaces session.messages. CompactionError
caught and logged (fail-open per spec §7.2).

Default token counter heuristic: ~1 token / 4 chars text.

E2E: test_compaction_triggered_e2e (50 pre-populated msgs → compacted)."
```

---

## Task 15: Cancellation-Safe Finally Save

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py`

Wrap the main loop body in try/finally so that on cancellation (or any error), the engine still saves the session (preserving half-baked state per spec §6.1) and flushes the trace sink.

- [ ] **Step 1: Append failing test**

```python


async def test_cancellation_preserves_session():
    """If caller cancels mid-turn, session is saved with partial state."""
    store = MemorySessionStore()
    await _new_session(store)

    class _BlockingProvider:
        async def stream(self, **kwargs):
            await asyncio.sleep(10.0)  # will be cancelled
            yield  # type: ignore[unreachable]

    async def runner():
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
    assert user_msgs[-1].content[0].text == "hi"
```

- [ ] **Step 2: Run failing test**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_cancellation_preserves_session -v
```
Expected: FAIL — user message not saved on cancellation (current code only saves at successful end).

- [ ] **Step 3: Wrap main loop body in try/finally**

Modify `src/meta_harney/engine/loop.py`. Locate the line:

```python
    session.messages.append(user_message)
```

…and wrap everything after this point through to the end of the function in a `try/finally`. The `finally` block performs the save + flush.

Replace the relevant section of `run_turn` (after `session.messages.append(user_message)`) with:

```python
    saved = False
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
        iteration = 0
        stop = False

        while not stop and iteration < config.max_iterations:
            # ... (the WHOLE existing iteration body from Task 14 stays here, unchanged) ...
            pass  # placeholder — real code from Task 14 goes here

        # turn_complete + session_end hooks
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
        await trace_sink.flush()

        yield TurnCompleted(total_iterations=iteration)

    finally:
        # On cancellation/error: ensure session is saved and trace flushed.
        if not saved:
            try:
                await session_store.save(session)
            except Exception as save_exc:  # noqa: BLE001
                # If save itself fails, at least try to flush trace
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
        try:
            await trace_sink.flush()
        except Exception:  # noqa: BLE001
            pass  # sink failures swallowed per spec §7.2
```

Replace the entire `run_turn` function so the final structure is:

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
) -> AsyncIterator[StreamEvent]:
    turn_span = new_span_id()
    token_counter = token_counter or _default_token_counter

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

            text_chunks: list[str] = []
            tool_calls: list[ProviderToolCall] = []
            stop_reason = "end_turn"

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
                    break

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

            # Compaction
            if (
                compaction is not None
                and config.compaction_trigger_tokens is not None
            ):
                current_tokens = token_counter(session.messages)
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
                        except Exception as exc:  # noqa: BLE001
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
                        after_tokens = token_counter(session.messages)
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
        await trace_sink.flush()

        yield TurnCompleted(total_iterations=iteration)

    finally:
        if not saved:
            try:
                await session_store.save(session)
            except Exception as save_exc:  # noqa: BLE001
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
        try:
            await trace_sink.flush()
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```
Expected: 8 tests pass (all previous + cancellation), clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): cancellation-safe finally save

Wrap run_turn body in try/finally. On any exception (including
asyncio.CancelledError), engine still calls session_store.save(session)
to preserve half-baked turn state (per spec §6.1 option a), and
trace_sink.flush() to drain observability events.

If finally save itself fails, log error and continue (no double-fault).

E2E: test_cancellation_preserves_session — caller cancels at LLM call,
user message survives in store on reload."
```

---

## Task 16: Final Verification Pass

**Files:**
- Verify: all of `src/meta_harney`, `tests/`

- [ ] **Step 1: Full test suite**

```bash
source .venv/bin/activate
pytest -v
```
Expected: All tests pass. Count should be ≥ 150 (Phase 1 had 122; Phase 2 adds ~30: 7 base + 6 fake + 2 contract + 7 stream + 4 trace + 7 retry + 6 config + 7 hook + 6 tool + 8 e2e).

- [ ] **Step 2: mypy strict**

```bash
mypy src/meta_harney
```
Expected: 0 errors.

- [ ] **Step 3: ruff check**

```bash
ruff check src/meta_harney tests
```
Expected: 0 findings. Fix any with `ruff check --fix` and re-run.

- [ ] **Step 4: ruff format check**

```bash
ruff format --check src/meta_harney tests
```
Expected: 0 differences. Fix with `ruff format src/meta_harney tests` if needed.

- [ ] **Step 5: Public API smoke test**

```bash
python -c "
from meta_harney.engine.loop import run_turn
from meta_harney.providers.base import LLMProvider
from meta_harney.providers.fake import FakeLLMProvider, FakeRound
from meta_harney.engine.config import RuntimeConfig
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 6: If any fixes were made above, commit them**

```bash
git status
git add -A
git commit -m "chore: phase 2 final verification

Full test suite green, mypy strict clean, ruff check + format clean.
Public API smoke import works for the engine + provider entry points."
```

(If nothing changed, skip the commit.)

---

## Phase 2 Completion Checklist

- [ ] `from meta_harney.engine.loop import run_turn` works
- [ ] `from meta_harney.providers.fake import FakeLLMProvider, FakeRound` works
- [ ] `pytest -v` reports ≥ 150 tests passing, 0 failures
- [ ] `mypy src/meta_harney` reports 0 errors
- [ ] `ruff check src/meta_harney tests` reports 0 issues
- [ ] All 8 integration scenarios in `tests/integration/test_engine_e2e.py` pass:
  - happy_path_text_only
  - tool_call_cycle
  - permission_denied_e2e
  - hook_firing_all_kinds
  - hook_halt_terminates_turn
  - tool_timeout_e2e
  - compaction_triggered_e2e
  - cancellation_preserves_session
- [ ] Engine package has: `loop.py`, `stream_events.py`, `tracing.py`, `retry.py`, `config.py`, `hook_dispatch.py`, `tool_dispatch.py`
- [ ] Provider package has: `base.py`, `fake.py`
- [ ] Contract suite has: `tests/contracts/llm_provider.py`

**Phase 3 (next plan):**
- `AgentRuntime` class (top-level entry point that wires everything)
- `providers/anthropic.py`, `providers/openai.py` (real LLM providers)
- `MultiAgentBackend` implementations (in-process, subprocess)
- Public API additions to `meta_harney.__init__`

---

## Self-Review

**Spec coverage:**
- §4.1 data contracts: already in Phase 1 (Message, ToolInvocation, ToolResult, ToolContext)
- §4.2-4.10 abstractions: already in Phase 1
- §5.1 turn execution sequence: implemented across Tasks 9-15 (loop.py)
- §5.2 StreamEvent vs TraceEvent: Task 4 (StreamEvent) + tracing in every task
- §5.3 retry: Task 5 (retry.py); integrated via `LLMProvider` calls being wrappable (Phase 3 wires retry_with_backoff into actual provider calls; Phase 2 has FakeProvider which doesn't need retry)
- §5.4 compaction: Task 14
- §6 session & trace model: covered via session_store.save in finally (Task 15) + trace events across all tasks
- §7 error handling: every failure mode (perm deny, hook deny, tool exception, timeout, compaction failure) converts to ToolResult or fail-open behavior. HookHaltError propagates. Cancellation preserves state. TraceSink exceptions swallowed.
- §7.5 tool timeout: Task 6 (RuntimeConfig.resolve_tool_timeout) + Task 8 (execute_tool wraps in asyncio.wait_for) + Task 13 (e2e)
- §8 testing: contract test for LLMProvider (Task 3), 8 integration scenarios

Coverage gap: retry layer integration. Phase 2 builds the `retry_with_backoff` helper but doesn't wrap the FakeLLMProvider's stream() in it. This is intentional — FakeProvider is deterministic. Real providers in Phase 3 will use `retry_with_backoff` around the actual API call. Adding it to Phase 2 would require a "RetryWrappingProvider" decorator which is YAGNI for Phase 2.

**Placeholder scan:** Searched for "TBD", "TODO", "later", "fill in", "add appropriate". None found in steps.

**Type consistency:**
- `RuntimeConfig` signature consistent across Tasks 6, 8, 9, 10, 12, 14, 15 (always passed as `config: RuntimeConfig` kwarg)
- `ToolInvocation(name, args, invocation_id, session_id)` used identically across all engine modules
- `ToolResult(success, output, error, metadata=...)` used identically
- `HookEvent.kind` literal values match between hook_dispatch.py and loop.py at all 7 fire points
- `ProviderStreamEvent` variants checked via `isinstance(ev, ProviderTextDelta | ProviderToolCall | ProviderStreamDone)` consistently
- `dispatch_hooks(hooks, event, sink, current_span_id)` signature unchanged across Task 7, 12 usages
- `execute_tool(invocation=, tool=, permission_resolver=, hooks=, ctx=, config=, parent_span_id=)` kwargs consistent across Task 8 + Task 10
- `run_turn` kwargs grow over Tasks 9 (10 kwargs), 14 (12 kwargs), 15 (12 kwargs); compaction + token_counter added as keyword-only with defaults so earlier task tests still work
