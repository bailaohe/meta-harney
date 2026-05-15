"""Tests for engine.loop._open_provider_stream_with_retry.

The key contract (changed in 0.2.7 to fix the streaming-burst bug):
  * Retryable errors raised BEFORE the first event arrives → retry.
  * Retryable errors raised AFTER the first event arrives → propagate.
  * Successful streams pass through every event in real time without
    buffering.

Previously the engine collected the entire stream into a list before
yielding — that made retry trivially safe but turned every truly-streamed
reasoning span (DeepSeek, Anthropic thinking) into a single-frame burst.
The wire-level real pacing was confirmed by direct curl probing of
DeepSeek's API: ~30ms per packet, not 90ms total. We never want to
re-introduce the collect step.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.engine.loop import _open_provider_stream_with_retry
from meta_harney.engine.retry import RetryConfig
from meta_harney.errors import (
    NonRetryableProviderError,
    RetryableProviderError,
)
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ToolSpec,
)


class _ScriptedProvider(LLMProvider):
    """LLMProvider stub whose `stream` plays out a scripted sequence of
    events/exceptions per call. Tracks attempt count so tests can assert
    on retry behavior."""

    def __init__(self, scripts: list[list[object]]) -> None:
        # Each inner list is the sequence emitted for that attempt. Items
        # that are `Exception` instances are raised at that position;
        # everything else is yielded as-is.
        self._scripts = scripts
        self.attempts = 0

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolSpec],
        config: ProviderCallConfig,
    ) -> AsyncGenerator[ProviderStreamEvent, None]:
        script = self._scripts[self.attempts]
        self.attempts += 1
        for item in script:
            if isinstance(item, BaseException):
                raise item
            yield item  # type: ignore[misc]


def _msgs() -> list[Message]:
    return [Message(role="user", content=[TextBlock(text="x")])]


async def _drain(
    provider: LLMProvider,
    retry_config: RetryConfig | None = None,
) -> list[ProviderStreamEvent]:
    out: list[ProviderStreamEvent] = []
    async for ev in _open_provider_stream_with_retry(
        provider,
        _msgs(),
        system_prompt="",
        tool_specs=[],
        call_config=ProviderCallConfig(model="x"),
        retry_config=retry_config
        or RetryConfig(max_attempts=3, initial_delay_s=0.0),
    ):
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Happy path: stream passes through verbatim
# ---------------------------------------------------------------------------


async def test_stream_passes_events_through_in_order() -> None:
    """Real-time forwarding contract: no buffering, no reordering."""
    events = [
        ProviderTextDelta(text="a"),
        ProviderTextDelta(text="b"),
        ProviderStreamDone(stop_reason="end_turn"),
    ]
    provider = _ScriptedProvider([events])

    out = await _drain(provider)

    assert out == events
    assert provider.attempts == 1


# ---------------------------------------------------------------------------
# Retry covers ONLY the pre-first-event phase
# ---------------------------------------------------------------------------


async def test_retries_when_first_event_call_raises_retryable() -> None:
    """RetryableProviderError raised before the first event → retry."""
    events = [
        ProviderTextDelta(text="ok"),
        ProviderStreamDone(stop_reason="end_turn"),
    ]
    provider = _ScriptedProvider(
        [
            [RetryableProviderError("rate limit")],
            [RetryableProviderError("rate limit again")],
            events,
        ]
    )

    out = await _drain(provider)

    assert out == events
    assert provider.attempts == 3


async def test_gives_up_after_max_attempts_on_pre_first_event_failures() -> None:
    """All attempts return RetryableProviderError at first-event time →
    raise the last error."""
    provider = _ScriptedProvider(
        [
            [RetryableProviderError("1")],
            [RetryableProviderError("2")],
            [RetryableProviderError("3")],
        ]
    )

    with pytest.raises(RetryableProviderError, match="3"):
        await _drain(provider)
    assert provider.attempts == 3


async def test_does_not_retry_when_first_event_call_raises_nonretryable() -> None:
    """NonRetryableProviderError at first-event time still propagates
    immediately — retry only applies to *retryable* errors."""
    provider = _ScriptedProvider(
        [
            [NonRetryableProviderError("nope")],
        ]
    )

    with pytest.raises(NonRetryableProviderError):
        await _drain(provider)
    assert provider.attempts == 1


# ---------------------------------------------------------------------------
# Past the first event: NO retry, errors propagate as-is
# ---------------------------------------------------------------------------


async def test_mid_stream_retryable_propagates_without_retry() -> None:
    """After the consumer has seen at least one event, a retryable error
    must propagate as-is. Retrying would require re-emitting events the
    consumer has already rendered, which is the bug we're fixing.
    """
    provider = _ScriptedProvider(
        [
            [
                ProviderTextDelta(text="partial"),
                RetryableProviderError("died mid-stream"),
            ],
            # If retry was wrongly attempted, this second script would
            # supply a clean run. The test asserts we never get here.
            [
                ProviderTextDelta(text="should not be seen"),
                ProviderStreamDone(stop_reason="end_turn"),
            ],
        ]
    )

    out: list[ProviderStreamEvent] = []
    with pytest.raises(RetryableProviderError, match="died mid-stream"):
        async for ev in _open_provider_stream_with_retry(
            provider,
            _msgs(),
            system_prompt="",
            tool_specs=[],
            call_config=ProviderCallConfig(model="x"),
            retry_config=RetryConfig(max_attempts=3, initial_delay_s=0.0),
        ):
            out.append(ev)

    assert out == [ProviderTextDelta(text="partial")]
    assert provider.attempts == 1


async def test_empty_stream_returns_cleanly() -> None:
    """A stream that immediately raises StopAsyncIteration (empty) is
    not an error condition — return cleanly, no events."""
    provider = _ScriptedProvider([[]])

    out = await _drain(provider)

    assert out == []
    assert provider.attempts == 1
