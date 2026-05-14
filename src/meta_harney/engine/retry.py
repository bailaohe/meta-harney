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
    assert last_exc is not None
    raise last_exc
