# meta-harney Phase 6: Stabilize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten v0.0.5 by (a) fixing `ToolResult.output` serialization across both providers, (b) wiring Anthropic extended thinking through to `StreamEvent.ThinkingDelta`, and (c) backfilling the two missing integration scenarios from spec §8.4.

**Architecture:** Phase 6 is a stabilization phase: 5 work items, executed in order of risk (safest first). New shared helper `_serialize_tool_output()` lives in `abstractions/_serialize.py` and both providers call it. New `ProviderThinkingDelta` event flows from AnthropicProvider → engine → runtime stream without ever touching `session.messages`. Two new integration scenarios extend `tests/integration/test_engine_e2e.py`.

**Tech Stack:** Python 3.10+, Pydantic v2, anthropic SDK, openai SDK, pytest + pytest-asyncio, mypy strict + ruff.

**Pre-conditions:**
- On `main` at `b329040` (Phase 6 spec committed) or later
- Tests: 268/268 passing
- Version: 0.0.5

---

## File Structure After Phase 6

```
src/meta_harney/
├── __init__.py                           # MODIFIED — export ProviderThinkingDelta, bump 0.0.6
├── abstractions/
│   └── _serialize.py                     # NEW
├── providers/
│   ├── base.py                           # MODIFIED — ProviderThinkingDelta + union
│   ├── anthropic.py                      # MODIFIED — thinking_budget, thinking_delta, helper
│   ├── openai.py                         # MODIFIED — helper + RateLimitError comment
│   └── fake.py                           # MODIFIED — FakeRound.thinking field
└── engine/
    └── loop.py                           # MODIFIED — ProviderThinkingDelta passthrough

pyproject.toml                            # MODIFIED — version 0.0.6

tests/
├── unit/
│   ├── abstractions/
│   │   └── test_serialize.py             # NEW
│   └── providers/
│       ├── test_anthropic.py             # MODIFIED — thinking + dict serialization tests
│       └── test_openai.py                # MODIFIED — dict serialization test
└── integration/
    └── test_engine_e2e.py                # MODIFIED — 3 new scenarios
```

---

## Task 1: `_serialize_tool_output` helper + unit tests

**Files:**
- Create: `src/meta_harney/abstractions/_serialize.py`
- Create: `tests/unit/abstractions/test_serialize.py`

- [ ] **Step 1: Write failing tests in `tests/unit/abstractions/test_serialize.py`**

```python
"""Tests for _serialize_tool_output helper."""
from __future__ import annotations

from datetime import datetime

from meta_harney.abstractions._serialize import _serialize_tool_output


def test_none_returns_empty_string() -> None:
    assert _serialize_tool_output(None) == ""


def test_str_passes_through_unchanged() -> None:
    assert _serialize_tool_output("hello") == "hello"


def test_empty_str_passes_through() -> None:
    assert _serialize_tool_output("") == ""


def test_dict_becomes_json() -> None:
    out = _serialize_tool_output({"a": 1, "b": "x"})
    # Order-stable: json.dumps preserves insertion order
    assert out == '{"a": 1, "b": "x"}'


def test_list_becomes_json() -> None:
    assert _serialize_tool_output([1, 2, 3]) == "[1, 2, 3]"


def test_int_becomes_json() -> None:
    assert _serialize_tool_output(42) == "42"


def test_unicode_preserved_not_escaped() -> None:
    # ensure_ascii=False should keep CJK characters readable
    assert _serialize_tool_output({"name": "张三"}) == '{"name": "张三"}'


def test_datetime_uses_str_fallback() -> None:
    # default=str fallback handles non-JSON-serializable objects
    out = _serialize_tool_output(datetime(2026, 5, 14, 12, 0, 0))
    assert "2026-05-14" in out


def test_circular_reference_returns_repr_not_raise() -> None:
    d: dict[str, object] = {}
    d["self"] = d
    # Should NOT raise; should return some string (repr fallback)
    result = _serialize_tool_output(d)
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_serialize.py -v
```

Expected: ModuleNotFoundError on `meta_harney.abstractions._serialize`.

- [ ] **Step 3: Implement `src/meta_harney/abstractions/_serialize.py`**

```python
"""Tool output serialization helper.

Used by provider implementations to convert ToolResult.output (Any) into a
single string suitable for the LLM's tool_result content. Encapsulates:

- None → "" (omitted content)
- str → unchanged (preserves prose tool outputs as-is)
- structured (dict / list / number / bool) → json.dumps with default=str fallback
- circular references / unserializable → repr(...) — never raises

This is shared between AnthropicProvider and OpenAIProvider to enforce the
invariant that tool result content is always a string.
"""

from __future__ import annotations

import json
from typing import Any


def _serialize_tool_output(output: Any) -> str:
    """Convert arbitrary tool output into a string for LLM consumption."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, default=str, ensure_ascii=False)
    except (ValueError, TypeError):
        return repr(output)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_serialize.py -v
ruff check src/meta_harney/abstractions/_serialize.py tests/unit/abstractions/test_serialize.py
mypy src/meta_harney/abstractions/_serialize.py
```

