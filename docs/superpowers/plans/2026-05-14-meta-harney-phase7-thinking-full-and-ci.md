# meta-harney Phase 7: ThinkingDelta Full Mode + GitHub Remote/CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v0.0.7 — Anthropic extended-thinking content blocks (persisted + signature round-trip) and GitHub Actions matrix CI.

**Architecture:** Phase 7 has two independent workflows bundled into one release. **Workflow A** (code: 10 tasks) adds two new ContentBlock types and two new ProviderStreamEvent types, wires them through `AnthropicProvider` (emit + round-trip), engine (persist), and Fake provider (test fixture). Pydantic v2 discriminated union gives JSON round-trip "for free" — no changes needed in SessionStore implementations. **Workflow B** (infra: 6 tasks) creates the public GitHub repo `meta-harney`, configures CI matrix (3 Python × 2 OS = 6 jobs), and pushes the v0.0.7 tag.

**Tech Stack:** Python 3.10+ · Pydantic v2 discriminated union · anthropic SDK · openai SDK · pytest + pytest-asyncio · mypy strict · ruff · GitHub Actions · `gh` CLI.

**Pre-conditions:**
- On `main` at `cfbaf9f` (Phase 7 spec committed) or later
- Tests: 289 passing on v0.0.6
- mypy strict + ruff check + format all clean
- `gh` CLI installed and authenticated (will be verified in Task 11)

**Execution order:** Tasks 1–10 are pure code (Workflow A) and produce a green local checkout. Tasks 11–17 are Workflow B + release (involves irreversible `gh repo create` — Task 12 must explicitly confirm with user before pressing the button).

---

## File Structure After Phase 7

```
.github/                                              # NEW
├── workflows/
│   └── ci.yml
└── pull_request_template.md

src/meta_harney/
├── __init__.py                                       # MODIFIED — 4 new exports + 0.0.7
├── abstractions/
│   ├── __init__.py                                   # MODIFIED — re-export new blocks
│   └── _types.py                                     # MODIFIED — ThinkingBlock, RedactedThinkingBlock, discriminated union
├── providers/
│   ├── base.py                                       # MODIFIED — ProviderThinkingBlock, ProviderRedactedThinking, union
│   ├── anthropic.py                                  # MODIFIED — emit + round-trip
│   ├── openai.py                                     # MODIFIED — skip new blocks
│   └── fake.py                                       # MODIFIED — FakeRound.thinking_blocks + validator
└── engine/
    └── loop.py                                       # MODIFIED — handle new provider events

pyproject.toml                                        # MODIFIED — version 0.0.7 + [project.urls]
README.md                                             # MODIFIED — replace badges
```

---

## Workflow A — ThinkingDelta Full Mode (Tasks 1–10)

## Task 1: Add `ThinkingBlock` + `RedactedThinkingBlock` types

**Files:**
- Modify: `src/meta_harney/abstractions/_types.py`
- Modify: `src/meta_harney/abstractions/__init__.py`
- Modify: `tests/unit/abstractions/test_types.py`

- [ ] **Step 1: Append failing tests to `tests/unit/abstractions/test_types.py`**

```python


def test_thinking_block_construction() -> None:
    from meta_harney.abstractions._types import ThinkingBlock

    b = ThinkingBlock(text="reasoning", signature="sig-abc")
    assert b.type == "thinking"
    assert b.text == "reasoning"
    assert b.signature == "sig-abc"


def test_redacted_thinking_block_construction() -> None:
    from meta_harney.abstractions._types import RedactedThinkingBlock

    b = RedactedThinkingBlock(data="opaque-blob")
    assert b.type == "redacted_thinking"
    assert b.data == "opaque-blob"


def test_message_with_thinking_blocks_json_roundtrip() -> None:
    """Discriminated union must reconstruct concrete subclasses from JSON."""
    from meta_harney.abstractions._types import (
        Message,
        RedactedThinkingBlock,
        TextBlock,
        ThinkingBlock,
    )

    msg = Message(
        role="assistant",
        content=[
            ThinkingBlock(text="r", signature="s"),
            RedactedThinkingBlock(data="d"),
            TextBlock(text="final"),
        ],
    )
    j = msg.model_dump_json()
    parsed = Message.model_validate_json(j)
    assert isinstance(parsed.content[0], ThinkingBlock)
    assert parsed.content[0].signature == "s"
    assert isinstance(parsed.content[1], RedactedThinkingBlock)
    assert parsed.content[1].data == "d"
    assert isinstance(parsed.content[2], TextBlock)
    assert parsed.content[2].text == "final"


def test_content_block_discriminator_rejects_unknown_type() -> None:
    """Validation must fail when 'type' is not in the discriminator set."""
    import pytest
    from pydantic import ValidationError

    from meta_harney.abstractions._types import Message

    bad_json = '{"role":"assistant","content":[{"type":"unknown","whatever":1}]}'
    with pytest.raises(ValidationError):
        Message.model_validate_json(bad_json)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_types.py::test_thinking_block_construction \
       tests/unit/abstractions/test_types.py::test_redacted_thinking_block_construction \
       tests/unit/abstractions/test_types.py::test_message_with_thinking_blocks_json_roundtrip \
       tests/unit/abstractions/test_types.py::test_content_block_discriminator_rejects_unknown_type -v
```

Expected: ImportError on `ThinkingBlock` / `RedactedThinkingBlock`.

- [ ] **Step 3: Modify `src/meta_harney/abstractions/_types.py`**

Replace the entire file with:

```python
"""Shared data contracts: Content blocks and Message envelope.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.1.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class _ContentBlockBase(BaseModel):
    type: str


class TextBlock(_ContentBlockBase):
    type: Literal["text"] = "text"
    text: str


class ImageBlock(_ContentBlockBase):
    type: Literal["image"] = "image"
    url: str | None = None
    data: str | None = None  # base64
    media_type: str


class ToolCallBlock(_ContentBlockBase):
    type: Literal["tool_call"] = "tool_call"
    invocation_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(_ContentBlockBase):
    type: Literal["tool_result"] = "tool_result"
    invocation_id: str
    success: bool
    output: Any = None
    error: str | None = None


class ThinkingBlock(_ContentBlockBase):
    """Anthropic extended-thinking content, fully persisted.

    Carried in assistant Message.content to round-trip back to the provider
    on subsequent turns. Required for Anthropic's thinking-continuity check
    when extended thinking + tool_use is enabled.
    """

    type: Literal["thinking"] = "thinking"
    text: str
    signature: str


class RedactedThinkingBlock(_ContentBlockBase):
    """Opaque encrypted thinking payload from Anthropic.

    `data` is treated as a black box: we never decrypt, only round-trip.
    """

    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


ContentBlock = Annotated[
    TextBlock
    | ImageBlock
    | ToolCallBlock
    | ToolResultBlock
    | ThinkingBlock
    | RedactedThinkingBlock,
    Field(discriminator="type"),
]


class Message(BaseModel):
    """A single message in a session's history.

    `role` is constrained to the LLM wire vocabulary; `author` is a free-form
    business label (e.g., "sales", "customer") that provider adapters map to
    the wire (OpenAI: `name`; Anthropic: text prefix injection).
    """

    role: Literal["user", "assistant", "system", "tool"]
    author: str | None = None
    name: str | None = None  # OpenAI passthrough
    content: list[ContentBlock]
```

- [ ] **Step 4: Modify `src/meta_harney/abstractions/__init__.py`**

Find the `from meta_harney.abstractions._types import (...)` block. Add `ThinkingBlock` and `RedactedThinkingBlock` to it (alphabetically):

```python
from meta_harney.abstractions._types import (
    ContentBlock,
    ImageBlock,
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

Then in the `__all__` list, add `"ThinkingBlock"` and `"RedactedThinkingBlock"` (alphabetically).

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/abstractions/test_types.py -v
pytest -q
ruff check src/meta_harney/abstractions tests/unit/abstractions
mypy src/meta_harney/abstractions
```

