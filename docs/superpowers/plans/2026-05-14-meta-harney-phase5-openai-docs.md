# meta-harney Phase 5: OpenAI Provider + Documentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Implement `OpenAIProvider` as the second real LLM backend, proving the `LLMProvider` Protocol extends beyond a single vendor; (2) write end-user documentation (README + 4 docs files) so the SDK is discoverable and adoptable.

**Architecture:** Two threads.
- **Provider:** `providers/openai.py` using `openai.AsyncOpenAI` SDK as optional dependency. Differs from Anthropic in message format (system in-band, tool_calls array on assistant, role=tool with tool_call_id) and stream structure (chat.completions chunks with `choices[0].delta`).
- **Documentation:** Top-level README rewritten for SDK consumers; 4 reference docs covering architecture, the 9 abstractions, provider setup, and testing helpers.

**Tech Stack:**
- Python 3.10+
- Pydantic v2
- `openai` SDK (NEW optional dependency, >=1.50)
- pytest + pytest-asyncio
- mypy strict + ruff
- Markdown for docs

**Phase 4 status (already merged on `main` @ v0.0.4):**
- AnthropicProvider + meta_harney.testing complete
- 247/247 tests pass; mypy strict + ruff clean

**Phase 5 carry-overs to Phase 6+:**
- ⏸ ThinkingDelta wiring (needs Anthropic extended thinking integration)
- ⏸ CRM mini-demo end-to-end example
- ⏸ Multi-turn-session E2E scenario (spec §8.4 #4)

---

## File Structure After Phase 5

```
src/meta_harney/
├── __init__.py                                # MODIFIED — expose OpenAIProvider, bump 0.0.5
└── providers/
    └── openai.py                              # NEW

docs/
├── README.md                                  # not here — at repo root
├── architecture.md                            # NEW
├── abstractions.md                            # NEW
├── providers.md                               # NEW
└── testing.md                                 # NEW

README.md                                      # MODIFIED (at repo root)

tests/
└── unit/providers/
    └── test_openai.py                         # NEW
```

---

## Task 1: Add `openai` optional dependency + scaffold `OpenAIProvider`

**Files:**
- Modify: `pyproject.toml`
- Create: `src/meta_harney/providers/openai.py`
- Test: `tests/unit/providers/test_openai.py`

- [ ] **Step 1: Add `openai>=1.50` to pyproject `[project.optional-dependencies]`**

Read `pyproject.toml`. The current optional deps section has `dev` and `anthropic`. Add:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
    "anthropic>=0.40",
    "openai>=1.50",
]
anthropic = [
    "anthropic>=0.40",
]
openai = [
    "openai>=1.50",
]
```

Then install:
```bash
source .venv/bin/activate
uv pip install -e ".[dev]"
python -c "import openai; print(openai.__version__)"
```

- [ ] **Step 2: Write `tests/unit/providers/test_openai.py`**

```python
"""Tests for OpenAIProvider — Chat Completions adapter."""
from __future__ import annotations

import pytest

from meta_harney.providers.openai import OpenAIProvider


def test_openai_provider_constructs() -> None:
    p = OpenAIProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_openai_provider_requires_api_key() -> None:
    """Empty api_key should raise ConfigurationError."""
    from meta_harney.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="api_key"):
        OpenAIProvider(api_key="")
```

- [ ] **Step 3: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement scaffold `src/meta_harney/providers/openai.py`**

```python
"""OpenAIProvider — adapts the OpenAI Chat Completions API to LLMProvider Protocol.

Uses the official `openai` Python SDK. Install via:
    pip install meta-harney[openai]

Phase 5 task 1: scaffold + constructor + api_key validation.
Tasks 2-7 implement message conversion, stream event mapping, and error
classification.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from meta_harney.abstractions._types import Message
from meta_harney.errors import ConfigurationError
from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamEvent,
    ToolSpec,
)


class OpenAIProvider:
    """LLMProvider implementation using the openai SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise ConfigurationError("OpenAIProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url
        self._default_max_tokens = default_max_tokens

    def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream a single LLM call. Filled in by Tasks 4-6."""
        raise NotImplementedError("OpenAI stream lands in Task 4")
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
mypy src/meta_harney/providers/openai.py
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAIProvider scaffold + api_key validation

Adds 'openai' optional dependency (>=1.50). OpenAIProvider constructor
validates api_key, stores base_url + default_max_tokens. stream()
raises NotImplementedError — implementation in Tasks 4-6."
```

---

## Task 2: OpenAI message format conversion

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

OpenAI Chat Completions format (key differences from Anthropic):
- `system` is a regular role in the messages array (not extracted)
- `assistant` with tool call: `content=None` + `tool_calls=[{"id","type":"function","function":{"name","arguments":<json-str>}}]`
- `tool` role for results: `{"role":"tool","tool_call_id","content":<str>}`
- `system_prompt` arg (if provided) is PREPENDED as a `{"role":"system"}` message

- [ ] **Step 1: Append failing tests**

```python


from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.providers.openai import _convert_messages_to_openai


def test_convert_simple_user_message_with_system_prompt() -> None:
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    converted = _convert_messages_to_openai(msgs, system_prompt="be helpful")
    assert converted == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]


def test_convert_inband_system_message() -> None:
    """System-role messages from history stay in-band (not extracted)."""
    msgs = [
        Message(role="system", content=[TextBlock(text="be helpful")]),
        Message(role="user", content=[TextBlock(text="hi")]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    # No runtime system_prompt prepended because it's empty
    assert converted == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]


def test_convert_assistant_with_tool_call() -> None:
    msgs = [
        Message(role="user", content=[TextBlock(text="search")]),
        Message(role="assistant", content=[
            TextBlock(text="Let me check."),
            ToolCallBlock(invocation_id="call_1", name="search", args={"q": "x"}),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assistant_msg = converted[-1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Let me check."
    assert assistant_msg["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "search", "arguments": '{"q": "x"}'},
    }]


def test_convert_assistant_tool_call_only_no_text() -> None:
    """Assistant message with only ToolCallBlocks: content is None."""
    msgs = [
        Message(role="assistant", content=[
            ToolCallBlock(invocation_id="c1", name="f", args={}),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["content"] is None
    assert len(converted[0]["tool_calls"]) == 1


def test_convert_tool_result_message() -> None:
    """tool role → OpenAI tool role with tool_call_id."""
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(invocation_id="c1", success=True, output="result text"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert converted[0]["role"] == "tool"
    assert converted[0]["tool_call_id"] == "c1"
    assert "result text" in converted[0]["content"]


def test_convert_failed_tool_result_includes_error() -> None:
    msgs = [
        Message(role="tool", content=[
            ToolResultBlock(invocation_id="c1", success=False, output=None, error="boom"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    assert "boom" in converted[0]["content"]


def test_convert_image_block_uses_image_url() -> None:
    """ImageBlock with url → OpenAI image_url content part."""
    msgs = [
        Message(role="user", content=[
            TextBlock(text="see this"),
            ImageBlock(url="https://x/y.png", media_type="image/png"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    content = converted[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "see this"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://x/y.png"},
    }


def test_convert_image_block_base64() -> None:
    """Base64 ImageBlock → data URL in image_url."""
    msgs = [
        Message(role="user", content=[
            ImageBlock(data="iVBORw0KGgo...", media_type="image/png"),
        ]),
    ]
    converted = _convert_messages_to_openai(msgs, system_prompt="")
    content = converted[0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
```

Move new imports to top of file.

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
```

Expected: ImportError on `_convert_messages_to_openai`.

- [ ] **Step 3: Add converter to `src/meta_harney/providers/openai.py`**

Add module-level function BEFORE the `OpenAIProvider` class. Also add imports at top:

```python
import json
from typing import Any

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
```

Then the function:

```python
def _convert_messages_to_openai(
    messages: list[Message],
    *,
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Convert meta_harney messages to OpenAI Chat Completions format.

    Conversion rules:
    - system_prompt (if non-empty) → prepended as {"role":"system"} message
    - role=user → {"role":"user","content":...} (string or list of content parts)
    - role=assistant text-only → {"role":"assistant","content":<str>}
    - role=assistant with tool calls →
        {"role":"assistant","content":<str|None>,"tool_calls":[...]}
    - role=tool → {"role":"tool","tool_call_id":...,"content":<str>}
    - TextBlock → {"type":"text","text":...} (inside content list)
    - ImageBlock (url) → {"type":"image_url","image_url":{"url":...}}
    - ImageBlock (data) → {"type":"image_url","image_url":{"url":"data:<media>;base64,<data>"}}
    """
    out: list[dict[str, Any]] = []
    if system_prompt:
        out.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "system":
            # In-band system message: keep verbatim text
            text = "".join(
                b.text for b in msg.content if isinstance(b, TextBlock)
            )
            out.append({"role": "system", "content": text})
            continue

        if msg.role == "tool":
            # Tool result: one ToolResultBlock per OpenAI tool message
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    content_str = (
                        block.error if not block.success else str(block.output)
                    )
                    out.append({
                        "role": "tool",
                        "tool_call_id": block.invocation_id,
                        "content": content_str or "",
                    })
            continue

        # user or assistant
        text_parts: list[str] = []
        content_parts: list[dict[str, Any]] = []  # for vision-style multi-part
        tool_calls: list[dict[str, Any]] = []
        has_non_text = False

        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
                content_parts.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageBlock):
                has_non_text = True
                if block.url is not None:
                    url = block.url
                else:
                    url = f"data:{block.media_type};base64,{block.data}"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            elif isinstance(block, ToolCallBlock):
                tool_calls.append({
                    "id": block.invocation_id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.args),
                    },
                })
            # ToolResultBlock in user/assistant message is unexpected — skip

        entry: dict[str, Any] = {"role": msg.role}

        if has_non_text:
            entry["content"] = content_parts
        elif text_parts:
            entry["content"] = "".join(text_parts)
        else:
            entry["content"] = None  # tool_calls-only assistant

        if tool_calls:
            entry["tool_calls"] = tool_calls

        out.append(entry)

    return out
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAI message format conversion