Expected: 9/9 tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/_serialize.py tests/unit/abstractions/test_serialize.py
git commit -m "feat(abstractions): _serialize_tool_output helper

Shared serializer for ToolResult.output → str:
- None → ''
- str → unchanged
- structured → json.dumps(default=str, ensure_ascii=False)
- unserializable / circular → repr() fallback

Applied to both providers in subsequent tasks."
```

---

## Task 2: AnthropicProvider uses `_serialize_tool_output`

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py` (line 86, ToolResultBlock branch)
- Modify: `tests/unit/providers/test_anthropic.py` (add dict serialization test)

- [ ] **Step 1: Add failing test to `tests/unit/providers/test_anthropic.py`**

Append at end of file:

```python


def test_convert_tool_result_with_dict_output_serializes_json() -> None:
    """Successful ToolResult with dict output uses JSON, not Python repr."""
    from meta_harney.abstractions._types import Message, ToolResultBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(
                    invocation_id="c1",
                    success=True,
                    output={"id": "C-001", "name": "Acme"},
                ),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    result_block = converted[0]["content"][0]
    assert result_block["type"] == "tool_result"
    # Must be JSON (double quotes), not Python repr (single quotes)
    assert result_block["content"] == '{"id": "C-001", "name": "Acme"}'


def test_convert_tool_result_with_none_output_empty_content() -> None:
    """Successful ToolResult with output=None produces empty content, not 'None'."""
    from meta_harney.abstractions._types import Message, ToolResultBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(invocation_id="c1", success=True, output=None),
            ],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    assert converted[0]["content"][0]["content"] == ""
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_convert_tool_result_with_dict_output_serializes_json tests/unit/providers/test_anthropic.py::test_convert_tool_result_with_none_output_empty_content -v
```

Expected: both FAIL — current code uses `str()`, producing Python repr / `"None"`.

- [ ] **Step 3: Modify `src/meta_harney/providers/anthropic.py`**

Add import at top (after the existing `meta_harney.abstractions._types` import block):

```python
from meta_harney.abstractions._serialize import _serialize_tool_output
```

Then in `_convert_block`, change lines around 85-91 from:

```python
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": str(content),
            }
```

To:

```python
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": _serialize_tool_output(content),
            }
```

(Only `str(content)` → `_serialize_tool_output(content)` changes. The rest of the block is unchanged.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: all anthropic tests pass (including the 2 new ones); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "fix(providers): AnthropicProvider uses _serialize_tool_output

Replaces str(content) coercion in ToolResultBlock handling. Fixes:
- output=None → '' (was 'None')
- output=dict/list → JSON (was Python repr with single quotes)

Adds 2 regression tests."
```

---

## Task 3: OpenAIProvider uses `_serialize_tool_output`

**Files:**
- Modify: `src/meta_harney/providers/openai.py` (line ~74, ToolResultBlock branch)
- Modify: `tests/unit/providers/test_openai.py` (add dict serialization test)

- [ ] **Step 1: Add failing test to `tests/unit/providers/test_openai.py`**

Append at end of file:

```python


def test_convert_tool_result_with_dict_output_serializes_json() -> None:
    """Successful ToolResult with dict output uses JSON, not Python repr."""
    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(
                    invocation_id="c1",
                    success=True,
                    output={"id": "C-001", "name": "Acme"},
                ),
            ],
        ),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["role"] == "tool"
    assert converted[0]["content"] == '{"id": "C-001", "name": "Acme"}'


