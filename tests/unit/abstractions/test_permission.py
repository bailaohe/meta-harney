"""Tests for PermissionResolver Protocol + PermissionDecision."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meta_harney.abstractions.permission import (
    PermissionDecision,
    PermissionResolver,
)
from meta_harney.abstractions.tool import ToolInvocation


def test_permission_decision_allow():
    d = PermissionDecision(verdict="allow")
    assert d.verdict == "allow"
    assert d.reason is None


def test_permission_decision_deny():
    d = PermissionDecision(verdict="deny", reason="path forbidden")
    assert d.verdict == "deny"
    assert d.reason == "path forbidden"


def test_permission_decision_ask():
    d = PermissionDecision(verdict="ask")
    assert d.verdict == "ask"


def test_permission_decision_invalid_verdict():
    with pytest.raises(ValidationError):
        PermissionDecision(verdict="maybe")  # type: ignore


async def test_protocol_is_satisfied_by_duck_typing():
    """PermissionResolver is a Protocol — any class with `resolve()` matches."""

    class AllowAll:
        async def resolve(self, invocation, session_id):
            return PermissionDecision(verdict="allow")

    resolver: PermissionResolver = AllowAll()
    inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
    d = await resolver.resolve(inv, "s")
    assert d.verdict == "allow"