_convert_messages_to_openai(messages, *, system_prompt):
- system_prompt prepended as {role:system} message
- in-band system messages kept verbatim
- assistant text + tool_calls combine: content=str|None, tool_calls=[...]
- tool role expanded to one OpenAI tool message per ToolResultBlock
- ImageBlock url → image_url.url, data → data: URL
- ToolCallBlock args serialized via json.dumps (OpenAI expects string)"
```

---

## Task 3: Convert ToolSpec to OpenAI tools format

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

OpenAI tools format wraps each ToolSpec into a function definition:
```python
{"type": "function", "function": {"name": ..., "description": ..., "parameters": <schema>}}
```

- [ ] **Step 1: Append failing test**

```python


from meta_harney.providers.base import ToolSpec
from meta_harney.providers.openai import _convert_tools_to_openai


def test_convert_tools_to_openai_basic() -> None:
    tools = [
        ToolSpec(
            name="echo",
            description="Echoes input",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        ),
    ]
    converted = _convert_tools_to_openai(tools)
    assert converted == [{
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echoes input",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
    }]


def test_convert_empty_tools() -> None:
    assert _convert_tools_to_openai([]) == []
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
```

- [ ] **Step 3: Implement `_convert_tools_to_openai` in `openai.py`**

Add module-level function (placement: between `_convert_messages_to_openai` and `OpenAIProvider`):

```python
def _convert_tools_to_openai(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec list to OpenAI tools array."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): _convert_tools_to_openai helper

Maps ToolSpec list to OpenAI tools array:
{name, description, input_schema} → {type:function, function:{name,description,parameters}}"
```

---

## Task 4: OpenAIProvider.stream() — text-only path

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

Implement the streaming consumer for text-only responses. Tool calls come in Task 5.

OpenAI Chat Completions stream chunks:
- Each chunk: `chunk.choices[0].delta` with `content` (text delta)
- Final chunk: `chunk.choices[0].finish_reason` is set ("stop", "length", "tool_calls", etc.)
- Usage stats: with `stream_options={"include_usage": True}`, last chunk has `chunk.usage` with `prompt_tokens` and `completion_tokens`

`finish_reason` → `ProviderStreamDone.stop_reason`:
- "stop" → "end_turn"
- "length" → "max_tokens"
- "tool_calls" → "tool_use"
- "content_filter" / other → "error"

- [ ] **Step 1: Append failing test**

```python


from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock, patch

from meta_harney.providers.base import (
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
)


class _FakeOpenAIStream:
    """AsyncIterable of fake chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _make_chunk(
    *,
    text: str | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
) -> MagicMock:
    """Build a MagicMock chunk that mimics OpenAI ChatCompletionChunk."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()

    delta.content = text
    delta.tool_calls = None
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _make_usage(prompt_tokens: int, completion_tokens: int) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt_tokens
    u.completion_tokens = completion_tokens
    return u


async def test_stream_emits_text_delta_and_done() -> None:
    """Simple text response: chunks with text + final finish_reason."""
    chunks = [
        _make_chunk(text="hello "),
        _make_chunk(text="world"),
        _make_chunk(finish_reason="stop"),
        _make_chunk(usage=_make_usage(prompt_tokens=10, completion_tokens=2)),
    ]

    fake_completions = MagicMock()
    fake_completions.create = MagicMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch(
        "meta_harney.providers.openai.AsyncOpenAI",
        return_value=fake_client,
    ):
        provider = OpenAIProvider(api_key="test")
        msgs = [Message(role="user", content=[TextBlock(text="hi")])]
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=msgs,
            system_prompt="be helpful",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    text_events = [e for e in collected if isinstance(e, ProviderTextDelta)]
    assert [e.text for e in text_events] == ["hello ", "world"]
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert len(done) == 1
    assert done[0].stop_reason == "end_turn"
    assert done[0].input_tokens == 10
    assert done[0].output_tokens == 2


async def test_stream_finish_reason_length_maps_to_max_tokens() -> None:
    chunks = [
        _make_chunk(text="incomplete"),
        _make_chunk(finish_reason="length"),
    ]
    fake_completions = MagicMock()
    fake_completions.create = MagicMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected = [
            ev
            async for ev in provider.stream(
                messages=[Message(role="user", content=[TextBlock(text="hi")])],
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="gpt-4"),
            )
        ]
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert done[0].stop_reason == "max_tokens"
```

Move new imports to top of file.

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py::test_stream_emits_text_delta_and_done -v
```