def test_convert_tool_result_with_none_output_empty_content() -> None:
    """Successful ToolResult with output=None produces empty content, not 'None'."""
    msgs = [
        Message(
            role="tool",
            content=[
                ToolResultBlock(invocation_id="c1", success=True, output=None),
            ],
        ),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["content"] == ""
```

(Imports `Message`, `ToolResultBlock`, `_convert_messages_to_openai` are already at top from prior phases.)

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py::test_convert_tool_result_with_dict_output_serializes_json tests/unit/providers/test_openai.py::test_convert_tool_result_with_none_output_empty_content -v
```

Expected: both FAIL — current code uses `str(block.output)` + `or ""`.

- [ ] **Step 3: Modify `src/meta_harney/providers/openai.py`**

Add import at the top, after the existing `meta_harney.abstractions._types` import block:

```python
from meta_harney.abstractions._serialize import _serialize_tool_output
```

In `_convert_messages_to_openai`, around line 72-82 (the `if msg.role == "tool":` branch), change from:

```python
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    content_str = block.error if not block.success else str(block.output)
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.invocation_id,
                            "content": content_str or "",
                        }
                    )
```

To:

```python
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    if block.success:
                        content_str = _serialize_tool_output(block.output)
                    else:
                        content_str = _serialize_tool_output(block.error)
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.invocation_id,
                            "content": content_str,
                        }
                    )
```

(Both success and failure paths go through the helper. The `or ""` fallback is no longer needed — helper guarantees a string and returns `""` for None.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all openai tests pass (including the 2 new ones); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "fix(providers): OpenAIProvider uses _serialize_tool_output

Replaces str(block.output) + 'or' fallback. Fixes:
- output=None → '' (was 'None')
- output=dict/list → JSON (was Python repr with single quotes)

Adds 2 regression tests."
```

---

## Task 4: OpenAI `RateLimitError` catch-order comment

**Files:**
- Modify: `src/meta_harney/providers/openai.py` (error handling block)

- [ ] **Step 1: Locate the error-handling block in `src/meta_harney/providers/openai.py`**

Read the file. Find the `except RateLimitError as exc:` line in the `stream()` method's try/except block.

- [ ] **Step 2: Add a single explanatory comment**

Insert a comment line directly above the `except RateLimitError as exc:` line. Example:

Before:
```python
        try:
            stream_ = await client.chat.completions.create(**kwargs)
            async for chunk in stream_:
                ...
        except RateLimitError as exc:
            raise RetryableProviderError(f"openai rate limit: {exc}") from exc
        except APIStatusError as exc:
            ...
```

After:
```python
        try:
            stream_ = await client.chat.completions.create(**kwargs)
            async for chunk in stream_:
                ...
        # NOTE: RateLimitError is a subclass of APIStatusError in the openai SDK.
        # It MUST be caught before APIStatusError or rate-limit errors would be
        # misclassified as non-retryable 4xx.
        except RateLimitError as exc:
            raise RetryableProviderError(f"openai rate limit: {exc}") from exc
        except APIStatusError as exc:
            ...
```

(The `try:` and `async for chunk in stream_:` lines are unchanged. Only insert the 3-line comment between the inner block and the first `except`.)

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all tests still pass; clean.

- [ ] **Step 4: Commit**

```bash
git add src/meta_harney/providers/openai.py
git commit -m "docs(providers): note RateLimitError catch-order in OpenAIProvider

Comment explains that RateLimitError extends APIStatusError in the
openai SDK, so the except order matters. Prevents future maintainer
from accidentally reordering and misclassifying rate-limit errors."
```

---

## Task 5: Add `ProviderThinkingDelta` to providers/base.py

**Files:**
- Modify: `src/meta_harney/providers/base.py`
- Modify: `tests/unit/providers/` — add a small unit test for the new type (use `test_anthropic.py` or new file; the spec puts it under anthropic tests)

- [ ] **Step 1: Write failing test in `tests/unit/providers/test_anthropic.py`**

Append:

```python


def test_provider_thinking_delta_construction() -> None:
    """ProviderThinkingDelta is a valid stream event variant."""
    from meta_harney.providers.base import ProviderStreamEvent, ProviderThinkingDelta

    ev = ProviderThinkingDelta(text="reasoning step 1")
    assert ev.text == "reasoning step 1"
    assert ev.type == "thinking_delta"

    # Must be a member of ProviderStreamEvent union
    def accepts_event(_: ProviderStreamEvent) -> None:
        pass

    accepts_event(ev)  # type-checker enforcement; no runtime assertion needed
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_provider_thinking_delta_construction -v
```

Expected: ImportError on `ProviderThinkingDelta`.

- [ ] **Step 3: Modify `src/meta_harney/providers/base.py`**

After the existing `ProviderToolCall` class definition and before `ProviderStreamDone`, add:

```python
class ProviderThinkingDelta(_ProviderStreamEventBase):
    """Incremental extended-thinking text emitted by the LLM.

    Anthropic emits these during extended-thinking content blocks. OpenAI
    Chat Completions does not currently have an analog. Engine treats these
    as ephemeral stream events: they do NOT enter session.messages.
    """

    type: Literal["thinking_delta"] = "thinking_delta"
    text: str
```

Update the union (currently line 71):

```python
ProviderStreamEvent = (
    ProviderTextDelta | ProviderToolCall | ProviderThinkingDelta | ProviderStreamDone
)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_provider_thinking_delta_construction -v
ruff check src/meta_harney/providers/base.py
mypy src/meta_harney/providers/base.py
```

Expected: 1/1 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/base.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): add ProviderThinkingDelta event variant

New stream-event type for Anthropic extended-thinking tokens.
Added to ProviderStreamEvent union. Engine and AnthropicProvider
wiring follow in subsequent tasks."
```

---

## Task 6: AnthropicProvider `thinking_budget` + `thinking_delta` parsing

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

- [ ] **Step 1: Write failing tests in `tests/unit/providers/test_anthropic.py`**

Append (assume `AsyncMock`, `MagicMock`, `patch`, and the fake stream helpers from existing tests are already imported at top):

```python


async def test_anthropic_thinking_budget_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider with thinking_budget=N adds thinking kwarg to API call."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import ProviderCallConfig

    captured_kwargs: dict[str, object] = {}

    class _FakeStreamCM:
        async def __aenter__(self) -> "_FakeStreamCM":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> "_FakeStreamCM":
            return self

        async def __anext__(self) -> None:
            raise StopAsyncIteration

    def _fake_stream(**kwargs: object) -> _FakeStreamCM:
        captured_kwargs.update(kwargs)
        return _FakeStreamCM()

    fake_client = MagicMock()
    fake_client.messages.stream = _fake_stream

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        async for _ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            pass

    assert captured_kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 4096}


async def test_anthropic_no_thinking_kwarg_when_budget_none() -> None:
    """Provider with default thinking_budget=None does NOT add thinking kwarg."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import ProviderCallConfig

    captured_kwargs: dict[str, object] = {}

    class _FakeStreamCM:
        async def __aenter__(self) -> "_FakeStreamCM":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> "_FakeStreamCM":
            return self

        async def __anext__(self) -> None:
            raise StopAsyncIteration

    def _fake_stream(**kwargs: object) -> _FakeStreamCM:
        captured_kwargs.update(kwargs)
        return _FakeStreamCM()

    fake_client = MagicMock()
    fake_client.messages.stream = _fake_stream

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test")
        async for _ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            pass

    assert "thinking" not in captured_kwargs


async def test_anthropic_thinking_delta_emits_provider_thinking_delta() -> None:
    """SSE thinking_delta → ProviderThinkingDelta."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamDone,
        ProviderStreamEvent,
        ProviderThinkingDelta,
    )

    # Build fake SSE events: content_block_start(thinking) → content_block_delta(thinking_delta)
    # → content_block_stop → message_stop
    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "thinking"

    cb_delta = MagicMock()
    cb_delta.type = "content_block_delta"
    cb_delta.index = 0
    cb_delta.delta = MagicMock()
    cb_delta.delta.type = "thinking_delta"
    cb_delta.delta.thinking = "let me think..."

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events = [cb_start, cb_delta, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> "_FakeStreamCM":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> "_FakeStreamCM":
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    thinking = [e for e in collected if isinstance(e, ProviderThinkingDelta)]
    assert len(thinking) == 1
    assert thinking[0].text == "let me think..."
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(done) == 1


async def test_anthropic_redacted_thinking_silently_skipped() -> None:
    """redacted_thinking content block → no event, no error."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamDone,
        ProviderStreamEvent,
        ProviderThinkingDelta,
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "redacted_thinking"

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events = [cb_start, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> "_FakeStreamCM":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> "_FakeStreamCM":
            return self

        async def __anext__(self) -> object:
            if not self._evs:
                raise StopAsyncIteration
            return self._evs.pop(0)

    fake_client = MagicMock()
    fake_client.messages.stream = lambda **_kw: _FakeStreamCM(events)

    with patch("meta_harney.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        provider = AnthropicProvider(api_key="test", thinking_budget=4096)
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="claude-sonnet-4-5"),
        ):
            collected.append(ev)

    # No ProviderThinkingDelta yielded
    assert not any(isinstance(e, ProviderThinkingDelta) for e in collected)
    # Stream completes normally
    assert any(isinstance(e, ProviderStreamDone) for e in collected)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v -k "thinking"
```

Expected: 4 FAILs — `AnthropicProvider.__init__` doesn't accept `thinking_budget`; `thinking_delta` SSE not parsed.

- [ ] **Step 3: Modify `src/meta_harney/providers/anthropic.py`**

(a) Update `__init__` signature (after the existing `default_max_tokens` line):

Find:
```python
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
```

Replace with:
```python
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
        thinking_budget: int | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError("AnthropicProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url
        self._default_max_tokens = default_max_tokens
        self._thinking_budget = thinking_budget
```

(b) In `stream()`, after the existing `if config.temperature is not None: kwargs["temperature"] = config.temperature` line, add:

```python
        if self._thinking_budget is not None:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self._thinking_budget,
            }
```

(c) In the SSE event loop, add the `thinking_delta` parsing. Find the `elif etype == "content_block_delta":` branch (around line 196) and extend it. Replace:

```python
                    elif etype == "content_block_delta":
                        delta = event.delta  # type: ignore[union-attr]
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta":
                            yield ProviderTextDelta(text=delta.text)  # type: ignore[union-attr]
                        elif dtype == "input_json_delta":
                            idx = event.index  # type: ignore[union-attr]
                            if idx in tool_use_buffer:
                                tool_use_buffer[idx]["json_chunks"].append(delta.partial_json)  # type: ignore[union-attr]
```

With:

```python
                    elif etype == "content_block_delta":
                        delta = event.delta  # type: ignore[union-attr]
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta":
                            yield ProviderTextDelta(text=delta.text)  # type: ignore[union-attr]
                        elif dtype == "thinking_delta":
                            yield ProviderThinkingDelta(
                                text=getattr(delta, "thinking", "")
                            )
                        elif dtype == "input_json_delta":
                            idx = event.index  # type: ignore[union-attr]
                            if idx in tool_use_buffer:
                                tool_use_buffer[idx]["json_chunks"].append(delta.partial_json)  # type: ignore[union-attr]
```

(d) Import `ProviderThinkingDelta`. Update the existing import block:

```python
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

Note: `redacted_thinking` is naturally a no-op because:
- `content_block_start` with `type="redacted_thinking"` doesn't match the existing `tool_use` branch, so no buffer entry is created
- `content_block_delta` for redacted blocks doesn't carry `thinking_delta` (Anthropic emits the full redacted block as a single payload), so no event is yielded
- `content_block_stop` with no buffer entry is also a no-op

The provider thus silently skips redacted thinking — exactly matching the spec.

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
ruff check src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: all anthropic tests pass (including 4 new thinking tests); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider extended thinking support

- New constructor param thinking_budget: int | None = None
- When set, injects thinking={'type':'enabled','budget_tokens':N} into API call
- Parses SSE content_block_delta with type=thinking_delta → ProviderThinkingDelta
- redacted_thinking blocks naturally skipped (no special-case code needed)

4 new tests cover: budget passthrough, no-budget default, thinking_delta
emission, redacted_thinking silent."
```

---

## Task 7: `FakeRound.thinking` field + FakeLLMProvider emits ProviderThinkingDelta

**Files:**
- Modify: `src/meta_harney/providers/fake.py`
- Modify: existing tests in `tests/unit/providers/` (if any test the FakeLLMProvider behavior directly — otherwise rely on the integration test in Task 9)

- [ ] **Step 1: Modify `src/meta_harney/providers/fake.py`**

(a) Update `FakeRound` class — add `thinking: str | None = None` after `split_on`:

```python
class FakeRound(BaseModel):
    """One scripted LLM response."""

    text: str = ""
    split_on: str | None = None  # if set, text is split and each chunk emitted as a delta
    thinking: str | None = None  # if set, emits a ProviderThinkingDelta before text
    tool_calls: list[ProviderToolCall] = []
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None
```

(b) Update import block to bring in `ProviderThinkingDelta`:

```python
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

(c) Update `stream()` to emit thinking before text. Find:

```python
        round_ = self.rounds[self._index]
        self._index += 1

        # Emit text (chunked if split_on set)
        if round_.text:
```

Replace with:

```python
        round_ = self.rounds[self._index]
        self._index += 1

        # Emit thinking (if any) before any visible output
        if round_.thinking is not None:
            yield ProviderThinkingDelta(text=round_.thinking)

        # Emit text (chunked if split_on set)
        if round_.text:
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/ tests/integration/ -v 2>&1 | tail -10
ruff check src/meta_harney/providers/fake.py
mypy src/meta_harney/providers/fake.py
```

Expected: all prior tests still pass (additive change); clean.

- [ ] **Step 3: Commit**

```bash
git add src/meta_harney/providers/fake.py
git commit -m "feat(testing): FakeRound.thinking field

Adds optional 'thinking' to FakeRound (default None). When set,
FakeLLMProvider.stream() yields ProviderThinkingDelta before text.

Enables integration tests for ThinkingDelta engine passthrough."
```

---

## Task 8: Engine passthrough `ProviderThinkingDelta` → `StreamEvent.ThinkingDelta`

**Files:**
- Modify: `src/meta_harney/engine/loop.py`
- Modify: `tests/integration/test_engine_e2e.py` (add passthrough + history isolation scenario)

- [ ] **Step 1: Write failing test in `tests/integration/test_engine_e2e.py`**

Append (use the existing fixtures and imports already in this file; if `ThinkingDelta` is not imported, add it):

```python


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
```

Note: `rt._session_store` access works because `AgentRuntime` stores the session_store internally; if that attribute is private and a public accessor exists, use that instead. Check `src/meta_harney/runtime.py` to confirm. If `_session_store` is the attribute name, the leading underscore is just naming convention — direct access is fine for tests.

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_thinking_delta_passthrough_and_not_in_history -v
```

Expected: FAIL — engine currently doesn't translate `ProviderThinkingDelta` to `StreamEvent.ThinkingDelta`; the event is silently dropped (or worse, mishandled).

- [ ] **Step 3: Modify `src/meta_harney/engine/loop.py`**

(a) Update imports. Find:

```python
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
```

Add `ThinkingDelta`:

```python
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
```

And update the providers.base import:

```python
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

(b) Add an `elif` branch in the event-handling loop. Find:

```python
            for ev in provider_events:
                if isinstance(ev, ProviderTextDelta):
                    text_chunks.append(ev.text)
                    yield TextDelta(text=ev.text)
                elif isinstance(ev, ProviderToolCall):
                    tool_calls.append(ev)
                elif isinstance(ev, ProviderStreamDone):
                    stop_reason = ev.stop_reason
                    await emit_event(
                        ...
                    )
```

Insert a new `elif` for `ProviderThinkingDelta` BEFORE `ProviderToolCall`:

```python
            for ev in provider_events:
                if isinstance(ev, ProviderTextDelta):
                    text_chunks.append(ev.text)
                    yield TextDelta(text=ev.text)
                elif isinstance(ev, ProviderThinkingDelta):
                    # Passthrough: stream the thinking to the consumer, but do
                    # NOT append to text_chunks or assistant_blocks, and do not
                    # persist to session.messages.
                    yield ThinkingDelta(text=ev.text)
                elif isinstance(ev, ProviderToolCall):
                    tool_calls.append(ev)
                elif isinstance(ev, ProviderStreamDone):
                    stop_reason = ev.stop_reason
                    ...
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```

Expected: all integration tests pass (including the new one); clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/engine/loop.py tests/integration/test_engine_e2e.py
git commit -m "feat(engine): pass ProviderThinkingDelta through as StreamEvent.ThinkingDelta

ThinkingDelta is yielded to runtime.stream() consumers but never:
- appended to text_chunks
- appended to assistant_blocks
- persisted to session.messages

Integration test verifies both the passthrough and the history isolation."
```

---

## Task 9: Integration test — `tool-error-recovery` (spec §8.4 #2)

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

- [ ] **Step 1: Write the test**

Append to `tests/integration/test_engine_e2e.py`:

```python


async def test_tool_error_recovery_e2e() -> None:
    """Tool exception → ToolResult(success=False) → LLM recovers in next round.

    Spec §8.4 #2: agent calls a tool that raises; engine catches and feeds
    error back to LLM; LLM apologizes / gives a recovery response.
    """
    from pydantic import BaseModel

    from meta_harney.abstractions.tool import (
        BaseTool,
        ToolContext,
        ToolInvocation,
        ToolResult,
    )
    from meta_harney.providers.base import ProviderToolCall
    from meta_harney.testing import FakeRound, runtime_for_testing

    class _QueryInput(BaseModel):
        q: str

    class FlakyDBTool(BaseTool):
        name = "query_db"
        description = "Query the database."
        input_schema = _QueryInput

        async def execute(
            self, inv: ToolInvocation, ctx: ToolContext
        ) -> ToolResult:
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
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_tool_error_recovery_e2e -v
ruff check tests/integration/test_engine_e2e.py
mypy tests/integration/test_engine_e2e.py
```

Expected: PASS. No source-code changes were needed — engine's `_execute_after_permission` already wraps exceptions as `ToolResult(success=False)`, and the engine continues into round 2.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(integration): tool-error-recovery scenario (spec §8.4 #2)

Verifies the engine wraps a tool exception into ToolResult(success=False)
and continues the loop. LLM (FakeRound 2) emits a recovery response.
Final session.messages role sequence: [user, assistant, tool, assistant]."
```

---

## Task 10: Integration test — `multi-turn-session` (spec §8.4 #4)

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

- [ ] **Step 1: Write the test**

Append to `tests/integration/test_engine_e2e.py`:

```python


async def test_multi_turn_session_e2e() -> None:
    """Two consecutive invoke() calls share history (spec §8.4 #4).

    - Turn 1: user asks Q1, assistant answers A1
    - Turn 2: user asks Q2; provider sees [Q1, A1, Q2] as messages
    - Final session.messages = [user(Q1), assistant(A1), user(Q2), assistant(A2)]
    """
    from meta_harney.providers.fake import FakeLLMProvider, FakeRound
    from meta_harney.testing import runtime_for_testing

    rounds = [
        FakeRound(text="4", stop_reason="end_turn"),
        FakeRound(text="8", stop_reason="end_turn"),
    ]
    provider = FakeLLMProvider(rounds=rounds)

    # Build the runtime but inject our specific FakeLLMProvider so we can
    # inspect calls afterward
    rt = runtime_for_testing(scripted_rounds=rounds)
    # Replace the auto-created provider with our hand-built one so we can read .calls
    rt._provider = provider  # type: ignore[attr-defined]

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
```

Note: `runtime_for_testing` builds its own internal `FakeLLMProvider`. We override `rt._provider` with our hand-built instance so we can inspect `provider.calls` after the turns. If `AgentRuntime` stores the provider under a different attribute name, check `src/meta_harney/runtime.py` and adjust accordingly.

- [ ] **Step 2: RED → check**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_multi_turn_session_e2e -v
```

If FAIL: investigate. The mostly likely failure is the provider override — `runtime_for_testing` builds a new FakeLLMProvider internally. The override line must match the actual attribute name. Read `src/meta_harney/runtime.py` to confirm:
- If runtime stores it as `self._provider`, the test as written works.
- If as `self.provider`, change to `rt.provider = provider`.

Adjust the test accordingly. No source-code changes should be needed otherwise — multi-turn session continuity is already implemented (engine loads, appends, saves session each invoke).

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
ruff check tests/integration/test_engine_e2e.py
mypy tests/integration/test_engine_e2e.py
```

Expected: all integration tests pass; clean.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(integration): multi-turn-session scenario (spec §8.4 #4)

Two consecutive invoke() calls. Assert:
- Final session.messages role sequence: user, assistant, user, assistant
- Provider's second call sees the first turn's messages in history
- Each turn's text appears in the respective assistant message"
```

---

## Task 11: Expose `ProviderThinkingDelta` at top level + version bump to 0.0.6

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Modify `src/meta_harney/__init__.py`**

(a) Update module docstring. Find:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 5 status: OpenAIProvider (second real LLM backend) added alongside
AnthropicProvider. User-facing documentation shipped: README, architecture,
abstractions, providers, and testing reference docs.

Public surface:
- AgentRuntime facade (create_session, invoke, stream)
- LLMProvider Protocol + ProviderStreamEvent variants
- FakeLLMProvider + runtime_for_testing for SDK consumers' tests
- AnthropicProvider (optional 'anthropic' extra)
- OpenAIProvider (optional 'openai' extra)
- InProcessMultiAgentBackend
- 9 core abstractions + builtin defaults (Phase 1)
- StreamEvent types, RetryConfig, RuntimeConfig (Phase 2-3)
"""
```

Replace with:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 6 status: stabilization release.
- ToolResult.output serialization unified (helper in abstractions/_serialize)
- ProviderThinkingDelta event variant — Anthropic extended-thinking streaming
- Integration test coverage backfilled (tool-error-recovery, multi-turn-session)

Public surface:
- AgentRuntime facade (create_session, invoke, stream)
- LLMProvider Protocol + ProviderStreamEvent variants
- FakeLLMProvider + runtime_for_testing for SDK consumers' tests
- AnthropicProvider (optional 'anthropic' extra; supports thinking_budget)
- OpenAIProvider (optional 'openai' extra)
- InProcessMultiAgentBackend
- 9 core abstractions + builtin defaults (Phase 1)
- StreamEvent types, RetryConfig, RuntimeConfig (Phase 2-3)
"""
```

(b) Add `ProviderThinkingDelta` to the existing `from meta_harney.providers.base import (...)` block (alphabetical):

Find:
```python
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)
```

Replace with:
```python
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

(c) Update version:

Find `__version__ = "0.0.5"` and change to `__version__ = "0.0.6"`.

(d) Add `"ProviderThinkingDelta"` to `__all__` (alphabetically, between `ProviderTextDelta` and `ProviderToolCall`).

- [ ] **Step 2: Modify `pyproject.toml`**

Find `version = "0.0.5"` and change to `version = "0.0.6"`.

- [ ] **Step 3: Smoke test**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
assert mh.__version__ == '0.0.6'
assert mh.ProviderThinkingDelta
assert mh.AnthropicProvider
assert mh.OpenAIProvider
print('Exports:', len(mh.__all__))
print('OK')
"
```

Expected: `Exports: 55` (was 54 in v0.0.5), `OK`.

- [ ] **Step 4: Full quality gates**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -3
```

Expected: ~283 tests passing; mypy strict + ruff all clean. If `ruff format --check` reports diffs, apply `ruff format src/meta_harney tests` and commit those as a separate "style:" commit before the release commit.

- [ ] **Step 5: Commit + tag**

```bash
git add src/meta_harney/__init__.py pyproject.toml
git commit -m "release: bump version to 0.0.6 for Phase 6 milestone

Phase 6 deliverables:
- ToolResult.output serialization helper (None / dict / list / non-JSON)
- ProviderThinkingDelta event variant + Anthropic streaming support
- Engine passthrough (not into session history)
- Integration coverage: tool-error-recovery, multi-turn-session
- OpenAI RateLimitError catch-order comment

Phase 7 candidates: ThinkingDelta full mode (in history + multi-turn),
CRM mini-demo, CI matrix."

git tag -a v0.0.6 HEAD -m "meta-harney v0.0.6 — Phase 6 (Stabilize)

Builds on v0.0.5. Adds:

ToolResult.output serialization:
- Shared helper _serialize_tool_output(output) -> str
- Applied uniformly across AnthropicProvider + OpenAIProvider
- Fixes None -> '' (was 'None'), dict/list -> JSON (was Python repr)

Anthropic extended thinking (real-time stream only):
- AnthropicProvider(thinking_budget=N) opt-in
- SSE thinking_delta -> ProviderThinkingDelta -> StreamEvent.ThinkingDelta
- Not persisted to session.messages
- redacted_thinking blocks silently skipped

Integration test coverage:
- tool-error-recovery (spec §8.4 #2)
- multi-turn-session (spec §8.4 #4)
- ThinkingDelta passthrough + history-isolation

Quality:
- 283 tests passing (was 268)
- mypy strict + ruff check + ruff format all clean

Phase 7 candidates:
- ThinkingDelta full mode (signature/redacted, persisted, multi-turn tool_use)
- CRM mini-demo
- CI matrix (spec §8.6)"
```

---

## Phase 6 Completion Checklist

- [ ] `_serialize_tool_output` in `abstractions/_serialize.py` + 9 unit tests
- [ ] AnthropicProvider's ToolResultBlock branch uses the helper
- [ ] OpenAIProvider's ToolResultBlock branch uses the helper
- [ ] OpenAI `RateLimitError` catch-order comment in place
- [ ] `ProviderThinkingDelta` defined in `providers/base.py` and in `ProviderStreamEvent` union
- [ ] AnthropicProvider accepts `thinking_budget: int | None = None`
- [ ] AnthropicProvider injects `thinking={"type":"enabled","budget_tokens":N}` when budget is set
- [ ] AnthropicProvider parses `thinking_delta` SSE → `ProviderThinkingDelta`
- [ ] AnthropicProvider naturally skips `redacted_thinking` (no event, no error)
- [ ] `FakeRound.thinking: str | None = None` added; FakeLLMProvider emits `ProviderThinkingDelta`
- [ ] Engine has elif branch for `ProviderThinkingDelta` → `StreamEvent.ThinkingDelta`
- [ ] ThinkingDelta does NOT enter `session.messages`
- [ ] Integration test: `test_thinking_delta_passthrough_and_not_in_history`
- [ ] Integration test: `test_tool_error_recovery_e2e`
- [ ] Integration test: `test_multi_turn_session_e2e`
- [ ] `__version__ = "0.0.6"` and `pyproject.toml` version 0.0.6
- [ ] `ProviderThinkingDelta` in `meta_harney.__all__`
- [ ] All ~283 tests pass; mypy strict + ruff clean
- [ ] `v0.0.6` git tag on HEAD

---

## Self-Review

**Spec coverage:**
- §1 Goals item 1 (output serialization) → Tasks 1–3
- §1 Goals item 2 (RateLimitError comment) → Task 4
- §1 Goals item 3 (ThinkingDelta wiring) → Tasks 5, 6, 7, 8
- §1 Goals item 4 (tool-error-recovery integration) → Task 9
- §1 Goals item 5 (multi-turn-session integration) → Task 10
- §3 File Structure → Tasks 1–11 all map to declared files
- §4 APIs (helper, ProviderThinkingDelta, FakeRound.thinking, AnthropicProvider param) → Tasks 1, 5, 6, 7
- §5 Data flow → enforced by Tasks 8 (passthrough not-in-history) and Task 10 (multi-turn)
- §6 Error handling → Task 1 covers the helper's exception path; redacted_thinking covered in Task 6
- §7 Testing → all required user counts present (verified per task)
- §8 Version + tag → Task 11

**Placeholder scan:** No "TBD", "TODO", "implement later", "handle edge cases" without specifics. Every step has actual code or precise command.

**Type consistency:**
- `_serialize_tool_output(output: Any) -> str` — same signature in Tasks 1, 2, 3
- `ProviderThinkingDelta(text: str)` — same shape in Tasks 5, 6, 7, 8
- `FakeRound.thinking: str | None = None` — same default in Task 7, used in Task 8 + 9 + 10
- `AnthropicProvider.__init__(... thinking_budget: int | None = None)` — same signature in Task 6 (tests + impl)
- Engine import block extended in Task 8 with both `ThinkingDelta` (from stream_events) and `ProviderThinkingDelta` (from providers.base) — consistent with Task 5/7 names