Expected: 4 new tests pass; full suite still passes; clean.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/abstractions/_types.py src/meta_harney/abstractions/__init__.py tests/unit/abstractions/test_types.py
git commit -m "feat(abstractions): ThinkingBlock + RedactedThinkingBlock content blocks

ContentBlock is now a Pydantic v2 discriminated union (Field(discriminator='type')).
Gives JSON round-trip for free — SessionStore impls auto-handle the new types.

- ThinkingBlock(text, signature) — Anthropic extended-thinking content
- RedactedThinkingBlock(data) — opaque encrypted payload

4 new unit tests cover construction + JSON round-trip + discriminator rejection."
```

---

## Task 2: `ProviderThinkingBlock` + `ProviderRedactedThinking` events

**Files:**
- Modify: `src/meta_harney/providers/base.py`
- Modify: `tests/unit/providers/test_base.py`

- [ ] **Step 1: Append failing test to `tests/unit/providers/test_base.py`**

Append at the end of the file:

```python


def test_provider_thinking_block_construction() -> None:
    from meta_harney.providers.base import ProviderStreamEvent, ProviderThinkingBlock

    ev = ProviderThinkingBlock(text="reasoning", signature="sig")
    assert ev.text == "reasoning"
    assert ev.signature == "sig"
    assert ev.type == "thinking_block"

    def accepts(_: ProviderStreamEvent) -> None:
        pass

    accepts(ev)


def test_provider_redacted_thinking_construction() -> None:
    from meta_harney.providers.base import ProviderRedactedThinking, ProviderStreamEvent

    ev = ProviderRedactedThinking(data="opaque")
    assert ev.data == "opaque"
    assert ev.type == "redacted_thinking"

    def accepts(_: ProviderStreamEvent) -> None:
        pass

    accepts(ev)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_base.py -v
```

Expected: ImportError on `ProviderThinkingBlock` / `ProviderRedactedThinking`.

- [ ] **Step 3: Modify `src/meta_harney/providers/base.py`**

After the existing `ProviderThinkingDelta` class and before `ProviderStreamDone`, insert:

```python
class ProviderThinkingBlock(_ProviderStreamEventBase):
    """Complete thinking content block emitted at content_block_stop.

    Engine appends a ThinkingBlock to assistant message content. Distinct
    from ProviderThinkingDelta (which is the live-stream variant emitted
    incrementally and never persisted).
    """

    type: Literal["thinking_block"] = "thinking_block"
    text: str
    signature: str


class ProviderRedactedThinking(_ProviderStreamEventBase):
    """Opaque redacted-thinking block from Anthropic."""

    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str
```

Then update the union at line ~83:

```python
ProviderStreamEvent = (
    ProviderTextDelta
    | ProviderToolCall
    | ProviderThinkingDelta
    | ProviderThinkingBlock
    | ProviderRedactedThinking
    | ProviderStreamDone
)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_base.py -v
pytest -q
ruff check src/meta_harney/providers/base.py
mypy src/meta_harney/providers/base.py
```

Expected: 2 new pass; full suite still passes; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/base.py tests/unit/providers/test_base.py
git commit -m "feat(providers): ProviderThinkingBlock + ProviderRedactedThinking events

Provider-level companions to the new content-block types:
- ProviderThinkingBlock(text, signature) — emitted at content_block_stop
  for persistence in assistant message
- ProviderRedactedThinking(data) — emitted immediately on
  content_block_start for redacted_thinking blocks

Engine wiring follows in Task 8."
```

---

## Task 3: AnthropicProvider emits `ProviderThinkingBlock` + accumulates `signature_delta`

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

- [ ] **Step 1: Append failing test**

```python


async def test_anthropic_thinking_block_emit_with_signature_accumulation() -> None:
    """Provider buffers thinking_delta + signature_delta and emits one
    ProviderThinkingBlock at content_block_stop."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamEvent,
        ProviderThinkingBlock,
        ProviderThinkingDelta,
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "thinking"

    text_delta_1 = MagicMock()
    text_delta_1.type = "content_block_delta"
    text_delta_1.index = 0
    text_delta_1.delta = MagicMock()
    text_delta_1.delta.type = "thinking_delta"
    text_delta_1.delta.thinking = "let me "

    text_delta_2 = MagicMock()
    text_delta_2.type = "content_block_delta"
    text_delta_2.index = 0
    text_delta_2.delta = MagicMock()
    text_delta_2.delta.type = "thinking_delta"
    text_delta_2.delta.thinking = "think..."

    sig_delta_1 = MagicMock()
    sig_delta_1.type = "content_block_delta"
    sig_delta_1.index = 0
    sig_delta_1.delta = MagicMock()
    sig_delta_1.delta.type = "signature_delta"
    sig_delta_1.delta.signature = "sig-pa"

    sig_delta_2 = MagicMock()
    sig_delta_2.type = "content_block_delta"
    sig_delta_2.index = 0
    sig_delta_2.delta = MagicMock()
    sig_delta_2.delta.type = "signature_delta"
    sig_delta_2.delta.signature = "rt2"

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [
        cb_start, text_delta_1, text_delta_2, sig_delta_1, sig_delta_2, cb_stop, msg_stop,
    ]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
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

    # Live stream: 2 ProviderThinkingDelta (unchanged Phase 6 behavior)
    deltas = [e for e in collected if isinstance(e, ProviderThinkingDelta)]
    assert [d.text for d in deltas] == ["let me ", "think..."]

    # Persistence: exactly 1 ProviderThinkingBlock with concatenated text + signature
    blocks = [e for e in collected if isinstance(e, ProviderThinkingBlock)]
    assert len(blocks) == 1
    assert blocks[0].text == "let me think..."
    assert blocks[0].signature == "sig-part2"  # WRONG — fix below


# NOTE: the assertion above intentionally uses a wrong concatenation to fail.
# Actual concatenation is "sig-pa" + "rt2" = "sig-part2"
# (the value above is correct; preserve it).
```

Note on the assertion: signature_delta chunks concatenate verbatim. Two chunks `"sig-pa"` + `"rt2"` = `"sig-part2"`. The "WRONG" annotation in the comment was a typo — the assertion value `"sig-part2"` is actually correct. Treat the assertion as authoritative.

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_anthropic_thinking_block_emit_with_signature_accumulation -v
```

Expected: FAIL — no ProviderThinkingBlock is emitted; provider doesn't recognize signature_delta.

- [ ] **Step 3: Modify `src/meta_harney/providers/anthropic.py`**

(a) Add `ProviderThinkingBlock` to the import block:

```python
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingBlock,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

(b) Before the `async with client.messages.stream(...)` block, add a new buffer alongside `tool_use_buffer`:

Find:
```python
        # Per-tool-use streaming state: block_index → {"id":..., "name":..., "json_chunks":[...]}
        tool_use_buffer: dict[int, dict[str, Any]] = {}
```

Add immediately below:
```python
        # Per-thinking-block streaming state: block_index → {"text_chunks":[...], "signature_chunks":[...]}
        thinking_buffer: dict[int, dict[str, list[str]]] = {}
```

(c) Extend `content_block_start` handler. Find:

```python
                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[union-attr]
                        if getattr(block, "type", None) == "tool_use":
                            tool_use_buffer[event.index] = {  # type: ignore[union-attr]
                                "id": block.id,  # type: ignore[union-attr]
                                "name": block.name,  # type: ignore[union-attr]
                                "json_chunks": [],
                            }
```

Replace with:

```python
                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[union-attr]
                        block_type = getattr(block, "type", None)
                        if block_type == "tool_use":
                            tool_use_buffer[event.index] = {  # type: ignore[union-attr]
                                "id": block.id,  # type: ignore[union-attr]
                                "name": block.name,  # type: ignore[union-attr]
                                "json_chunks": [],
                            }
                        elif block_type == "thinking":
                            thinking_buffer[event.index] = {  # type: ignore[union-attr]
                                "text_chunks": [],
                                "signature_chunks": [],
                            }
```