Expected: NotImplementedError.

- [ ] **Step 3: Implement `stream()` text-only path**

Add imports to `openai.py`:
```python
from openai import AsyncOpenAI
```

Replace the `stream()` method:

```python
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream one OpenAI Chat Completions call.

        Translates SDK chunks into ProviderStreamEvent variants.
        """
        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        wire_messages = _convert_messages_to_openai(messages, system_prompt=system_prompt)
        wire_tools = _convert_tools_to_openai(tools)
        max_tokens = config.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if wire_tools:
            kwargs["tools"] = wire_tools
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        stream_ = await client.chat.completions.create(**kwargs)

        async for chunk in stream_:
            # Usage chunk (with stream_options={"include_usage": True}) has empty choices.
            if getattr(chunk, "usage", None) is not None:
                input_tokens = getattr(chunk.usage, "prompt_tokens", None)
                output_tokens = getattr(chunk.usage, "completion_tokens", None)

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            text_delta = getattr(delta, "content", None)
            if text_delta:
                yield ProviderTextDelta(text=text_delta)

            # Tool call deltas handled in Task 5

            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

        # Map OpenAI finish_reason → meta_harney stop_reason literal
        stop_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "function_call": "tool_use",
        }
        mapped = stop_map.get(finish_reason or "stop", "error")

        yield ProviderStreamDone(
            stop_reason=mapped,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
```

Note: `stream_` is an `AsyncStream`; iterating it requires `await client.chat.completions.create(...)` first (returns the stream object). The fake test uses `return_value=_FakeOpenAIStream(...)` which is the right shape — but `client.chat.completions.create` returns it directly without `await`. The actual OpenAI SDK returns a coroutine that resolves to the AsyncStream. The fake doesn't simulate that.

**Fix:** make `create` an `AsyncMock` returning the stream, OR make `_FakeOpenAIStream` an awaitable that returns itself.

In the test, change:
```python
fake_completions.create = MagicMock(return_value=_FakeOpenAIStream(chunks))
```
to:
```python
from unittest.mock import AsyncMock
fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
```

Apply this fix to both new tests.

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAIProvider.stream() text-only path

Iterates async chat.completions.create(stream=True) chunks. Accumulates:
- delta.content → ProviderTextDelta
- choice.finish_reason → final stop_reason (mapped to literal)
- chunk.usage → input/output tokens (last chunk via stream_options)

stop_reason mapping: stop→end_turn, length→max_tokens, tool_calls/function_call→tool_use, other→error.

Tool call deltas handled in Task 5."
```

---

## Task 5: OpenAIProvider tool_calls accumulation

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

OpenAI streams tool calls as deltas per-index. Each delta has:
- `index` (which tool call)
- `id` (only set on FIRST delta of a tool call)
- `function.name` (set on first delta usually)
- `function.arguments` (streaming JSON-as-string chunks)

We accumulate per-index until finish_reason is set, then emit one `ProviderToolCall` per index.

- [ ] **Step 1: Append failing test**

```python


from meta_harney.providers.base import ProviderToolCall


def _make_tool_call_delta(
    *,
    index: int,
    id_: str | None = None,
    name: str | None = None,
    arguments: str = "",
) -> MagicMock:
    tc = MagicMock()
    tc.index = index
    tc.id = id_
    tc.type = "function"
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc.function = func
    return tc


def _make_chunk_with_tool_calls(
    *,
    tool_call_deltas: list[Any] | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
) -> MagicMock:
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = tool_call_deltas
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


async def test_stream_emits_tool_call() -> None:
    """OpenAI streams tool_calls as per-index deltas; we accumulate and emit one ProviderToolCall."""
    from unittest.mock import AsyncMock

    chunks = [
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, id_="call_abc", name="search"),
            ],
        ),
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, arguments='{"query":'),
            ],
        ),
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, arguments='"hello"}'),
            ],
        ),
        _make_chunk_with_tool_calls(finish_reason="tool_calls"),
    ]

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="search hello")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].invocation_id == "call_abc"
    assert tool_calls[0].name == "search"
    assert tool_calls[0].args == {"query": "hello"}
    done = [e for e in collected if isinstance(e, ProviderStreamDone)]
    assert done[0].stop_reason == "tool_use"


