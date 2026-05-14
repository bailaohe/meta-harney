# meta-harney Abstractions Reference

The 9 core interfaces. Each is either a Protocol (structural — duck-typed) or
an ABC (nominal — subclass required). Pick the right pattern per impl style.

## BaseTool (ABC)

A capability the LLM can invoke. Subclasses declare:

- `name: ClassVar[str]` — identifier shown to the LLM
- `description: ClassVar[str]` — natural-language purpose
- `input_schema: ClassVar[type[BaseModel]]` — Pydantic schema for args
- `default_timeout: ClassVar[float | None] = None` — execution timeout
- `async def execute(inv: ToolInvocation, ctx: ToolContext) -> ToolResult`

```python
from pydantic import BaseModel
from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult


class _LookupCustomerInput(BaseModel):
    customer_id: str


class LookupCustomerTool(BaseTool):
    name = "lookup_customer"
    description = "Look up a customer by ID."
    input_schema = _LookupCustomerInput
    default_timeout = 10.0

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        cid = inv.args["customer_id"]
        record = await my_db.fetch_customer(cid)
        return ToolResult(success=True, output=record)
```

`ToolContext` exposes: `session_store`, `trace_sink`, `current_span_id`,
`new_span_id`, optional `multi_agent`.

## BaseHook (ABC)

Lifecycle event subscriber. 7 event kinds: `session_start`, `pre_llm`,
`post_llm`, `pre_tool`, `post_tool`, `turn_complete`, `session_end`.

```python
class AuditHook(BaseHook):
    subscribed_events = {"pre_tool", "post_tool"}

    async def handle(self, event: HookEvent) -> HookDecision:
        await my_audit_log.write(event)
        return HookDecision(allow=True)
```

`HookDecision`:
- `allow: bool` — `False` short-circuits the loop (returns the decision to the engine)
- `transform: dict | None` — modify pre-event payload (e.g., args override)
- `reason: str | None` — human-readable reason for the decision

Raise `HookHaltError` to halt the whole turn.

## PermissionResolver (Protocol)

Pre-execution gate per tool call. Verdict is `allow` / `deny` / `ask`:

```python
class TenantScopedPermission:
    async def resolve(self, inv: ToolInvocation, session_id: str) -> PermissionDecision:
        session = await session_store.load(session_id)
        if inv.name == "delete_customer" and session.tenant_id != "admin":
            return PermissionDecision(verdict="deny", reason="non-admin tenant")
        return PermissionDecision(verdict="allow")
```

`ask` is treated as deny in Phase 4 (no human-approval mechanism yet).

## PromptBuilder (Protocol)

```python
class PromptBuilder(Protocol):
    async def build_system_prompt(self, session_id: str) -> str: ...
    async def build_context_messages(self, session_id: str) -> list[Message]: ...
```

`MinimalPromptBuilder` (built-in) reads from a `SessionStore`. Override for
domain-specific framing.

## BaseTask (ABC)

Background-task primitive. Used by `MultiAgentBackend` (detached children
become tasks). 5 states: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`CANCELLED`.

## Session + SessionStore

`Session` carries:
- `id`, `tenant_id`, `user_id`, `parent_session_id`
- `created_at`, `version` (optimistic-lock)
- `messages: list[Message]`
- `attributes: dict` (free-form business data)
- `metadata: dict` (free-form app data)

`SessionStore` Protocol:
- `load(session_id, *, tenant_id=None) -> Session | None`
- `save(session)` — must enforce optimistic lock (raise `SessionConflictError`)
- `list(*, tenant_id=None, filter=None)`
- `delete(session_id)`

Built-ins: `MemorySessionStore`, `FileSessionStore`. Contract test:
`SessionStoreContract` (10 checks).

## TraceEvent + TraceSink

Observability stream. Every `TraceEvent` has `ts`, `session_id`, `kind`,
`span_id`, `parent_span_id`, `payload`, optional `duration_ms`.

Reserved `kind` vocabulary includes `turn.started`, `llm.completed`,
`tool.invoked`, `tool.completed`, `permission.resolved`, `hook.fired`,
`error.raised`, `compaction.triggered`, etc.

Built-ins: `NullSink` (default), `JsonlSink` (file).

## MultiAgentBackend (Protocol)

`spawn(spec, initial_message, parent_session_id, mode="blocking" | "detached") -> SpawnHandle`

```python
spec = AgentSpec(
    name="sales-helper",
    instructions="You are a focused sales-research assistant.",
    allowed_tools=["search_company", "get_news"],
    max_iters=5,
)
handle = await ctx.multi_agent.spawn(spec, "Research Acme Corp.", parent_session_id, mode="blocking")
result = await ctx.multi_agent.join(handle.child_session_id)
```

Built-in: `InProcessMultiAgentBackend`. Contract test:
`MultiAgentBackendContract` (5 checks).

## CompactionStrategy (Protocol)

```python
class CompactionStrategy(Protocol):
    async def should_compact(self, session_id, current_tokens, window_limit) -> bool: ...
    async def compact(self, session_id) -> list[Message]: ...
```

Built-in: `SummarizationCompactor` (keeps recent N + summarizes the middle via
an injected `summarize_fn`).

## Contract tests

Each Protocol has a reusable `XContract` test class. Subclass it for your
custom impl:

```python
from tests.contracts.session_store import SessionStoreContract

class TestMyPostgresStore(SessionStoreContract):
    def make_store(self):
        return MyPostgresStore(dsn="...")
```

This gives you 10 conformance tests for free. Same pattern for
`PermissionResolverContract`, `TraceSinkContract`, `PromptBuilderContract`,
`CompactionStrategyContract`, `MultiAgentBackendContract`, `LLMProviderContract`.