(d) Extend `content_block_delta` handler. Find:

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

Replace with:

```python
                    elif etype == "content_block_delta":
                        delta = event.delta  # type: ignore[union-attr]
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta":
                            yield ProviderTextDelta(text=delta.text)  # type: ignore[union-attr]
                        elif dtype == "thinking_delta":
                            thinking_text = getattr(delta, "thinking", "")
                            yield ProviderThinkingDelta(text=thinking_text)
                            idx = event.index  # type: ignore[union-attr]
                            if idx in thinking_buffer:
                                thinking_buffer[idx]["text_chunks"].append(thinking_text)
                        elif dtype == "signature_delta":
                            idx = event.index  # type: ignore[union-attr]
                            if idx in thinking_buffer:
                                thinking_buffer[idx]["signature_chunks"].append(
                                    getattr(delta, "signature", "")
                                )
                        elif dtype == "input_json_delta":
                            idx = event.index  # type: ignore[union-attr]
                            if idx in tool_use_buffer:
                                tool_use_buffer[idx]["json_chunks"].append(delta.partial_json)  # type: ignore[union-attr]
```

(e) Extend `content_block_stop` handler. Find:

```python
                    elif etype == "content_block_stop":
                        idx = event.index  # type: ignore[union-attr]
                        if idx in tool_use_buffer:
                            buf = tool_use_buffer.pop(idx)
                            raw_json = "".join(buf["json_chunks"])
                            try:
                                parsed_args = json.loads(raw_json) if raw_json else {}
                            except json.JSONDecodeError:
                                parsed_args = {}
                            yield ProviderToolCall(
                                invocation_id=buf["id"],
                                name=buf["name"],
                                args=parsed_args,
                            )
```

Add an `elif idx in thinking_buffer:` branch:

```python
                    elif etype == "content_block_stop":
                        idx = event.index  # type: ignore[union-attr]
                        if idx in tool_use_buffer:
                            buf = tool_use_buffer.pop(idx)
                            raw_json = "".join(buf["json_chunks"])
                            try:
                                parsed_args = json.loads(raw_json) if raw_json else {}
                            except json.JSONDecodeError:
                                parsed_args = {}
                            yield ProviderToolCall(
                                invocation_id=buf["id"],
                                name=buf["name"],
                                args=parsed_args,
                            )
                        elif idx in thinking_buffer:
                            tbuf = thinking_buffer.pop(idx)
                            yield ProviderThinkingBlock(
                                text="".join(tbuf["text_chunks"]),
                                signature="".join(tbuf["signature_chunks"]),
                            )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
pytest -q
ruff check src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: new test passes; all prior tests still pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider emits ProviderThinkingBlock with signature

- Buffers thinking_delta text + signature_delta per block index
- At content_block_stop, emits ProviderThinkingBlock(text, signature)
- Existing live-stream ProviderThinkingDelta path unchanged (double-emit)

1 new test covers buffer accumulation + final emission."
```

---

## Task 4: AnthropicProvider emits `ProviderRedactedThinking`

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

- [ ] **Step 1: Append failing test**

```python


async def test_anthropic_redacted_thinking_emits_provider_event() -> None:
    """content_block_start with redacted_thinking → ProviderRedactedThinking immediately."""
    from unittest.mock import MagicMock, patch

    from meta_harney.abstractions._types import Message, TextBlock
    from meta_harney.providers.anthropic import AnthropicProvider
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderRedactedThinking,
        ProviderStreamEvent,
    )

    cb_start = MagicMock()
    cb_start.type = "content_block_start"
    cb_start.index = 0
    cb_start.content_block = MagicMock()
    cb_start.content_block.type = "redacted_thinking"
    cb_start.content_block.data = "opaque-blob-xyz"

    cb_stop = MagicMock()
    cb_stop.type = "content_block_stop"
    cb_stop.index = 0

    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    msg_stop.message = MagicMock()
    msg_stop.message.stop_reason = "end_turn"
    msg_stop.message.usage = None

    events: list[object] = [cb_start, cb_stop, msg_stop]

    class _FakeStreamCM:
        def __init__(self, evs: list[object]) -> None:
            self._evs = evs

        async def __aenter__(self) -> _FakeStreamCM:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        def __aiter__(self) -> _FakeStreamCM:
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

    redacted = [e for e in collected if isinstance(e, ProviderRedactedThinking)]
    assert len(redacted) == 1
    assert redacted[0].data == "opaque-blob-xyz"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_anthropic_redacted_thinking_emits_provider_event -v
```

Expected: FAIL — no event emitted for redacted_thinking.

- [ ] **Step 3: Modify `src/meta_harney/providers/anthropic.py`**

(a) Add `ProviderRedactedThinking` to the import block:

```python
from meta_harney.providers.base import (
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
```

(b) Extend the `content_block_start` handler again. Find:

```python
                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[union-attr]
                        block_type = getattr(block, "type", None)
                        if block_type == "tool_use":
                            tool_use_buffer[event.index] = {  # type: ignore[union-attr]
                                "id": block.id,  # type: ignore[union-attr]
                                "name": block.name,  # type: ignore[union-attr]
                                "json_chunks": [],
                            }
                        elif block_type == "thinking":
                            thinking_buffer[event.index] = {  # type: ignore[union-attr]
                                "text_chunks": [],
                                "signature_chunks": [],
                            }
```

Add a third branch:

```python
                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[union-attr]
                        block_type = getattr(block, "type", None)
                        if block_type == "tool_use":
                            tool_use_buffer[event.index] = {  # type: ignore[union-attr]
                                "id": block.id,  # type: ignore[union-attr]
                                "name": block.name,  # type: ignore[union-attr]
                                "json_chunks": [],
                            }
                        elif block_type == "thinking":
                            thinking_buffer[event.index] = {  # type: ignore[union-attr]
                                "text_chunks": [],
                                "signature_chunks": [],
                            }
                        elif block_type == "redacted_thinking":
                            yield ProviderRedactedThinking(
                                data=getattr(block, "data", "")
                            )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
pytest -q
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: new test + all prior anthropic tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider emits ProviderRedactedThinking

content_block_start with type=redacted_thinking → immediate yield of
ProviderRedactedThinking(data=<blob>). No deltas inside redacted blocks
so no buffering needed.

Phase 6's silent-skip behavior for redacted_thinking is now superseded:
the data is round-tripped via session.messages.

1 new test covers emission + data field passthrough."
```

---

## Task 5: AnthropicProvider round-trips `ThinkingBlock` + `RedactedThinkingBlock`

**Files:**
- Modify: `src/meta_harney/providers/anthropic.py`
- Modify: `tests/unit/providers/test_anthropic.py`

- [ ] **Step 1: Append failing tests**

```python


def test_convert_thinking_block_to_anthropic_wire_format() -> None:
    """ThinkingBlock in assistant content → {type:thinking,thinking,signature}."""
    from meta_harney.abstractions._types import Message, ThinkingBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="assistant",
            content=[ThinkingBlock(text="reasoning", signature="sig1")],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    content = converted[0]["content"]
    assert content[0] == {
        "type": "thinking",
        "thinking": "reasoning",
        "signature": "sig1",
    }


def test_convert_redacted_thinking_block_to_anthropic_wire_format() -> None:
    from meta_harney.abstractions._types import Message, RedactedThinkingBlock
    from meta_harney.providers.anthropic import _convert_messages_to_anthropic

    msgs = [
        Message(
            role="assistant",
            content=[RedactedThinkingBlock(data="opaque-xyz")],
        ),
    ]
    converted, _ = _convert_messages_to_anthropic(msgs)
    content = converted[0]["content"]
    assert content[0] == {"type": "redacted_thinking", "data": "opaque-xyz"}
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py::test_convert_thinking_block_to_anthropic_wire_format \
       tests/unit/providers/test_anthropic.py::test_convert_redacted_thinking_block_to_anthropic_wire_format -v
```

