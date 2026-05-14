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
