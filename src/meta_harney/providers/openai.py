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