async def test_stream_multiple_tool_calls() -> None:
    """Two tool calls at different indices accumulate independently."""
    from unittest.mock import AsyncMock

    chunks = [
        _make_chunk_with_tool_calls(
            tool_call_deltas=[
                _make_tool_call_delta(index=0, id_="c1", name="f1", arguments='{"a":1}'),
                _make_tool_call_delta(index=1, id_="c2", name="f2", arguments='{"b":2}'),
            ],
        ),
        _make_chunk_with_tool_calls(finish_reason="tool_calls"),
    ]

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        collected: list[ProviderStreamEvent] = []
        async for ev in provider.stream(
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
            system_prompt="",
            tools=[],
            config=ProviderCallConfig(model="gpt-4"),
        ):
            collected.append(ev)

    tool_calls = [e for e in collected if isinstance(e, ProviderToolCall)]
    assert len(tool_calls) == 2
    by_id = {tc.invocation_id: tc for tc in tool_calls}
    assert by_id["c1"].name == "f1"
    assert by_id["c1"].args == {"a": 1}
    assert by_id["c2"].name == "f2"
    assert by_id["c2"].args == {"b": 2}
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py::test_stream_emits_tool_call -v
```

Expected: FAIL — current code doesn't accumulate tool_calls.

- [ ] **Step 3: Add tool_calls accumulation to `stream()`**

Update the `stream()` method in `openai.py` to track tool_call buffer and emit on finish. Replace the entire body:

```python
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        """Stream one OpenAI Chat Completions call."""
        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        wire_messages = _convert_messages_to_openai(messages, system_prompt=system_prompt)
        wire_tools = _convert_tools_to_openai(tools)
        max_tokens = config.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if wire_tools:
            kwargs["tools"] = wire_tools
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        # tool_call_buffer[index] = {"id": str, "name": str, "args_chunks": [str, ...]}
        tool_call_buffer: dict[int, dict[str, Any]] = {}

        stream_ = await client.chat.completions.create(**kwargs)

        async for chunk in stream_:
            if getattr(chunk, "usage", None) is not None:
                input_tokens = getattr(chunk.usage, "prompt_tokens", None)
                output_tokens = getattr(chunk.usage, "completion_tokens", None)

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            text_delta = getattr(delta, "content", None)
            if text_delta:
                yield ProviderTextDelta(text=text_delta)

            tc_deltas = getattr(delta, "tool_calls", None) or []
            for tc_delta in tc_deltas:
                idx = tc_delta.index
                if idx not in tool_call_buffer:
                    tool_call_buffer[idx] = {
                        "id": None,
                        "name": None,
                        "args_chunks": [],
                    }
                buf = tool_call_buffer[idx]
                if tc_delta.id is not None:
                    buf["id"] = tc_delta.id
                fn = getattr(tc_delta, "function", None)
                if fn is not None:
                    if fn.name is not None:
                        buf["name"] = fn.name
                    if fn.arguments:
                        buf["args_chunks"].append(fn.arguments)

            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

        # Emit ProviderToolCall for each accumulated tool call (sorted by index)
        for idx in sorted(tool_call_buffer):
            buf = tool_call_buffer[idx]
            raw = "".join(buf["args_chunks"])
            try:
                parsed_args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed_args = {}
            yield ProviderToolCall(
                invocation_id=buf["id"] or f"openai-tc-{idx}",
                name=buf["name"] or "",
                args=parsed_args,
            )

        stop_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "function_call": "tool_use",
        }
        mapped = stop_map.get(finish_reason or "stop", "error")

        yield ProviderStreamDone(
            stop_reason=mapped,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAIProvider tool_calls accumulation

Tool calls stream as per-index deltas: id (first delta only),
function.name (first), function.arguments (multiple chunks of JSON).
Buffer by index; emit one ProviderToolCall per index after stream
finishes. JSON parse with graceful {} fallback."
```

---

## Task 6: OpenAIProvider error classification

**Files:**
- Modify: `src/meta_harney/providers/openai.py`
- Modify: `tests/unit/providers/test_openai.py`

`openai` SDK raises:
- `APIConnectionError` — network / DNS failure → Retryable
- `RateLimitError` (429) → Retryable
- `APIStatusError` (other 4xx/5xx) — check `.status_code`:
  - 5xx → Retryable
  - other → NonRetryable

- [ ] **Step 1: Append failing tests**

```python


async def test_openai_rate_limit_maps_to_retryable() -> None:
    """RateLimitError → RetryableProviderError."""
    from unittest.mock import AsyncMock

    from openai import RateLimitError

    from meta_harney.errors import RetryableProviderError

    def _raise_rate_limit(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 429
        raise RateLimitError("rate limited", response=resp, body=None)

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(side_effect=_raise_rate_limit)
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=[Message(role="user", content=[TextBlock(text="hi")])],
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="gpt-4"),
            ):
                pass


async def test_openai_500_maps_to_retryable() -> None:
    from unittest.mock import AsyncMock

    from openai import APIStatusError

    from meta_harney.errors import RetryableProviderError

    def _raise_500(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 503
        raise APIStatusError("upstream error", response=resp, body=None)

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(side_effect=_raise_500)
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        with pytest.raises(RetryableProviderError):
            async for _ev in provider.stream(
                messages=[Message(role="user", content=[TextBlock(text="hi")])],
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="gpt-4"),
            ):
                pass


