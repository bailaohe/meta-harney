"""Tests for BaseHook, HookEvent, HookDecision."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from meta_harney.abstractions.hook import (
    BaseHook,
    HookDecision,
    HookEvent,
    HookEventKind,
)


def test_hook_event_kinds():
    valid: list[HookEventKind] = [
        "pre_tool",
        "post_tool",
        "pre_llm",
        "post_llm",
        "session_start",
        "session_end",
        "turn_complete",
    ]
    for kind in valid:
        ev = HookEvent(kind=kind, session_id="s1", payload={})
        assert ev.kind == kind


def test_hook_event_invalid_kind():
    with pytest.raises(ValidationError):
        HookEvent(kind="bogus", session_id="s1", payload={})  # type: ignore


def test_hook_decision_defaults():
    d = HookDecision()
    assert d.allow is True
    assert d.transform is None
    assert d.reason is None


def test_hook_decision_deny():
    d = HookDecision(allow=False, reason="blocked")
    assert not d.allow
    assert d.reason == "blocked"


def test_hook_decision_with_transform():
    d = HookDecision(transform={"args": {"x": 99}})
    assert d.transform == {"args": {"x": 99}}


def test_base_hook_is_abstract():
    with pytest.raises(TypeError):
        BaseHook()  # type: ignore[abstract]


def test_concrete_hook_subclass():
    class LogHook(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool", "post_tool"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(allow=True)

    h = LogHook()
    assert h.subscribed_events == {"pre_tool", "post_tool"}
