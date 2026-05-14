from typing import Literal

from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from tests.contracts.permission_resolver import PermissionResolverContract


class TestAllowAll(PermissionResolverContract):
    def make_resolver(self) -> AllowAllPermissionResolver:
        return AllowAllPermissionResolver()

    def expected_verdict(self) -> Literal["allow", "deny", "ask"]:
        return "allow"


async def test_allow_all_no_reason() -> None:
    r = AllowAllPermissionResolver()
    inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.reason is None