Expected: FAIL — `_convert_block` currently raises `ValueError("unknown content block type: ThinkingBlock")` for these.

- [ ] **Step 3: Modify `src/meta_harney/providers/anthropic.py`**

(a) Add to the imports from `meta_harney.abstractions._types`:

```python
from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

(b) Inside `_convert_block` (located in `_convert_messages_to_anthropic`), before the final `raise ValueError(...)` line, add two new branches:

Find:
```python
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": _serialize_tool_output(content),
            }
            if not block.success:
                result_block["is_error"] = True
            return result_block
        raise ValueError(f"unknown content block type: {type(block).__name__}")
```

Replace with:
```python
        if isinstance(block, ToolResultBlock):
            content = block.error if not block.success else block.output
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.invocation_id,
                "content": _serialize_tool_output(content),
            }
            if not block.success:
                result_block["is_error"] = True
            return result_block
        if isinstance(block, ThinkingBlock):
            return {
                "type": "thinking",
                "thinking": block.text,
                "signature": block.signature,
            }
        if isinstance(block, RedactedThinkingBlock):
            return {"type": "redacted_thinking", "data": block.data}
        raise ValueError(f"unknown content block type: {type(block).__name__}")
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_anthropic.py -v
pytest -q
ruff check src/meta_harney/providers/anthropic.py
mypy src/meta_harney/providers/anthropic.py
```

Expected: 2 new pass; all prior tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/anthropic.py tests/unit/providers/test_anthropic.py
git commit -m "feat(providers): AnthropicProvider round-trips ThinkingBlock + RedactedThinkingBlock

_convert_messages_to_anthropic now recognizes the two new content-block types
and emits Anthropic wire format:
- ThinkingBlock → {type:thinking, thinking, signature}
- RedactedThinkingBlock → {type:redacted_thinking, data}

Enables thinking continuity for multi-turn extended-thinking + tool_use flows.

2 new tests verify wire-format mapping."
```

---

## Task 6: OpenAIProvider skips new block types

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

- [ ] **Step 1: Append failing test**

```python


def test_openai_skips_thinking_and_redacted_blocks() -> None:
    """Assistant message containing ThinkingBlock + RedactedThinkingBlock is
    converted as if those blocks were not there. OpenAI Chat Completions
    has no concept of thinking blocks."""
    msgs = [
        Message(
            role="assistant",
            content=[
                ThinkingBlock(text="reasoning", signature="sig"),
                RedactedThinkingBlock(data="opaque"),
                TextBlock(text="visible answer"),
            ],
        ),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    # Single assistant message, content is the visible text only
    assert len(converted) == 1
    assert converted[0]["role"] == "assistant"
    assert converted[0]["content"] == "visible answer"
```

This test references `ThinkingBlock`, `RedactedThinkingBlock`, `Message`, `TextBlock`, `_convert_messages_to_openai`. Make sure all of these are imported at the top of the file (the existing imports already include `Message` and `TextBlock`; `_convert_messages_to_openai` is already imported; just add the new block types to the existing `meta_harney.abstractions._types` import block):

```python
from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py::test_openai_skips_thinking_and_redacted_blocks -v
```

Expected: FAIL — currently OpenAIProvider falls through the user/assistant block loop without matching ThinkingBlock; it might either (a) raise an exception in a downstream branch or (b) silently produce a malformed message. Either way the assertion fails.

- [ ] **Step 3: Modify `src/meta_harney/providers/openai.py`**

(a) Add the new block types to the existing `from meta_harney.abstractions._types import (...)` block. (If the imports already include `ImageBlock`, `Message`, `TextBlock`, `ToolCallBlock`, `ToolResultBlock`, just add `RedactedThinkingBlock` and `ThinkingBlock`.)

(b) Locate the user/assistant message handling loop in `_convert_messages_to_openai`. It iterates `for block in msg.content:` and dispatches on `isinstance(block, ...)`. Find the chain (it follows after the `if msg.role == "tool":` block):

```python
        for block in msg.content:
            if isinstance(block, TextBlock):
                ...
            elif isinstance(block, ImageBlock):
                ...
            elif isinstance(block, ToolCallBlock):
                ...
```

(Exact code may differ slightly; the actual file is the source of truth.)

Add a branch that skips ThinkingBlock and RedactedThinkingBlock. Append to the chain:

```python
            elif isinstance(block, (ThinkingBlock, RedactedThinkingBlock)):
                # OpenAI Chat Completions has no thinking concept; skip silently.
                continue
```

If the existing chain has no `elif`-tail catch-all that would mishandle unknown blocks, this is purely additive. If there's a `raise` for unknown types, the new branch matches before that and prevents it.

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
pytest -q
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: new test passes; all prior tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAIProvider skips ThinkingBlock / RedactedThinkingBlock

OpenAI Chat Completions has no analog to Anthropic's thinking blocks.
When converting assistant messages that mix thinking + text content,
the thinking blocks are silently dropped.

This means a session that has interacted with Anthropic and is later
queried through OpenAIProvider won't replay thinking content — which
is the correct behavior (OpenAI cannot consume or verify it).

1 new test covers the skip path."
```

---

## Task 7: `FakeRound.thinking_blocks` + FakeLLMProvider emit + mutual-exclusion validator

**Files:**
- Modify: `src/meta_harney/providers/fake.py`
- Modify: `tests/unit/providers/test_fake.py`

- [ ] **Step 1: Append failing tests to `tests/unit/providers/test_fake.py`**

```python


async def test_fake_round_emits_provider_thinking_block_from_thinking_blocks() -> None:
    """FakeRound.thinking_blocks → ProviderThinkingBlock events."""
    from meta_harney.abstractions._types import Message, TextBlock, ThinkingBlock
    from meta_harney.providers.base import (
        ProviderCallConfig,
        ProviderStreamEvent,
        ProviderThinkingBlock,
    )
    from meta_harney.providers.fake import FakeLLMProvider, FakeRound

    provider = FakeLLMProvider(
        rounds=[
            FakeRound(
                thinking_blocks=[
                    ThinkingBlock(text="step 1", signature="s1"),
                    ThinkingBlock(text="step 2", signature="s2"),
                ],
                text="Done",
                stop_reason="end_turn",
            )
        ]
    )
    collected: list[ProviderStreamEvent] = []
    async for ev in provider.stream(
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        system_prompt="",
        tools=[],
        config=ProviderCallConfig(model="test"),
    ):
        collected.append(ev)

    blocks = [e for e in collected if isinstance(e, ProviderThinkingBlock)]
    assert len(blocks) == 2
    assert blocks[0].text == "step 1"
    assert blocks[0].signature == "s1"
    assert blocks[1].text == "step 2"
    assert blocks[1].signature == "s2"


def test_fake_round_thinking_and_thinking_blocks_mutually_exclusive() -> None:
    """Setting both .thinking and .thinking_blocks raises validation error."""
    import pytest
    from pydantic import ValidationError

    from meta_harney.abstractions._types import ThinkingBlock
    from meta_harney.providers.fake import FakeRound

    with pytest.raises(ValidationError, match="thinking"):
        FakeRound(
            thinking="live stream text",
            thinking_blocks=[ThinkingBlock(text="x", signature="s")],
        )
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_fake.py -v
```

Expected: FAIL — `FakeRound` doesn't have `thinking_blocks` field.

- [ ] **Step 3: Modify `src/meta_harney/providers/fake.py`**

(a) Update the import from `meta_harney.abstractions._types`. If the module doesn't already import `ThinkingBlock`, add it:

```python
from meta_harney.abstractions._types import Message, ThinkingBlock
```

(b) Update the import from `meta_harney.providers.base` to include `ProviderThinkingBlock`:

```python
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingBlock,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

