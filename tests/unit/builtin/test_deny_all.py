from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
from tests.contracts.permission_resolver import PermissionResolverContract


class TestDenyAll(PermissionResolverContract):
    def make_resolver(self) -> DenyAllPermissionResolver:
        return DenyAllPermissionResolver()

    def expected_verdict(self) -> str:
        return "deny"


async def test_deny_all_custom_reason() -> None:
    r = DenyAllPermissionResolver(reason="policy: deny by default")
    inv = ToolInvocation(name="x", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.reason == "policy: deny by default"
