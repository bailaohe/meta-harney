# Testing your agent

meta-harney ships a `testing` module with scriptable fakes so business apps
can test their custom tools, hooks, and permission policies without hitting
real LLM APIs.

## Quick test: agent invokes a tool

```python
import pytest
from pydantic import BaseModel
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.testing import FakeRound, runtime_for_testing


class _LookupInput(BaseModel):
    customer_id: str


class LookupCustomerTool(BaseTool):
    name = "lookup_customer"
    description = "Find a customer."
    input_schema = _LookupInput

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output={"id": inv.args["customer_id"], "name": "Acme"})


async def test_agent_uses_lookup_tool():
    from meta_harney.providers.base import ProviderToolCall

    rt = runtime_for_testing(
        scripted_rounds=[
            FakeRound(
                tool_calls=[ProviderToolCall(
                    invocation_id="t1",
                    name="lookup_customer",
                    args={"customer_id": "C-001"},
                )],
                stop_reason="tool_use",
            ),
            FakeRound(text="Customer C-001 is Acme.", stop_reason="end_turn"),
        ],
        tools={"lookup_customer": LookupCustomerTool()},
    )
    session = await rt.create_session()
    final = await rt.invoke(session.id, "Who is C-001?")
    assert "Acme" in final.content[0].text
```

## FakeLLMProvider

The fake provider is **scripted** — each call to `stream()` consumes the next
`FakeRound` from the list. Useful for:
- Multi-turn scenarios (provide a sequence of rounds)
- Tool-call cycles (round 1: emit tool call, round 2: respond after tool)
- Error scenarios (raise inside a FakeRound)

```python
from meta_harney.testing import FakeLLMProvider, FakeRound

provider = FakeLLMProvider(rounds=[
    FakeRound(text="ab|cd|ef", split_on="|", stop_reason="end_turn"),  # streams 3 deltas
])
```

After use, `provider.calls` is a list of `RecordedCall` snapshots — assert
what messages/tools/config the provider received:

```python
async for _ in rt.stream(session.id, "hi"):
    pass

assert provider.calls[0].system_prompt == "be helpful"
assert len(provider.calls[0].tools) == 1
```

## Custom services via runtime_for_testing kwargs

`runtime_for_testing` accepts optional overrides for any service:

```python
rt = runtime_for_testing(
    scripted_rounds=[...],
    permission_resolver=MyTenantPermission(...),   # test your custom permission
    session_store=MyPostgresStore(...),            # test integration with real DB
    hooks=[AuditHook(), RateLimitHook()],
    multi_agent=InProcessMultiAgentBackend(...),
)
```

## Contract tests for your own implementations

If you write a custom `SessionStore`, `PermissionResolver`, `TraceSink`,
`PromptBuilder`, `CompactionStrategy`, `MultiAgentBackend`, or `LLMProvider`,
inherit the matching `XContract` class to get 5-10 conformance checks for free:

```python
from tests.contracts.session_store import SessionStoreContract

class TestMyPostgresStore(SessionStoreContract):
    def make_store(self):
        return MyPostgresStore(dsn=test_db_url())
```

Available contract classes (under `tests/contracts/`):
- `SessionStoreContract` — 10 checks
- `PermissionResolverContract` — 2 checks
- `TraceSinkContract` — 4 checks
- `PromptBuilderContract` — 3 checks
- `CompactionStrategyContract` — 3 checks
- `MultiAgentBackendContract` — 5 checks
- `LLMProviderContract` — 2 checks

These tests verify your impl meets the spec semantics (e.g., `SessionStore`
must enforce optimistic locking; `TraceSink` must not raise from `emit()`).

## Pytest configuration

meta-harney uses pytest-asyncio in **auto mode**. Test functions can be
`async def` directly:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Set this in your own `pyproject.toml` if you don't already have it.