async def test_openai_401_maps_to_non_retryable() -> None:
    from unittest.mock import AsyncMock

    from openai import APIStatusError

    from meta_harney.errors import NonRetryableProviderError

    def _raise_401(**kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 401
        raise APIStatusError("auth failed", response=resp, body=None)

    fake_completions = MagicMock()
    fake_completions.create = AsyncMock(side_effect=_raise_401)
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_client = MagicMock()
    fake_client.chat = fake_chat

    with patch("meta_harney.providers.openai.AsyncOpenAI", return_value=fake_client):
        provider = OpenAIProvider(api_key="test")
        with pytest.raises(NonRetryableProviderError):
            async for _ev in provider.stream(
                messages=[Message(role="user", content=[TextBlock(text="hi")])],
                system_prompt="",
                tools=[],
                config=ProviderCallConfig(model="gpt-4"),
            ):
                pass
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
```

Expected: 3 new failures (errors propagate as-is).

- [ ] **Step 3: Add error mapping**

Update imports at top of `openai.py`:

```python
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from meta_harney.errors import NonRetryableProviderError, RetryableProviderError
```

(Keep existing `ConfigurationError` import.)

Wrap the entire `stream_ = await client.chat.completions.create(...)` + `async for chunk in stream_:` block in try/except. After the existing logic up to `mapped = stop_map.get(...)`, restructure so that the stream call + iteration is inside a single try:

```python
        try:
            stream_ = await client.chat.completions.create(**kwargs)
            async for chunk in stream_:
                # ... existing chunk handling ... (unchanged)
        except RateLimitError as exc:
            raise RetryableProviderError(f"openai rate limit: {exc}") from exc
        except APIStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            if status is not None and 500 <= status < 600:
                raise RetryableProviderError(
                    f"openai transient error (status {status}): {exc}"
                ) from exc
            raise NonRetryableProviderError(
                f"openai API error (status {status}): {exc}"
            ) from exc
        except APIConnectionError as exc:
            raise RetryableProviderError(
                f"openai connection error: {exc}"
            ) from exc
```

Keep the `yield ProviderToolCall(...)` and `yield ProviderStreamDone(...)` AFTER the try/except (they run only on the success path).

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check src/meta_harney/providers/openai.py
mypy src/meta_harney/providers/openai.py
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/openai.py tests/unit/providers/test_openai.py
git commit -m "feat(providers): OpenAIProvider error classification

Maps openai SDK exceptions to meta_harney provider errors:
- RateLimitError → RetryableProviderError
- APIConnectionError → RetryableProviderError
- APIStatusError 5xx → RetryableProviderError
- APIStatusError other → NonRetryableProviderError"
```

---

## Task 7: OpenAIProvider passes LLMProviderContract

**Files:**
- Modify: `tests/unit/providers/test_openai.py`

- [ ] **Step 1: Append contract subclass**

```python


from tests.contracts.llm_provider import LLMProviderContract


class TestOpenAIProviderContract(LLMProviderContract):
    """OpenAIProvider passes the standard LLMProvider contract."""

    @pytest.fixture(autouse=True)
    def _stub_openai_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace AsyncOpenAI with a mock for the duration of each test."""
        from unittest.mock import AsyncMock

        def _factory() -> MagicMock:
            chunks = [
                _make_chunk(text="ok"),
                _make_chunk(finish_reason="stop"),
                _make_chunk(usage=_make_usage(prompt_tokens=1, completion_tokens=1)),
            ]
            fake_completions = MagicMock()
            fake_completions.create = AsyncMock(return_value=_FakeOpenAIStream(chunks))
            fake_chat = MagicMock()
            fake_chat.completions = fake_completions
            fake_client = MagicMock()
            fake_client.chat = fake_chat
            return fake_client

        monkeypatch.setattr(
            "meta_harney.providers.openai.AsyncOpenAI",
            lambda **kwargs: _factory(),
        )

    def make_provider(self):
        return OpenAIProvider(api_key="test-contract")
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_openai.py -v
ruff check tests/unit/providers/test_openai.py
mypy tests/unit/providers/test_openai.py
```

Expected: all openai tests pass (~14-15); contract 2 pass; clean.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/providers/test_openai.py
git commit -m "test: OpenAIProvider passes LLMProviderContract

Standard 2 contract checks applied to OpenAIProvider with mocked SDK.
Confirms the OpenAI adapter conforms to the LLMProvider Protocol —
parallel validation to the AnthropicProvider contract test."
```

---

## Task 8: Expose OpenAIProvider at top level

**Files:**
- Modify: `src/meta_harney/__init__.py`

- [ ] **Step 1: Add import + `__all__` entry**

Read `src/meta_harney/__init__.py`. Add this import (alphabetical position):

```python
from meta_harney.providers.openai import OpenAIProvider
```

Add `"OpenAIProvider"` to `__all__` (preserve alphabetical sort).

- [ ] **Step 2: Smoke test**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
assert mh.OpenAIProvider
assert mh.AnthropicProvider
print(f'Exports: {len(mh.__all__)}')
print('OK')
"
ruff check src/meta_harney/__init__.py
mypy src/meta_harney/__init__.py
pytest -q
```

Expected: OK; exports 54.

- [ ] **Step 3: Commit**

```bash
git add src/meta_harney/__init__.py
git commit -m "feat: expose OpenAIProvider at meta_harney top level

Public API now exposes both Anthropic and OpenAI providers as
peer LLMProvider implementations."
```

---

## Task 9: README.md update

**Files:**
- Modify: `README.md` (at repo root — currently a placeholder)

- [ ] **Step 1: Replace `README.md` with user-facing intro**

Write to `/Users/baihe/Projects/study/OpenHarness/README.md`:

```markdown
# meta-harney

> A domain-agnostic agent runtime SDK. Clean abstractions for tools, hooks,
> permissions, prompts, sessions, tracing, and multi-agent coordination —
> with no assumptions about your business domain.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#testing)

## Why meta-harney?

Most agent frameworks bake in assumptions about *what* you're building — usually
coding assistants. meta-harney is the **runtime kernel**: agent loop, tool
dispatch, permission gating, hooks, multi-agent coordination, all behind clean
Protocol-based abstractions. **You** decide what your agent does.

Built for:

- **Business AI** — CRM agents, ops agents, support agents
- **Multi-tenant SaaS** — tenant-aware sessions, observability hooks
- **Reproducible testing** — `FakeLLMProvider` + contract test suite for
  every abstraction

## Quickstart

```bash
pip install meta-harney[anthropic]
```

```python
import asyncio
from meta_harney import (
    AgentRuntime,
    AnthropicProvider,
    MinimalPromptBuilder,
    AllowAllPermissionResolver,
    MemorySessionStore,
    NullSink,
    RuntimeConfig,
)
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink


async def main():
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=AnthropicProvider(api_key="sk-ant-..."),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="claude-sonnet-4-5"),
    )
    session = await rt.create_session()
    response = await rt.invoke(session.id, "What's the capital of France?")
    print(response.content[0].text)


asyncio.run(main())
```

## Core Abstractions

9 protocol/ABC interfaces define the runtime contract:

| Abstraction | What it does |
|---|---|
| `BaseTool` | Executable capability invoked by the LLM |
| `BaseHook` | Lifecycle event subscriber (7 event kinds) |
| `PermissionResolver` | Pre-execution allow/deny/ask check |
| `PromptBuilder` | System prompt + context assembly |
| `BaseTask` | Background-task primitive |
| `SessionStore` | Session persistence with optimistic locking |
| `TraceSink` | Observability event emission |
| `MultiAgentBackend` | Child agent spawning (blocking + detached) |
| `CompactionStrategy` | Context-window management |

See [`docs/abstractions.md`](docs/abstractions.md) for details on each.

## LLM Providers

| Provider | Install | Models |
|---|---|---|
| Anthropic | `pip install meta-harney[anthropic]` | Claude family |
| OpenAI | `pip install meta-harney[openai]` | GPT family |
| Custom | implement `LLMProvider` Protocol | any backend |

See [`docs/providers.md`](docs/providers.md).

## Testing your agent

```python
from meta_harney.testing import runtime_for_testing, FakeRound

rt = runtime_for_testing(
    scripted_rounds=[
        FakeRound(text="Hello!", stop_reason="end_turn"),
    ],
    tools={"my_tool": MyTool()},
)
session = await rt.create_session()
result = await rt.invoke(session.id, "hi")
```

See [`docs/testing.md`](docs/testing.md).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview
- [`docs/abstractions.md`](docs/abstractions.md) — the 9 abstractions reference
- [`docs/providers.md`](docs/providers.md) — provider setup + custom-provider guide
- [`docs/testing.md`](docs/testing.md) — testing helpers
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — original design specs

## Project status

| Phase | Status |
|---|---|
| 1: Foundation (9 abstractions + builtins) | ✅ v0.0.1 |
| 2: Engine + provider Protocol | ✅ v0.0.2 |
| 3: AgentRuntime + multi-agent | ✅ v0.0.3 |
| 4: Anthropic provider + testing module | ✅ v0.0.4 |
| 5: OpenAI provider + docs | ✅ v0.0.5 |

## License

Apache-2.0
```

- [ ] **Step 2: Verify**

```bash
test -f README.md && head -5 README.md
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README — user-facing intro

Replaces placeholder with: why meta-harney, quickstart code, 9 abstractions
table, provider matrix, testing snippet, doc links, project status table."
```