(c) Update the `FakeRound` class to add `thinking_blocks` and the mutual-exclusion validator. Find:

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

Replace with:

```python
class FakeRound(BaseModel):
    """One scripted LLM response."""

    text: str = ""
    split_on: str | None = None  # if set, text is split and each chunk emitted as a delta
    thinking: str | None = None  # if set, emits a ProviderThinkingDelta before text
    thinking_blocks: list[ThinkingBlock] = []
    tool_calls: list[ProviderToolCall] = []
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None

    @model_validator(mode="after")
    def _check_thinking_exclusive(self) -> FakeRound:
        if self.thinking is not None and self.thinking_blocks:
            raise ValueError(
                "FakeRound: set either 'thinking' (live-stream sugar) or "
                "'thinking_blocks' (persisted), not both"
            )
        return self
```

Add `model_validator` to the pydantic imports at the top of the file:

```python
from pydantic import BaseModel, model_validator
```

(d) Update `FakeLLMProvider.stream()` to emit `ProviderThinkingBlock` for each item in `thinking_blocks`. The emission order is: live `thinking` (Phase 6 sugar) → `thinking_blocks` (Phase 7 persisted) → text → tool_calls → stream_done.

Find:

```python
        round_ = self.rounds[self._index]
        self._index += 1

        # Emit thinking (if any) before any visible output
        if round_.thinking is not None:
            yield ProviderThinkingDelta(text=round_.thinking)

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
        for tb in round_.thinking_blocks:
            yield ProviderThinkingBlock(text=tb.text, signature=tb.signature)

        # Emit text (chunked if split_on set)
        if round_.text:
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_fake.py -v
pytest -q
ruff check src/meta_harney/providers/fake.py
mypy src/meta_harney/providers/fake.py
```

Expected: 2 new tests pass; all prior tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/fake.py tests/unit/providers/test_fake.py
git commit -m "feat(testing): FakeRound.thinking_blocks for persisted-thinking tests

- Adds 'thinking_blocks: list[ThinkingBlock]' field (Phase 7 persisted path)
- Existing 'thinking: str | None' kept as Phase 6 live-stream syntax sugar
- model_validator enforces mutual exclusion of the two fields
- FakeLLMProvider.stream() emits ProviderThinkingBlock for each entry

