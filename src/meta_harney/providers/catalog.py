"""Provider catalog: built-in provider specs + factory + extension hook.

Generic infrastructure for multi-provider apps. Specs are plain data
(frozen dataclasses). `provider_from_spec()` is the only factory you need.
`register_provider()` lets apps inject custom specs at startup.

Phase 9a addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from meta_harney.providers.anthropic import AnthropicProvider
from meta_harney.providers.base import LLMProvider
from meta_harney.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata for a known LLM provider.

    Specs are immutable. To replace a spec at runtime, call
    `register_provider(new_spec, overwrite=True)`.
    """

    name: str
    kind: Literal["anthropic", "openai"]
    base_url: str | None
    default_model: str
    description: str = ""


BUILT_IN_PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        kind="anthropic",
        base_url=None,
        default_model="claude-sonnet-4-5",
        description="Anthropic Claude (official)",
    ),
    "openai": ProviderSpec(
        name="openai",
        kind="openai",
        base_url=None,
        default_model="gpt-4o",
        description="OpenAI (official)",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        kind="openai",
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2-0905-preview",
        description="Moonshot AI (Kimi, OpenAI-compatible)",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        kind="openai",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        description="DeepSeek (OpenAI-compatible)",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        kind="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.0-flash",
        description="Google Gemini (OpenAI-compatible endpoint)",
    ),
    "minimax": ProviderSpec(
        name="minimax",
        kind="openai",
        base_url="https://api.minimax.io/v1",
        default_model="MiniMax-M2",
        description="MiniMax (OpenAI-compatible)",
    ),
    "nvidia": ProviderSpec(
        name="nvidia",
        kind="openai",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="meta/llama-3.1-405b-instruct",
        description="NVIDIA NIM (OpenAI-compatible)",
    ),
    "dashscope": ProviderSpec(
        name="dashscope",
        kind="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        description="Alibaba Dashscope (OpenAI-compatible)",
    ),
    "modelscope": ProviderSpec(
        name="modelscope",
        kind="openai",
        base_url="https://api-inference.modelscope.cn/v1",
        default_model="Qwen/Qwen2.5-72B-Instruct",
        description="ModelScope (OpenAI-compatible)",
    ),
}


def provider_from_spec(
    spec: ProviderSpec,
    *,
    api_key: str,
    model: str | None = None,
) -> LLMProvider:
    """Build an LLMProvider from a spec + api_key.

    `model` is accepted for API symmetry but unused here; the engine
    consumes the model id via RuntimeConfig. Higher-level callers can
    use spec.default_model as their default.

    Raises:
        ValueError: When spec.kind is not "anthropic" or "openai".
    """
    if spec.kind == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=spec.base_url)
    if spec.kind == "openai":
        return OpenAIProvider(api_key=api_key, base_url=spec.base_url)
    raise ValueError(f"unknown provider kind: {spec.kind!r}")


def register_provider(
    spec: ProviderSpec,
    *,
    overwrite: bool = False,
) -> None:
    """Register or replace a provider spec at runtime.

    Args:
        spec: The provider spec to register.
        overwrite: If False (default), raises ValueError when a provider
            with the same name already exists. Set to True to replace.

    Raises:
        ValueError: When the name conflicts and overwrite=False.

    Thread safety: not thread-safe. Intended for startup-time
    configuration. Do not call from request paths or worker threads.
    """
    if not overwrite and spec.name in BUILT_IN_PROVIDERS:
        raise ValueError(
            f"provider {spec.name!r} already registered "
            f"(use overwrite=True to replace)"
        )
    BUILT_IN_PROVIDERS[spec.name] = spec