---

## Task 10: docs/architecture.md

**Files:**
- Create: `docs/architecture.md`

- [ ] **Step 1: Write `docs/architecture.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add docs/architecture.md

System-level overview: high-level diagram, turn lifecycle, two event
streams (StreamEvent vs TraceEvent), error handling, multi-agent flow,
dependency layering."
```

---

## Task 11: docs/abstractions.md

**Files:**
- Create: `docs/abstractions.md`

- [ ] **Step 1: Write `docs/abstractions.md`**

```markdown
# meta-harney Abstractions Reference

The 9 core interfaces. Each is either a Protocol (structural — duck-typed) or
an ABC (nominal — subclass required). Pick the right pattern per impl style.

## BaseTool (ABC)

A capability the LLM can invoke. Subclasses declare:

- `name: ClassVar[str]` — identifier shown to the LLM
- `description: ClassVar[str]` — natural-language purpose
- `input_schema: ClassVar[type[BaseModel]]` — Pydantic schema for args
- `default_timeout: ClassVar[float | None] = None` — execution timeout
- `async def execute(inv: ToolInvocation, ctx: ToolContext) -> ToolResult`

```python
from pydantic import BaseModel
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult


class _LookupCustomerInput(BaseModel):
    customer_id: str


class LookupCustomerTool(BaseTool):
    name = "lookup_customer"
    description = "Look up a customer by ID."
    input_schema = _LookupCustomerInput
    default_timeout = 10.0

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        cid = inv.args["customer_id"]
        record = await my_db.fetch_customer(cid)
        return ToolResult(success=True, output=record)
```

`ToolContext` exposes: `session_store`, `trace_sink`, `current_span_id`,
`new_span_id`, optional `multi_agent`.

## BaseHook (ABC)

Lifecycle event subscriber. 7 event kinds: `session_start`, `pre_llm`,
`post_llm`, `pre_tool`, `post_tool`, `turn_complete`, `session_end`.

```python
class AuditHook(BaseHook):
    subscribed_events = {"pre_tool", "post_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        await my_audit_log.write(event)
        return HookDecision(allow=True)
```

`HookDecision`:
- `allow: bool` — `False` short-circuits the loop (returns the decision to the engine)
- `transform: dict | None` — modify pre-event payload (e.g., args override)
- `reason: str | None` — human-readable reason for the decision

Raise `HookHaltError` to halt the whole turn.

## PermissionResolver (Protocol)

Pre-execution gate per tool call. Verdict is `allow` / `deny` / `ask`:

```python
class TenantScopedPermission:
    async def resolve(self, inv: ToolInvocation, session_id: str) -> PermissionDecision:
        session = await session_store.load(session_id)
        if inv.name == "delete_customer" and session.tenant_id != "admin":
            return PermissionDecision(verdict="deny", reason="non-admin tenant")
        return PermissionDecision(verdict="allow")
```

`ask` is treated as deny in Phase 4 (no human-approval mechanism yet).

## PromptBuilder (Protocol)

```python
class PromptBuilder(Protocol):
    async def build_system_prompt(self, session_id: str) -> str: ...
    async def build_context_messages(self, session_id: str) -> list[Message]: ...
```

`MinimalPromptBuilder` (built-in) reads from a `SessionStore`. Override for
domain-specific framing.

## BaseTask (ABC)

Background-task primitive. Used by `MultiAgentBackend` (detached children
become tasks). 5 states: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`CANCELLED`.

## Session + SessionStore

`Session` carries:
- `id`, `tenant_id`, `user_id`, `parent_session_id`
- `created_at`, `version` (optimistic-lock)
- `messages: list[Message]`
- `attributes: dict` (free-form business data)
- `metadata: dict` (free-form app data)

`SessionStore` Protocol:
- `load(session_id, *, tenant_id=None) -> Session | None`
- `save(session)` — must enforce optimistic lock (raise `SessionConflictError`)
- `list(*, tenant_id=None, filter=None)`
- `delete(session_id)`

Built-ins: `MemorySessionStore`, `FileSessionStore`. Contract test:
`SessionStoreContract` (10 checks).

## TraceEvent + TraceSink

Observability stream. Every `TraceEvent` has `ts`, `session_id`, `kind`,
`span_id`, `parent_span_id`, `payload`, optional `duration_ms`.

Reserved `kind` vocabulary includes `turn.started`, `llm.completed`,
`tool.invoked`, `tool.completed`, `permission.resolved`, `hook.fired`,
`error.raised`, `compaction.triggered`, etc.

Built-ins: `NullSink` (default), `JsonlSink` (file).

## MultiAgentBackend (Protocol)

`spawn(spec, initial_message, parent_session_id, mode="blocking" | "detached") -> SpawnHandle`

```python
spec = AgentSpec(
    name="sales-helper",
    instructions="You are a focused sales-research assistant.",
    allowed_tools=["search_company", "get_news"],
    max_iters=5,
)
handle = await ctx.multi_agent.spawn(spec, "Research Acme Corp.", parent_session_id, mode="blocking")
result = await ctx.multi_agent.join(handle.child_session_id)
```

Built-in: `InProcessMultiAgentBackend`. Contract test:
`MultiAgentBackendContract` (5 checks).

## CompactionStrategy (Protocol)

```python
class CompactionStrategy(Protocol):
    async def should_compact(self, session_id, current_tokens, window_limit) -> bool: ...
    async def compact(self, session_id) -> list[Message]: ...
```

Built-in: `SummarizationCompactor` (keeps recent N + summarizes the middle via
an injected `summarize_fn`).

## Contract tests

Each Protocol has a reusable `XContract` test class. Subclass it for your
custom impl:

```python
from tests.contracts.session_store import SessionStoreContract

class TestMyPostgresStore(SessionStoreContract):
    def make_store(self):
        return MyPostgresStore(dsn="...")
```

This gives you 10 conformance tests for free. Same pattern for
`PermissionResolverContract`, `TraceSinkContract`, `PromptBuilderContract`,
`CompactionStrategyContract`, `MultiAgentBackendContract`, `LLMProviderContract`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/abstractions.md
git commit -m "docs: add docs/abstractions.md

Reference page for the 9 core abstractions. Each entry: purpose,
Protocol/ABC distinction, signature, code example. Built-in implementations
and contract test suites cross-referenced."
```

---

## Task 12: docs/providers.md

**Files:**
- Create: `docs/providers.md`

- [ ] **Step 1: Write `docs/providers.md`**

```markdown
# LLM Providers

meta-harney's `LLMProvider` Protocol decouples the engine from any specific
LLM backend. The runtime calls `provider.stream()` to consume a single LLM
round; everything else (retry, tool dispatch, message assembly) is provider-agnostic.

## Built-in providers

### AnthropicProvider

```bash
pip install meta-harney[anthropic]
```

```python
from meta_harney import AnthropicProvider, RuntimeConfig

provider = AnthropicProvider(
    api_key="sk-ant-...",          # required
    base_url=None,                  # optional override
    default_max_tokens=4096,        # if config.max_tokens not set
)

config = RuntimeConfig(
    model="claude-sonnet-4-5",
    max_tokens=8192,                # optional per-call override
    temperature=0.7,                # optional
)
```

Supported features:
- Streaming text + tool calls
- Multi-modal: `ImageBlock` (URL or base64)
- System message extraction (Anthropic uses `system` kwarg, not in messages)
- `tool_result` mapping (Anthropic uses `user` role with `tool_result` content)
- Error classification (429/5xx → retryable, other → non-retryable)

Note: `ThinkingDelta` (extended thinking) not yet wired — Phase 6.

### OpenAIProvider

```bash
pip install meta-harney[openai]
```

```python
from meta_harney import OpenAIProvider, RuntimeConfig

provider = OpenAIProvider(
    api_key="sk-...",
    base_url=None,                  # optional (Azure, local proxies)
    default_max_tokens=4096,
)

config = RuntimeConfig(model="gpt-4o")
```

Supported features:
- Streaming text + tool calls (per-index accumulation)
- Multi-modal: `ImageBlock` (`image_url` content parts)
- In-band system messages
- Function calling with `tool_calls` array
- Error classification (429 → retryable via `RateLimitError`, 5xx →
  retryable, other → non-retryable)

## Writing a custom provider

The `LLMProvider` Protocol is structural — no inheritance required:

```python
from collections.abc import AsyncGenerator
from meta_harney.abstractions._types import Message
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)


