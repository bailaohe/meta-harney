"""Tests for engine.retry helpers."""
from __future__ import annotations

import pytest

from meta_harney.engine.retry import RetryConfig, compute_backoff, retry_with_backoff
from meta_harney.errors import NonRetryableProviderError, RetryableProviderError


def test_retry_config_defaults() -> None:
    c = RetryConfig()
    assert c.max_attempts == 3
    assert c.initial_delay_s == 1.0
    assert c.backoff_multiplier == 2.0
    assert c.max_delay_s == 30.0


def test_compute_backoff_exponential() -> None:
    c = RetryConfig(initial_delay_s=1.0, backoff_multiplier=2.0, max_delay_s=100.0)
    assert compute_backoff(c, attempt=1) == 1.0
    assert compute_backoff(c, attempt=2) == 2.0
    assert compute_backoff(c, attempt=3) == 4.0


def test_compute_backoff_clamped_by_max() -> None:
    c = RetryConfig(initial_delay_s=1.0, backoff_multiplier=10.0, max_delay_s=5.0)
    assert compute_backoff(c, attempt=1) == 1.0
    assert compute_backoff(c, attempt=2) == 5.0  # clamped
    assert compute_backoff(c, attempt=3) == 5.0  # still clamped


async def test_retry_with_backoff_returns_on_success() -> None:
    async def f() -> str:
        return "ok"

    result = await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert result == "ok"


async def test_retry_with_backoff_retries_retryable() -> None:
    attempts: list[int] = []

    async def f() -> str:
        attempts.append(1)
        if len(attempts) < 2:
            raise RetryableProviderError("transient")
        return "eventually"

    result = await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert result == "eventually"
    assert len(attempts) == 2


async def test_retry_with_backoff_gives_up_after_max() -> None:
    async def f() -> str:
        raise RetryableProviderError("always fails")

    with pytest.raises(RetryableProviderError):
        await retry_with_backoff(
            f, RetryConfig(max_attempts=3, initial_delay_s=0.0)
        )


async def test_retry_with_backoff_does_not_retry_nonretryable() -> None:
    attempts: list[int] = []

    async def f() -> str:
        attempts.append(1)
        raise NonRetryableProviderError("auth fail")

    with pytest.raises(NonRetryableProviderError):
        await retry_with_backoff(f, RetryConfig(max_attempts=3, initial_delay_s=0.0))
    assert len(attempts) == 1  # NOT retried
