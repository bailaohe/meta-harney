"""Unit tests for the OpenAI-compat vendor-quirks module.

The double-gate (endpoint + model name) is the safety-critical contract:
quirks must NOT fire for OpenAI proper, must fire for DeepSeek reasoners,
and must not fire for either gate alone. These tests pin that exact
matrix down.
"""

from __future__ import annotations

from meta_harney.providers.openai_quirks import (
    deepseek_thinking_extras,
    is_deepseek_reasoner,
    requires_reasoning_content_replay,
)


# ---------------------------------------------------------------------------
# is_deepseek_reasoner — gate matrix
# ---------------------------------------------------------------------------


def test_deepseek_endpoint_and_reasoner_model_fires() -> None:
    """Both gates closed → quirk fires."""
    assert is_deepseek_reasoner("deepseek-chat", "https://api.deepseek.com")
    assert is_deepseek_reasoner("deepseek-reasoner", "https://api.deepseek.com")
    assert is_deepseek_reasoner("deepseek-v4-pro", "https://api.deepseek.com/v1")
    assert is_deepseek_reasoner("deepseek-v4-flash", "https://api.deepseek.cn")


def test_openai_endpoint_with_deepseek_named_model_does_not_fire() -> None:
    """User has a custom 'deepseek-chat' alias pointed at OpenAI proper for
    testing — must NOT inject DeepSeek extension fields, OpenAI would 400."""
    assert not is_deepseek_reasoner(
        "deepseek-chat", "https://api.openai.com/v1"
    )
    assert not is_deepseek_reasoner(
        "deepseek-reasoner", "https://api.openai.com/v1"
    )


def test_deepseek_endpoint_with_non_reasoner_model_does_not_fire() -> None:
    """Hitting DeepSeek with a non-reasoner model (e.g. legacy deepseek-coder)
    must not get thinking-mode treatment."""
    assert not is_deepseek_reasoner(
        "deepseek-coder", "https://api.deepseek.com"
    )


def test_openai_proper_models_never_fire() -> None:
    """Standard OpenAI models must never trigger the quirks regardless of
    endpoint variation."""
    for model in ("gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o3", "o4-mini"):
        assert not is_deepseek_reasoner(model, "https://api.openai.com/v1")
        assert not is_deepseek_reasoner(model, "https://api.deepseek.com")


def test_anthropic_and_other_vendors_never_fire() -> None:
    """Models routed through OpenAI-protocol passthroughs for non-DeepSeek
    vendors must not pick up DeepSeek's thinking-mode fields."""
    assert not is_deepseek_reasoner(
        "claude-sonnet-4-5", "https://api.anthropic.com"
    )
    assert not is_deepseek_reasoner(
        "qwen-reasoning-plus", "https://dashscope.aliyuncs.com"
    )
    assert not is_deepseek_reasoner(
        "kimi-k2", "https://api.moonshot.cn"
    )


def test_none_base_url_never_fires() -> None:
    """`base_url=None` (caller used SDK default) is treated as OpenAI proper —
    safer to under-fire than risk 400ing on the default OpenAI endpoint."""
    assert not is_deepseek_reasoner("deepseek-chat", None)
    assert not is_deepseek_reasoner("deepseek-reasoner", None)


# ---------------------------------------------------------------------------
# deepseek_thinking_extras — body shape
# ---------------------------------------------------------------------------


def test_thinking_extras_returns_empty_when_gate_off() -> None:
    """Caller can merge unconditionally — empty dict is the no-op signal."""
    assert deepseek_thinking_extras("gpt-4o", "https://api.openai.com/v1") == {}
    assert deepseek_thinking_extras("deepseek-coder", "https://api.deepseek.com") == {}


def test_thinking_extras_returns_thinking_enabled_and_effort_when_gate_on() -> None:
    """The two fields move together — DeepSeek-TUI's
    `apply_reasoning_effort` sets both for the DeepSeek provider family
    (client.rs:920-923)."""
    extras = deepseek_thinking_extras("deepseek-reasoner", "https://api.deepseek.com")
    assert extras == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }


# ---------------------------------------------------------------------------
# requires_reasoning_content_replay — multi-turn rule
# ---------------------------------------------------------------------------


def test_replay_requirement_mirrors_reasoner_gate() -> None:
    """Currently scoped to DeepSeek reasoners; the predicate must agree
    with `is_deepseek_reasoner`. If the two diverge, downstream
    `_convert_messages_to_openai` will start producing 400-triggering
    payloads for tool follow-ups."""
    cases = [
        ("deepseek-chat", "https://api.deepseek.com", True),
        ("gpt-4o", "https://api.openai.com/v1", False),
        ("deepseek-chat", "https://api.openai.com/v1", False),
        ("claude-sonnet", "https://api.anthropic.com", False),
    ]
    for model, base_url, expected in cases:
        assert requires_reasoning_content_replay(model, base_url) is expected
        assert is_deepseek_reasoner(model, base_url) is expected