class MyLocalLlamaProvider:
    """Adapter for a local Llama.cpp-style endpoint."""

    def __init__(self, base_url: str):
        self._base_url = base_url

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        # 1. Convert messages to your wire format
        # 2. Open SSE/HTTP stream to self._base_url
        # 3. For each chunk:
        async for chunk in self._http_stream(...):
            if chunk.text:
                yield ProviderTextDelta(text=chunk.text)
            if chunk.tool_call:
                yield ProviderToolCall(
                    invocation_id=chunk.tool_call.id,
                    name=chunk.tool_call.name,
                    args=chunk.tool_call.args,
                )
        # 4. Always end with stream_done
        yield ProviderStreamDone(stop_reason="end_turn")
```

Required contract:
- Yields at least one `ProviderStreamDone` as the final event
- Raises `RetryableProviderError` on 429/5xx/network errors
- Raises `NonRetryableProviderError` on auth/invalid-request errors

Apply `LLMProviderContract` to your impl:

```python
from tests.contracts.llm_provider import LLMProviderContract

class TestMyLocalLlamaContract(LLMProviderContract):
    def make_provider(self):
        return MyLocalLlamaProvider(base_url="http://localhost:8080")
```

## Stream event reference

| Event | When | Fields |
|---|---|---|
| `ProviderTextDelta` | LLM emits text | `text: str` |
| `ProviderToolCall` | LLM requests a tool | `invocation_id`, `name`, `args: dict` |
| `ProviderStreamDone` | End of stream | `stop_reason`, `input_tokens?`, `output_tokens?` |

`stop_reason` valid values: `"end_turn"` | `"tool_use"` | `"max_tokens"` | `"error"`.

## Configuration

`ProviderCallConfig` is the per-call snapshot derived from `RuntimeConfig`:

| Field | Source | Purpose |
|---|---|---|
| `model` | `RuntimeConfig.model` | which LLM to call |
| `max_tokens` | `RuntimeConfig.max_tokens` | optional output cap |
| `temperature` | `RuntimeConfig.temperature` | optional sampling temp |

For provider-specific knobs (e.g., Anthropic's `top_k`), pass them to your
provider's constructor and use them internally.

## Retry behavior

The engine wraps every `provider.stream()` call in `retry_with_backoff` using
`RuntimeConfig.retry: RetryConfig`. Defaults: 3 attempts, 1s initial delay,
2.0× backoff, 30s cap. Only `RetryableProviderError` triggers retry.
```

- [ ] **Step 2: Commit**

```bash
git add docs/providers.md
git commit -m "docs: add docs/providers.md

Anthropic + OpenAI provider setup, custom provider example, stream event
reference, ProviderCallConfig fields, retry semantics."
```

---

## Task 13: docs/testing.md

**Files:**
- Create: `docs/testing.md`

- [ ] **Step 1: Write `docs/testing.md`**

```markdown
# Testing your agent

meta-harney ships a `testing` module with scriptable fakes so business apps
can test their custom tools, hooks, and permission policies without hitting
real LLM APIs.

## Quick test: agent invokes a tool

```python
import pytest
from pydantic import BaseModel
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.testing import FakeRound, runtime_for_testing


class _LookupInput(BaseModel):
    customer_id: str


class LookupCustomerTool(BaseTool):
    name = "lookup_customer"
    description = "Find a customer."
    input_schema = _LookupInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output={"id": inv.args["customer_id"], "name": "Acme"})


async def test_agent_uses_lookup_tool():
    from meta_harney.providers.base import ProviderToolCall

    rt = runtime_for_testing(
        scripted_rounds=[
            FakeRound(
                tool_calls=[ProviderToolCall(
                    invocation_id="t1",
                    name="lookup_customer",
                    args={"customer_id": "C-001"},
                )],
                stop_reason="tool_use",
            ),
            FakeRound(text="Customer C-001 is Acme.", stop_reason="end_turn"),
        ],
        tools={"lookup_customer": LookupCustomerTool()},
    )
    session = await rt.create_session()
    final = await rt.invoke(session.id, "Who is C-001?")
    assert "Acme" in final.content[0].text
```

## FakeLLMProvider

The fake provider is **scripted** — each call to `stream()` consumes the next
`FakeRound` from the list. Useful for:
- Multi-turn scenarios (provide a sequence of rounds)
- Tool-call cycles (round 1: emit tool call, round 2: respond after tool)
- Error scenarios (raise inside a FakeRound)

```python
from meta_harney.testing import FakeLLMProvider, FakeRound

provider = FakeLLMProvider(rounds=[
    FakeRound(text="ab|cd|ef", split_on="|", stop_reason="end_turn"),  # streams 3 deltas
])
```

After use, `provider.calls` is a list of `RecordedCall` snapshots — assert
what messages/tools/config the provider received:

```python
async for _ in rt.stream(session.id, "hi"):
    pass

