"""Contract tests for PermissionResolver implementations."""

from __future__ import annotations

from abc import abstractmethod
from typing import Literal

from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.tool import ToolInvocation


class PermissionResolverContract:
    """Contract tests every PermissionResolver must pass.

    `expected_verdict` lets the subclass declare which verdict the
    resolver should produce so we can write generic assertions.
    """

    @abstractmethod
    def make_resolver(self) -> PermissionResolver: ...

    @abstractmethod
    def expected_verdict(self) -> Literal["allow", "deny", "ask"]: ...

    async def test_returns_expected_verdict(self) -> None:
        resolver = self.make_resolver()
        inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
        d = await resolver.resolve(inv, "s")
        assert d.verdict == self.expected_verdict()

    async def test_verdict_is_consistent_across_calls(self) -> None:
        resolver = self.make_resolver()
        inv1 = ToolInvocation(name="a", args={"x": 1}, invocation_id="i1", session_id="s1")
        inv2 = ToolInvocation(name="b", args={"y": 2}, invocation_id="i2", session_id="s2")
        d1 = await resolver.resolve(inv1, "s1")
        d2 = await resolver.resolve(inv2, "s2")
        assert d1.verdict == d2.verdict == self.expected_verdict()
