"""Tests for hook dispatch helpers."""

from __future__ import annotations

from typing import ClassVar

import pytest

from meta_harney.abstractions.hook import BaseHook, HookDecision, HookEvent, HookEventKind
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.hook_dispatch import dispatch_hooks
from meta_harney.errors import HookHaltError


class _AllowHook(BaseHook):
    subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool", "post_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(allow=True)


class _DenyHook(BaseHook):
    subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(allow=False, reason="policy")


class _HaltHook(BaseHook):
    subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        raise HookHaltError(reason="user-requested stop")


class _TransformHook(BaseHook):
    subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        return HookDecision(transform={"args": {"x": 42}})


class _RaiseHook(BaseHook):
    subscribed_events: ClassVar[set[HookEventKind]] = {"pre_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        raise RuntimeError("hook bug")


async def test_dispatch_skips_non_subscribed() -> None:
    class _SessionHook(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"session_start"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(allow=False)

    result = await dispatch_hooks(
        hooks=[_SessionHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is True  # default when no hook fires
    assert result.transform is None


async def test_dispatch_all_allow() -> None:
    result = await dispatch_hooks(
        hooks=[_AllowHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is True


async def test_dispatch_first_deny_short_circuits() -> None:
    result = await dispatch_hooks(
        hooks=[_DenyHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.allow is False
    assert result.reason == "policy"


async def test_dispatch_halt_propagates() -> None:
    with pytest.raises(HookHaltError, match="user-requested stop"):
        await dispatch_hooks(
            hooks=[_HaltHook()],
            event=HookEvent(kind="pre_tool", session_id="s", payload={}),
            sink=NullSink(),
            current_span_id="parent",
        )


async def test_dispatch_transform_pre_event_returned() -> None:
    """transform on pre_* events is returned in the merged decision."""
    result = await dispatch_hooks(
        hooks=[_TransformHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.transform == {"args": {"x": 42}}


async def test_dispatch_transform_on_post_ignored() -> None:
    """transform on post_* is ignored per spec (engine warns via trace)."""

    class _PostTransform(BaseHook):
        subscribed_events: ClassVar[set[HookEventKind]] = {"post_tool"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(transform={"foo": "bar"})

    result = await dispatch_hooks(
        hooks=[_PostTransform()],
        event=HookEvent(kind="post_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    assert result.transform is None  # ignored


async def test_dispatch_swallows_random_hook_exception() -> None:
    """Non-Halt exceptions in hooks are logged via trace and execution continues (fail-open)."""
    result = await dispatch_hooks(
        hooks=[_RaiseHook(), _AllowHook()],
        event=HookEvent(kind="pre_tool", session_id="s", payload={}),
        sink=NullSink(),
        current_span_id="parent",
    )
    # _RaiseHook fail-open, _AllowHook proceeds
    assert result.allow is True