assert provider.calls[0].system_prompt == "be helpful"
assert len(provider.calls[0].tools) == 1
```

## Custom services via runtime_for_testing kwargs

`runtime_for_testing` accepts optional overrides for any service:

```python
rt = runtime_for_testing(
    scripted_rounds=[...],
    permission_resolver=MyTenantPermission(...),   # test your custom permission
    session_store=MyPostgresStore(...),            # test integration with real DB
    hooks=[AuditHook(), RateLimitHook()],
    multi_agent=InProcessMultiAgentBackend(...),
)
```

## Contract tests for your own implementations

If you write a custom `SessionStore`, `PermissionResolver`, `TraceSink`,
`PromptBuilder`, `CompactionStrategy`, `MultiAgentBackend`, or `LLMProvider`,
inherit the matching `XContract` class to get 5-10 conformance checks for free:

```python
from tests.contracts.session_store import SessionStoreContract

class TestMyPostgresStore(SessionStoreContract):
    def make_store(self):
        return MyPostgresStore(dsn=test_db_url())
```

Available contract classes (under `tests/contracts/`):
- `SessionStoreContract` — 10 checks
- `PermissionResolverContract` — 2 checks
- `TraceSinkContract` — 4 checks
- `PromptBuilderContract` — 3 checks
- `CompactionStrategyContract` — 3 checks
- `MultiAgentBackendContract` — 5 checks
- `LLMProviderContract` — 2 checks

These tests verify your impl meets the spec semantics (e.g., `SessionStore`
must enforce optimistic locking; `TraceSink` must not raise from `emit()`).

## Pytest configuration

meta-harney uses pytest-asyncio in **auto mode**. Test functions can be
`async def` directly:

```python
# tests/conftest.py — included if you fork meta-harney
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Set this in your own `pyproject.toml` if you don't already have it.
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing.md
git commit -m "docs: add docs/testing.md

Quickstart with FakeRound + scripted scenarios. RecordedCall inspection.
runtime_for_testing kwargs. Contract test pattern for custom impls.
pytest-asyncio note."
```

---

## Task 14: v0.0.5 release — version bump + tag + final quality gates

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version**

In `src/meta_harney/__init__.py`: `__version__ = "0.0.4"` → `__version__ = "0.0.5"`.
In `pyproject.toml`: `version = "0.0.4"` → `version = "0.0.5"`.

Update the module docstring of `__init__.py` from "Phase 4 status" to "Phase 5 status" mentioning OpenAI provider + documentation.

- [ ] **Step 2: Run all quality gates**

```bash
source .venv/bin/activate
pytest -v 2>&1 | tail -5
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -2
```

Expected: all clean. Total tests ~260+ (Phase 4 was 247; Phase 5 adds ~13 OpenAI tests).

- [ ] **Step 3: Smoke test public API**

```bash
python -c "
import meta_harney as mh
print('Version:', mh.__version__)
print('Exports:', len(mh.__all__))
assert mh.OpenAIProvider
assert mh.AnthropicProvider
assert mh.runtime_for_testing
print('OK')
"
```

Expected: Version 0.0.5, exports 54.

- [ ] **Step 4: Commit + tag**

```bash
git add src/meta_harney/__init__.py pyproject.toml
git commit -m "release: bump version to 0.0.5 for Phase 5 milestone

Phase 5 deliverables:
- OpenAIProvider (Chat Completions, streaming, tool_calls, error classification)
- README.md rewrite
- docs/architecture.md, abstractions.md, providers.md, testing.md

Phase 6 candidates: ThinkingDelta wiring, CRM mini-demo, multi-turn-session E2E."

git tag -a v0.0.5 HEAD -m "meta-harney v0.0.5 — Phase 5 (OpenAI + Docs)

Builds on v0.0.4. Adds:

Second real LLM provider:
- OpenAIProvider via official openai SDK (optional dep)
- Chat Completions message format (in-band system, tool_calls array, role=tool)
- Streaming chunks with per-index tool_call accumulation
- finish_reason → stop_reason mapping (stop→end_turn, length→max_tokens,
  tool_calls→tool_use)
- RateLimitError / APIStatusError 5xx → Retryable, other → NonRetryable
- Passes LLMProviderContract

User-facing documentation:
- README.md rewritten with quickstart + 9-abstractions table + provider matrix
- docs/architecture.md — system overview, turn lifecycle, two event streams
- docs/abstractions.md — reference for the 9 core interfaces
- docs/providers.md — Anthropic + OpenAI setup + custom provider guide
- docs/testing.md — FakeLLMProvider + runtime_for_testing + contract tests

Tests: ~260/260 passing. mypy strict + ruff clean.

Phase 6 candidates:
- ThinkingDelta wiring (Anthropic extended thinking)
- CRM mini-demo as end-to-end business example
- Multi-turn-session E2E (spec §8.4 #4)"
```

---

## Phase 5 Completion Checklist

- [ ] `from meta_harney import OpenAIProvider` works
- [ ] `pytest -v` reports ≥ 260 passes, 0 failures
- [ ] `mypy src/meta_harney` reports 0 errors
- [ ] `mypy tests` reports 0 errors
- [ ] `ruff check src/meta_harney tests` reports 0 issues
- [ ] `ruff format --check` reports 0 differences
- [ ] `pip install meta-harney[openai]` extras declared
- [ ] OpenAIProvider handles text + tool_calls + error classification
- [ ] OpenAIProvider passes LLMProviderContract
- [ ] All 5 doc files present in repo root + docs/
- [ ] v0.0.5 tag exists on HEAD

**Phase 6 (next plan):**
- ThinkingDelta wiring (Anthropic extended thinking)
- CRM mini-demo
- Multi-turn-session E2E

---

## Self-Review

**Spec coverage:**
- §3 Repository Structure: `providers/openai.py` ✓
- §5 Engine: unchanged
- §7 Error handling: OpenAI errors classified
- §8.5 Testing: docs/testing.md references meta_harney.testing

**Phase 4 carry-over status:**
- ⏸ ThinkingDelta — still no provider emits it. Deferred to Phase 6.
- ⏸ CRM demo — Phase 6.

**Placeholder scan:** No "TBD"/"TODO"/"later".

**Type consistency:**
- `OpenAIProvider(api_key, base_url, default_max_tokens)` constructor consistent with `AnthropicProvider`
- `_convert_messages_to_openai(messages, *, system_prompt)` signature consistent across Tasks 2, 4, 5, 6, 7
- `_convert_tools_to_openai(tools)` signature consistent across Tasks 3, 4
- `_FakeOpenAIStream`, `_make_chunk`, `_make_usage` helpers consistent across Tasks 4, 5, 6, 7
- `stop_map` keys consistent: "stop"→"end_turn", "length"→"max_tokens", "tool_calls"/"function_call"→"tool_use"
