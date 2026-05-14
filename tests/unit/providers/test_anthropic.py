"""Tests for AnthropicProvider — real-LLM-API adapter.

Tests stub the anthropic SDK at the client boundary so they're deterministic
and don't make network calls.
"""
from __future__ import annotations

import pytest

from meta_harney.providers.anthropic import AnthropicProvider


def test_anthropic_provider_constructs() -> None:
    p = AnthropicProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_anthropic_provider_requires_api_key() -> None:
    """Empty api_key should raise ConfigurationError."""
    from meta_harney.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="api_key"):
        AnthropicProvider(api_key="")
