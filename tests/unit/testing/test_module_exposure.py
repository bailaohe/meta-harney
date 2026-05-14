"""Tests for meta_harney.testing module exposure."""

from __future__ import annotations


def test_testing_module_reexports_fake_provider() -> None:
    from meta_harney.testing import FakeLLMProvider, FakeRound

    assert FakeLLMProvider
    assert FakeRound


def test_testing_module_reexports_runtime_helper() -> None:
    from meta_harney.testing import runtime_for_testing

    assert runtime_for_testing


def test_runtime_for_testing_returns_agentruntime() -> None:
    from meta_harney import AgentRuntime
    from meta_harney.testing import FakeRound, runtime_for_testing

    rt = runtime_for_testing(
        scripted_rounds=[FakeRound(text="ok", stop_reason="end_turn")],
    )
    assert isinstance(rt, AgentRuntime)


async def test_runtime_for_testing_works_end_to_end() -> None:
    """Full turn via runtime_for_testing should succeed."""
    from meta_harney.abstractions._types import TextBlock
    from meta_harney.testing import FakeRound, runtime_for_testing

    rt = runtime_for_testing(
        scripted_rounds=[FakeRound(text="hello from helper", stop_reason="end_turn")],
    )
    session = await rt.create_session()
    final = await rt.invoke(session.id, "hi")
    assert final.role == "assistant"
    assert isinstance(final.content[0], TextBlock)
    assert "hello from helper" in final.content[0].text