Enables multi-turn integration tests for thinking + tool_use flow."
```

---

## Task 8: Engine appends new provider events to `assistant_blocks`

**Files:**
- Modify: `src/meta_harney/engine/loop.py`

(Integration test for this path is added in Task 10; this task is purely structural and depends on Tasks 1, 2, 7 already in place.)

- [ ] **Step 1: Add a smoke test in `tests/unit/providers/test_fake.py`** (lightweight unit-level check that the engine correctly maps events without needing a full e2e fixture)

Actually skip the unit-level smoke test here — Task 10's integration test covers this end-to-end and a unit smoke test would just duplicate. Proceed directly to the engine change.

- [ ] **Step 2: Modify `src/meta_harney/engine/loop.py`**

(a) Extend the imports. Find:

```python
from meta_harney.abstractions._types import (
    ContentBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

Add `RedactedThinkingBlock` and `ThinkingBlock`:

```python
from meta_harney.abstractions._types import (
    ContentBlock,
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

(b) Update the providers.base import to include the two new event types:

```python
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
```

(c) Add two new branches to the provider event dispatch loop. Find:

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
```

Replace with (the new branches go between `ProviderThinkingDelta` and `ProviderToolCall`):

```python
            thinking_blocks_buf: list[ThinkingBlock | RedactedThinkingBlock] = []

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
                    thinking_blocks_buf.append(
                        ThinkingBlock(text=ev.text, signature=ev.signature)
                    )
                elif isinstance(ev, ProviderRedactedThinking):
                    thinking_blocks_buf.append(RedactedThinkingBlock(data=ev.data))
                elif isinstance(ev, ProviderToolCall):
                    tool_calls.append(ev)
                elif isinstance(ev, ProviderStreamDone):
```

(d) When assembling `assistant_blocks` (after the loop), prepend the thinking_blocks_buf so they appear first in content (matching Anthropic's natural order: thinking → text → tool_use). Find:

```python
            assistant_blocks: list[ContentBlock] = []
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
```

Replace with:

```python
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
```

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest -q
ruff check src/meta_harney/engine/loop.py
mypy src/meta_harney/engine/loop.py
```

Expected: all tests still pass; clean. (No new tests yet — Task 10's integration test will exercise this path.)

- [ ] **Step 4: Commit**

```bash
git add src/meta_harney/engine/loop.py
git commit -m "feat(engine): persist ThinkingBlock + RedactedThinkingBlock to session.messages

Adds new branches to the provider event loop:
- ProviderThinkingBlock → ThinkingBlock buffered, appended to assistant_blocks
- ProviderRedactedThinking → RedactedThinkingBlock buffered, appended

Assistant message content order: thinking* → text? → tool_call*
(matches Anthropic's natural emission order).

Phase 6's live-stream ProviderThinkingDelta passthrough is unchanged.
Integration test for the full flow comes in Task 10."
```

---

## Task 9: SessionStore JSON round-trip verification

**Files:**
- Modify: `tests/unit/builtin/test_session.py` (verify path — should require no source-code changes)

This task is a verification step: Pydantic v2 discriminated unions should serialize and deserialize the new block types automatically. We add one test to prove it.

- [ ] **Step 1: Append failing test to `tests/unit/builtin/test_session.py`**

Look at the existing tests to find a session_store fixture pattern. The test pattern below assumes `MemorySessionStore` is the basic in-memory impl and that there's a similar test for `FileSessionStore`.

```python


async def test_memory_session_store_roundtrips_thinking_blocks() -> None:
    """ThinkingBlock + RedactedThinkingBlock survive save/load cycle."""
    from meta_harney.abstractions._types import (
        Message,
        RedactedThinkingBlock,
        TextBlock,
        ThinkingBlock,
    )
    from meta_harney.abstractions.session import Session
    from meta_harney.builtin.session.memory_store import MemorySessionStore

    store = MemorySessionStore()
    session = Session(id="s1")
    session.messages.append(
        Message(
            role="assistant",
            content=[
                ThinkingBlock(text="reasoning", signature="sig"),
                RedactedThinkingBlock(data="opaque"),
                TextBlock(text="answer"),
            ],
        )
    )
    await store.save(session)
    loaded = await store.load("s1")
    assert loaded is not None
    msg = loaded.messages[0]
    assert isinstance(msg.content[0], ThinkingBlock)
    assert msg.content[0].text == "reasoning"
    assert msg.content[0].signature == "sig"
    assert isinstance(msg.content[1], RedactedThinkingBlock)
    assert msg.content[1].data == "opaque"
    assert isinstance(msg.content[2], TextBlock)


async def test_file_session_store_roundtrips_thinking_blocks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """ThinkingBlock + RedactedThinkingBlock survive JSON-file save/load."""
    from meta_harney.abstractions._types import (
        Message,
        RedactedThinkingBlock,
        TextBlock,
        ThinkingBlock,
    )
    from meta_harney.abstractions.session import Session
    from meta_harney.builtin.session.file_store import FileSessionStore

    store = FileSessionStore(root=tmp_path)
    session = Session(id="s1")
    session.messages.append(
        Message(
            role="assistant",
            content=[
                ThinkingBlock(text="reasoning", signature="sig"),
                RedactedThinkingBlock(data="opaque"),
            ],
        )
    )
    await store.save(session)
    loaded = await store.load("s1")
    assert loaded is not None
    assert isinstance(loaded.messages[0].content[0], ThinkingBlock)
    assert loaded.messages[0].content[0].signature == "sig"
    assert isinstance(loaded.messages[0].content[1], RedactedThinkingBlock)
```

Note: `FileSessionStore`'s constructor argument name is `root` per inspection of `src/meta_harney/builtin/session/file_store.py`. If the actual name differs (e.g., `root_dir`), adjust accordingly. The `tmp_path` fixture is provided by pytest.

Also: `Session` may need additional required fields (e.g., `version`, `created_at`). Check `src/meta_harney/abstractions/session.py` and adjust the `Session(id="s1")` constructor accordingly — likely needs to either provide defaults or use the `Session(id="s1", tenant_id=None, user_id=None, ...)` signature. If `Session` is a Pydantic BaseModel with reasonable defaults, the bare construction should work.

- [ ] **Step 2: RED → ideally GREEN**

```bash
source .venv/bin/activate
pytest tests/unit/builtin/test_session.py -v -k "thinking"
```

Expected: PASS on the first try. If FAIL:
- Adjust constructor signatures based on actual `Session` / `FileSessionStore` defaults
- If `Session.id` needs a different positional arg or factory, use `Session.model_construct(...)` or the actual factory pattern from existing tests

If still FAIL after constructor fixes, this likely indicates a real bug in the discriminated union setup from Task 1 — debug there.

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest -q
ruff check tests/unit/builtin/test_session.py
mypy tests/unit/builtin/test_session.py
```

Expected: all tests pass; clean.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/builtin/test_session.py
git commit -m "test(builtin): SessionStore roundtrips ThinkingBlock + RedactedThinkingBlock

Verifies Pydantic v2 discriminated union (Task 1) gives JSON round-trip
for free — no changes needed in MemorySessionStore or FileSessionStore.

2 new tests cover both backends."
```

---

## Task 10: Integration test — thinking + tool_use multi-turn persistence

**Files:**
- Modify: `tests/integration/test_engine_e2e.py`

- [ ] **Step 1: Append failing test**

```python


async def test_thinking_plus_tool_use_multi_turn_persistence_e2e() -> None:
    """End-to-end: thinking_blocks persist to session.messages and get
    round-tripped to the provider on the next turn (Phase 7 full mode)."""
    from pydantic import BaseModel

    from meta_harney.abstractions._types import Message, ThinkingBlock
    from meta_harney.abstractions.tool import (
        BaseTool,
        ToolContext,
        ToolInvocation,
        ToolResult,
    )
    from meta_harney.providers.base import ProviderToolCall
    from meta_harney.providers.fake import FakeLLMProvider, FakeRound
    from meta_harney.testing import runtime_for_testing

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
    rt._provider = provider  # type: ignore[attr-defined]

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
    # The assistant message in second_call_msgs should contain the ThinkingBlock
    assistant_msgs = [m for m in second_call_msgs if m.role == "assistant"]
    assert any(
        any(isinstance(b, ThinkingBlock) for b in m.content) for m in assistant_msgs
    ), "second turn should include ThinkingBlock in history"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py::test_thinking_plus_tool_use_multi_turn_persistence_e2e -v
```

Expected: if Tasks 1, 2, 7, 8 are all in place, this should PASS. Failure modes to debug if not:
- ThinkingBlock not in `assistant_blocks` → Task 8 not applied
- ThinkingBlock not in `second_call.messages` → PromptBuilder doesn't include it (unlikely — it just loads session.messages); or session.messages reloaded between turns doesn't contain it (Task 9 failure)
- ToolResult issues → unrelated, probably a Phase 6 regression

- [ ] **Step 3: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_engine_e2e.py -v
pytest -q
ruff check tests/integration/test_engine_e2e.py
mypy tests/integration/test_engine_e2e.py
```

Expected: all integration tests pass; clean.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_engine_e2e.py
git commit -m "test(integration): thinking + tool_use multi-turn persistence (Phase 7 e2e)

Verifies the complete persisted-thinking flow:
- Round 1: assistant emits ThinkingBlock + ToolCallBlock → engine persists,
  executes tool, continues iteration
- Round 2: provider receives the prior turn's ThinkingBlock in history
- Final session.messages sequence: [user, assistant, tool, assistant]
- ThinkingBlock signature preserved through save/load cycle"
```

---

## Workflow B — GitHub Remote + CI Matrix (Tasks 11–17)

## Task 11: pyproject.toml `[project.urls]` (deferred until repo URL known)

This task is structurally part of release prep but its content depends on the actual GitHub URL. **Skip writing URLs here; integrate in Task 15 (README+pyproject badges) after repo is created in Task 12.**

For now, just update the module docstring in `src/meta_harney/__init__.py`:

- [ ] **Step 1: Modify `src/meta_harney/__init__.py`**

Find:
```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 6 status: stabilization release.
- ToolResult.output serialization unified (helper in abstractions/_serialize)
- ProviderThinkingDelta event variant — Anthropic extended-thinking streaming
- Integration test coverage backfilled (tool-error-recovery, multi-turn-session)
"""
```

Replace with:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 7 status: extended-thinking full mode + GitHub Actions CI.
- ThinkingBlock + RedactedThinkingBlock content blocks (persisted, round-tripped)
- ProviderThinkingBlock + ProviderRedactedThinking stream events
- AnthropicProvider buffers thinking_delta + signature_delta, emits at content_block_stop
- Engine appends thinking blocks to assistant Message.content (entering session.messages)
- OpenAIProvider silently skips thinking blocks (no concept)
- GitHub repo + Actions CI matrix (Python 3.10/3.11/3.12 × ubuntu/macos)
"""
```

(The "Public surface" block below the docstring is unchanged — Task 17 will add the 4 new exports there alongside the version bump.)

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest -q
```

Expected: 302 tests pass (289 from v0.0.6 + 13 from Phase 7 Workflow A).

- [ ] **Step 3: Commit**

```bash
git add src/meta_harney/__init__.py
git commit -m "docs: update meta_harney module docstring for Phase 7

Reflects the new thinking-blocks persistence path and the upcoming
GitHub Actions CI. __version__ + __all__ updates land in Task 17 alongside
the v0.0.7 tag."
```

---

## Task 12: Create GitHub remote (interactive confirmation step)

**Files:** none (executes commands only)

This is the irreversible action. The implementer **must explicitly confirm** with the user before pressing the button. There is no automated answer for this task.

- [ ] **Step 1: Verify `gh` CLI authentication**

```bash
gh auth status
```

Expected: shows logged-in account.

If not authenticated, **stop** and tell the user:
> "Please run `gh auth login` in your shell, then continue this plan."

- [ ] **Step 2: Capture the GitHub username**

```bash
GH_USER=$(gh api user --jq .login)
echo "GitHub user: $GH_USER"
```

Store the resulting value — it's needed for the `[project.urls]` section in Task 15 and for the badge URLs.

- [ ] **Step 3: Confirm with the user before creating the public repo**

Show the exact command that will run:

```
gh repo create $GH_USER/meta-harney --public \
  --description "Domain-agnostic agent runtime SDK with Pydantic-based abstractions" \
  --source=. --remote=origin --push
```

Ask:
> "About to create the **public** GitHub repo `<GH_USER>/meta-harney` and push all local commits + tags. This is irreversible (public visibility). OK to proceed?"

**Wait for explicit user confirmation.** If the user says no, ask what to do (use a different repo name? make private? skip?).

- [ ] **Step 4: Run the repo creation**

```bash
gh repo create $GH_USER/meta-harney --public \
  --description "Domain-agnostic agent runtime SDK with Pydantic-based abstractions" \
  --source=. --remote=origin --push
```

This creates the repo, adds `origin` as remote, and pushes the current branch.

- [ ] **Step 5: Push tags**

```bash
git push --tags
```

Pushes existing tags (`v0.0.1` through `v0.0.6`) to origin.

- [ ] **Step 6: Verify**

```bash
git remote -v
gh repo view $GH_USER/meta-harney --json url,visibility,defaultBranchRef
```

Expected: remote `origin` points to the new repo; repo is `PUBLIC`; default branch is `main`.

- [ ] **Step 7: No git commit needed**

This task only creates remote state and adjusts local git config (no working-tree changes). Move to Task 13.

---

## Task 13: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create directory and file**

```bash
mkdir -p .github/workflows
```

Then create `.github/workflows/ci.yml` with the following content:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Python ${{ matrix.python-version }} on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev,anthropic,openai]"

      - name: Run pytest
        run: pytest -q

      - name: Run mypy (src)
        run: mypy src/meta_harney

      - name: Run mypy (tests)
        run: mypy tests

      - name: Run ruff check
        run: ruff check src tests

      - name: Run ruff format check
        run: ruff format --check src tests
```

- [ ] **Step 2: Validate YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`. (No yaml-cli dependency needed; uses stdlib PyYAML via `python -c`. If PyYAML is not available, skip this step — GitHub will validate at push time.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions matrix workflow (Python 3.10/3.11/3.12 × ubuntu/macos)

Runs on push/PR to main:
- pytest (full suite, asyncio auto-mode)
- mypy src/meta_harney (strict)
- mypy tests (strict)
- ruff check src tests
- ruff format --check src tests

fail-fast: false → all 6 jobs report independently
No coverage threshold (measured but unenforced; spec §8.6 80% to be
established once baseline data is collected)."
```

- [ ] **Step 4: Push and verify CI runs**

```bash
git push origin main
```

Then watch the workflow status:

```bash
gh run watch
```

Expected: all 6 jobs (3 Python × 2 OS) pass. If any fails, investigate before proceeding to next task.

If a job fails on a specific Python version due to a real bug, fix it in a follow-up commit (no need to revert this commit). If it fails on a CI-environment issue (e.g., dependency resolution), debug and amend.

---

## Task 14: PR template

**Files:**
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Create `.github/pull_request_template.md`**

```markdown
## Summary

<!-- 2-3 bullet points describing what changed and why -->

-
-

## Test plan

- [ ] All CI checks pass (pytest × 6 jobs, mypy, ruff)
- [ ] Manual verification (if applicable): <describe>
- [ ] Updated tests for new behavior
- [ ] Updated docs/CHANGELOG if user-facing

## Notes

<!-- Optional: design rationale, alternatives considered, follow-ups -->
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/pull_request_template.md
git commit -m "ci: add pull request template

Standard sections: Summary, Test plan checklist, Notes.
Reminds contributors to verify CI passes and update tests/docs."
git push origin main
```

---

## Task 15: Update README badges + pyproject `[project.urls]`

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Determine the GitHub username**

```bash
GH_USER=$(gh api user --jq .login)
```

(If shell session was lost from Task 12, re-fetch.)

- [ ] **Step 2: Modify `README.md` badges**

Find the existing 3 placeholder badges at the top:

```markdown
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#testing-your-agent)
```

Replace with (substituting `<GH_USER>` for the actual GitHub username — write the literal username in the file, not a shell variable):

```markdown
[![CI](https://github.com/<GH_USER>/meta-harney/actions/workflows/ci.yml/badge.svg)](https://github.com/<GH_USER>/meta-harney/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
```

- [ ] **Step 3: Modify `pyproject.toml`**

Find the `[project]` block. After the `authors = [...]` line and before `dependencies = [`, add a new `[project.urls]` section:

```toml
[project.urls]
Homepage = "https://github.com/<GH_USER>/meta-harney"
Repository = "https://github.com/<GH_USER>/meta-harney"
Issues = "https://github.com/<GH_USER>/meta-harney/issues"
```

(Again, substitute the literal username for `<GH_USER>`.)

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pip install -e ".[dev]" --quiet
python -c "import meta_harney; print(meta_harney.__version__)"
```

Expected: prints `0.0.6` (version bump comes in Task 17). The pyproject change is metadata only — doesn't affect import.

- [ ] **Step 5: Commit and push**

```bash
git add README.md pyproject.toml
git commit -m "docs: replace README badges with GitHub Actions + project URLs

- README badges now point to the real CI workflow + license + python version
- pyproject [project.urls] populated with Homepage/Repository/Issues

Substituted <user>/meta-harney everywhere a placeholder existed."
git push origin main
```

Then watch CI again to confirm nothing broke:

```bash
gh run watch
```

---

## Task 16: Verify CI is green on main

**Files:** none

- [ ] **Step 1: Inspect the latest workflow run**

```bash
gh run list --workflow=ci.yml --limit 1
gh run view --log-failed 2>/dev/null || echo "no failures"
```

- [ ] **Step 2: If any job failed**

Investigate the specific failing job. Common failure modes:
- Some Python version doesn't have `anthropic` or `openai` SDK in its install path → check `pyproject.toml` version constraints.
- macOS-specific test failure → likely real bug; fix locally and push.
- mypy version mismatch → pin or update `dev` extra in pyproject.

Fix and push until all 6 jobs are green.

- [ ] **Step 3: If all green**

Move to Task 17.

(No commit for this task unless a fix was needed.)

---

## Task 17: v0.0.7 release — version bump + 4 new exports + tag

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Modify `src/meta_harney/__init__.py`**

(a) Find the imports from `meta_harney.abstractions` and add `ThinkingBlock` + `RedactedThinkingBlock`:

```python
from meta_harney.abstractions import (
    AgentSpec,
    BaseHook,
    BaseTask,
    BaseTool,
    CompactionStrategy,
    ContentBlock,
    HookDecision,
    HookEvent,
    HookEventKind,
    ImageBlock,
    Message,
    MultiAgentBackend,
    PermissionDecision,
    PermissionResolver,
    PromptBuilder,
    RedactedThinkingBlock,
    Session,
    SessionStore,
    SpawnHandle,
    TaskState,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolContext,
    ToolInvocation,
    ToolResult,
    ToolResultBlock,
    TraceEvent,
    TraceSink,
)
```

(b) Find the imports from `meta_harney.providers.base` and add `ProviderRedactedThinking` + `ProviderThinkingBlock`:

```python
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
```

(c) Update version:

Find `__version__ = "0.0.6"` and change to `__version__ = "0.0.7"`.

(d) Update `__all__`. Insert (alphabetically) the 4 new names:

- `"ProviderRedactedThinking"` between `"ProviderTextDelta"` and `"ProviderThinkingDelta"`
- `"ProviderThinkingBlock"` between `"ProviderThinkingDelta"` and `"ProviderToolCall"`
- `"RedactedThinkingBlock"` (find appropriate alphabetical slot — likely between `"PromptBuilder"`-style entries and `"RetryConfig"`; check the actual ordering)
- `"ThinkingBlock"` (alphabetical slot — between `"TextDelta"` and `"ToolCallBlock"` or wherever appropriate)

If unsure of exact positions, run `ruff check --fix src/meta_harney/__init__.py` after editing; ruff's `RUF022` rule sorts `__all__`.

- [ ] **Step 2: Modify `pyproject.toml`**

Find `version = "0.0.6"` and change to `version = "0.0.7"`.

- [ ] **Step 3: Smoke test**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
assert mh.__version__ == '0.0.7', mh.__version__
assert mh.ThinkingBlock
assert mh.RedactedThinkingBlock
assert mh.ProviderThinkingBlock
assert mh.ProviderRedactedThinking
print('Version:', mh.__version__)
print('Exports:', len(mh.__all__))
print('OK')
"
```

Expected: `Version: 0.0.7`, `Exports: 59` (55 from v0.0.6 + 4 new), `OK`.

- [ ] **Step 4: Run all quality gates**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -3
```

Expected: 302 tests pass; mypy + ruff all clean. If `ruff format --check` shows diffs, run `ruff format src tests` and commit those as a separate style-only commit before continuing.

- [ ] **Step 5: Commit + tag + push**

```bash
git add src/meta_harney/__init__.py pyproject.toml
git commit -m "release: bump version to 0.0.7 for Phase 7 milestone

Phase 7 deliverables:
- ThinkingBlock + RedactedThinkingBlock content blocks (persisted)
- ProviderThinkingBlock + ProviderRedactedThinking stream events
- AnthropicProvider: signature_delta accumulation + ProviderThinkingBlock
  emission + history round-trip
- OpenAIProvider: silently skip new block types
- FakeRound.thinking_blocks for persisted-thinking integration tests
- Engine writes thinking blocks to assistant Message.content
- SessionStore round-trips via Pydantic v2 discriminated union
- GitHub Actions CI: matrix 3.10/3.11/3.12 × ubuntu/macos

Phase 8 candidates: PyPI release flow, coverage threshold (after
baseline collection), release.yml automation, Windows matrix."

git tag -a v0.0.7 HEAD -m "meta-harney v0.0.7 — Phase 7 (Thinking Full Mode + CI)

Builds on v0.0.6. Adds:

Anthropic extended-thinking full mode:
- ThinkingBlock(text, signature) + RedactedThinkingBlock(data) ContentBlock types
- ProviderThinkingBlock + ProviderRedactedThinking stream events
- AnthropicProvider buffers thinking_delta + signature_delta and emits at content_block_stop
- _convert_messages_to_anthropic round-trips both block types in wire format
- Engine persists to assistant Message.content (entering session.messages)
- Pydantic v2 discriminated union → SessionStore JSON round-trip for free
- Live stream ProviderThinkingDelta from Phase 6 unchanged (double-emit)

OpenAI compatibility:
- _convert_messages_to_openai silently skips new block types
- (OpenAI Chat Completions has no thinking concept)

CI:
- GitHub Actions matrix Python 3.10/3.11/3.12 × ubuntu/macos = 6 jobs
- pytest + mypy strict + ruff check + ruff format --check per job
- Pull request template
- README + pyproject.toml URLs point to the new public repo

Tests: 302 (was 289), all green.
Quality: mypy strict + ruff check + ruff format all clean.

Phase 8 candidates:
- Coverage threshold (after baseline data)
- PyPI release flow
- release.yml automation
- Windows matrix"

git push origin main
git push --tags
```

- [ ] **Step 6: Watch final CI**

```bash
gh run watch
```

Expected: green across all 6 jobs.

---

## Phase 7 Completion Checklist

**Workflow A:**

- [ ] `ThinkingBlock(text, signature)` in `abstractions/_types.py`
- [ ] `RedactedThinkingBlock(data)` in `abstractions/_types.py`
- [ ] `ContentBlock` uses `Annotated[..., Field(discriminator="type")]`
- [ ] Both new block types in `abstractions.__all__` + top-level `meta_harney.__all__`
- [ ] `ProviderThinkingBlock(text, signature)` + `ProviderRedactedThinking(data)` in `providers/base.py`
- [ ] Both new events in `ProviderStreamEvent` union + top-level exports
- [ ] AnthropicProvider buffers `thinking_delta` + `signature_delta` per block index
- [ ] AnthropicProvider emits `ProviderThinkingBlock` at `content_block_stop`
- [ ] AnthropicProvider emits `ProviderRedactedThinking` at `content_block_start` (redacted_thinking)
- [ ] `_convert_messages_to_anthropic` round-trips both block types in wire format
- [ ] OpenAIProvider silently skips both block types
- [ ] `FakeRound.thinking_blocks: list[ThinkingBlock]` field added
- [ ] `FakeRound` mutual-exclusion validator (thinking vs thinking_blocks) raises ValidationError
- [ ] `FakeLLMProvider.stream()` emits `ProviderThinkingBlock` for each `thinking_blocks` entry
- [ ] Engine appends new blocks to `assistant_blocks` (entering `session.messages`)
- [ ] MemorySessionStore + FileSessionStore round-trip new block types via Pydantic
- [ ] Integration test: thinking + tool_use multi-turn persistence E2E

**Workflow B:**

- [ ] `gh auth status` shows logged-in user
- [ ] Public GitHub repo `<GH_USER>/meta-harney` exists
- [ ] `origin` remote configured; `main` + tags v0.0.1–v0.0.6 pushed
- [ ] `.github/workflows/ci.yml` defines 6-job matrix (3 Python × 2 OS)
- [ ] `.github/pull_request_template.md` exists
- [ ] README badges point to actual GH Actions workflow + license + python version
- [ ] `pyproject.toml [project.urls]` has Homepage / Repository / Issues
- [ ] All 6 CI jobs pass on main

**Release:**

- [ ] `__version__ = "0.0.7"` in `src/meta_harney/__init__.py`
- [ ] `version = "0.0.7"` in `pyproject.toml`
- [ ] All 4 new types in top-level `__all__`
- [ ] Total tests 302 (was 289)
- [ ] mypy strict + ruff check + ruff format clean
- [ ] `v0.0.7` git tag exists on HEAD (local + pushed)

---

## Self-Review

**Spec coverage:**

- §1 Goals A.1–A.7 → Tasks 1, 3, 4, 5, 6, 8, 9
- §1 Goals B.1–B.7 → Tasks 12, 13, 14, 15
- §3 File Structure → all Workflow A + B tasks cover the listed files
- §4 APIs (4 new types) → Tasks 1, 2 define; Tasks 3-8 wire
- §5 Data flow (ThinkingBlock path, RedactedThinkingBlock path, OpenAI skip, CI trigger) → Tasks 3, 4, 6, 13 implement
- §6 Error handling (cap on missing signature, redacted continuity, gh failures) → no dedicated task; handled by existing error paths and Task 12's explicit-confirmation gate
- §7 Testing (13 new tests across 4 files) → Tasks 1, 2, 3, 4, 5, 6, 7, 9, 10
- §8 Version + tag → Task 17
- §9 Completion criteria → tracked via per-task checkboxes + Phase Completion Checklist

**Placeholder scan:**

- No "TBD", "TODO", "implement later", "fill in details", "handle edge cases" without specifics.
- Task 9 says "if FAIL after constructor fixes, this likely indicates a real bug in the discriminated union setup from Task 1 — debug there" — this is an actionable diagnostic, not a placeholder. Acceptable.
- Task 15 uses `<GH_USER>` as a literal-substitution marker (with explicit instruction to "write the literal username in the file, not a shell variable"). This is unavoidable given Task 12 dynamically determines the username at execution time.
- Task 17 step 1 (d) says "If unsure of exact positions, run `ruff check --fix src/meta_harney/__init__.py`" — acceptable: it's giving a concrete fallback for ambiguous ordering.

**Type consistency:**

- `ThinkingBlock(text: str, signature: str)` — same shape across Tasks 1, 3, 5, 7, 8, 10
- `RedactedThinkingBlock(data: str)` — same shape across Tasks 1, 4, 5, 6, 8, 9
- `ProviderThinkingBlock(text: str, signature: str)` — Tasks 2, 3, 7, 8
- `ProviderRedactedThinking(data: str)` — Tasks 2, 4, 8
- `FakeRound.thinking_blocks: list[ThinkingBlock]` — Tasks 7, 10
- `ProviderStreamEvent` union expanded to include 5 variants (Text, Tool, ThinkingDelta, ThinkingBlock, RedactedThinking, StreamDone) — Task 2 defines, all subsequent uses align
- Engine `thinking_blocks_buf: list[ThinkingBlock | RedactedThinkingBlock]` — Task 8 introduces

No naming drift detected.

**Risk callouts:**

- **Task 12 is irreversible.** The implementer must literally pause for user OK. If executing via subagent, the controller must surface this confirmation to the human.
- **Task 13's first CI run may take 5-10 minutes.** Implementer should plan to `gh run watch` rather than poll.
- **Task 15's `<GH_USER>` substitution** must happen consistently across README + pyproject — Tasks 13 (workflow filename in badge URL) and 15 both reference the username.
