"""Tests for the Provider Catalog (Phase 9a)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from meta_harney.providers.anthropic import AnthropicProvider
from meta_harney.providers.catalog import (
    BUILT_IN_PROVIDERS,
    ProviderSpec,
    provider_from_spec,
    register_provider,
)
from meta_harney.providers.openai import OpenAIProvider


def test_provider_spec_construction() -> None:
    spec = ProviderSpec(
        name="foo",
        kind="openai",
        base_url="https://example.com/v1",
        default_model="foo-model",
        description="example",
    )
    assert spec.name == "foo"
    assert spec.kind == "openai"
    assert spec.base_url == "https://example.com/v1"
    assert spec.default_model == "foo-model"
    assert spec.description == "example"


def test_provider_spec_is_frozen() -> None:
    spec = ProviderSpec(name="x", kind="openai", base_url=None, default_model="y")
    with pytest.raises(FrozenInstanceError):
        spec.name = "z"  # type: ignore[misc]


def test_provider_spec_with_invalid_kind_caught_by_mypy_not_runtime() -> None:
    spec = ProviderSpec(
        name="future",
        kind=cast(Any, "vertex"),
        base_url=None,
        default_model="x",
    )
    assert spec.name == "future"


_EXPECTED_NAMES = {
    "anthropic",
    "openai",
    "moonshot",
    "deepseek",
    "gemini",
    "minimax",
    "nvidia",
    "dashscope",
    "modelscope",
}


def test_built_in_providers_contains_all_nine() -> None:
    assert set(BUILT_IN_PROVIDERS.keys()) == _EXPECTED_NAMES
    for name, spec in BUILT_IN_PROVIDERS.items():
        assert spec.name == name
        assert spec.kind in {"anthropic", "openai"}
        assert spec.default_model


def test_built_in_providers_anthropic_and_openai_have_none_base_url() -> None:
    assert BUILT_IN_PROVIDERS["anthropic"].base_url is None
    assert BUILT_IN_PROVIDERS["openai"].base_url is None
    for name in _EXPECTED_NAMES - {"anthropic", "openai"}:
        spec = BUILT_IN_PROVIDERS[name]
        assert spec.base_url is not None
        assert spec.base_url.startswith("https://"), f"{name}: {spec.base_url}"


def test_provider_from_spec_anthropic_constructs_anthropic_provider() -> None:
    spec = BUILT_IN_PROVIDERS["anthropic"]
    p = provider_from_spec(spec, api_key="sk-ant-test")
    assert isinstance(p, AnthropicProvider)
    assert p._api_key == "sk-ant-test"
    assert p._base_url is None


def test_provider_from_spec_openai_constructs_openai_provider() -> None:
    spec = BUILT_IN_PROVIDERS["moonshot"]
    p = provider_from_spec(spec, api_key="sk-moon")
    assert isinstance(p, OpenAIProvider)
    assert p._api_key == "sk-moon"
    assert p._base_url == "https://api.moonshot.cn/v1"


def test_provider_from_spec_unknown_kind_raises() -> None:
    bad_spec = ProviderSpec(
        name="future-vertex",
        kind=cast(Any, "vertex"),
        base_url=None,
        default_model="x",
    )
    with pytest.raises(ValueError, match="unknown provider kind"):
        provider_from_spec(bad_spec, api_key="k")


@pytest.fixture
def _clean_register() -> object:
    yield None
    for name in list(BUILT_IN_PROVIDERS.keys()):
        if name not in _EXPECTED_NAMES:
            del BUILT_IN_PROVIDERS[name]


def test_register_provider_adds_new_spec(_clean_register: object) -> None:
    spec = ProviderSpec(
        name="local-llama",
        kind="openai",
        base_url="http://localhost:8080/v1",
        default_model="llama-3.1-8b",
    )
    register_provider(spec)
    assert "local-llama" in BUILT_IN_PROVIDERS
    assert BUILT_IN_PROVIDERS["local-llama"].base_url == "http://localhost:8080/v1"


def test_register_provider_existing_name_without_overwrite_raises(
    _clean_register: object,
) -> None:
    duplicate = ProviderSpec(
        name="openai",
        kind="openai",
        base_url="https://different/v1",
        default_model="z",
    )
    with pytest.raises(ValueError, match="already registered"):
        register_provider(duplicate)
    register_provider(duplicate, overwrite=True)
    assert BUILT_IN_PROVIDERS["openai"].base_url == "https://different/v1"
    # Restore the original openai spec
    register_provider(
        ProviderSpec(
            name="openai",
            kind="openai",
            base_url=None,
            default_model="gpt-4o",
            description="OpenAI (official)",
        ),
        overwrite=True,
    )
