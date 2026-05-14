# LLM Providers

meta-harney's `LLMProvider` Protocol decouples the engine from any specific
LLM backend. The runtime calls `provider.stream()` to consume a single LLM
round; everything else (retry, tool dispatch, message assembly) is
provider-agnostic.

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
