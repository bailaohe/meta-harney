# meta-harney

> A domain-agnostic agent runtime SDK. Clean abstractions for tools, hooks,
> permissions, prompts, sessions, tracing, and multi-agent coordination —
> with no assumptions about your business domain.

[![CI](https://github.com/bailaohe/meta-harney/actions/workflows/ci.yml/badge.svg)](https://github.com/bailaohe/meta-harney/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

## Why meta-harney?

Most agent frameworks bake in assumptions about *what* you're building — usually
coding assistants. meta-harney is the **runtime kernel**: agent loop, tool
dispatch, permission gating, hooks, multi-agent coordination, all behind clean
Protocol-based abstractions. **You** decide what your agent does.

Built for:

- **Business AI** — CRM agents, ops agents, support agents
- **Multi-tenant SaaS** — tenant-aware sessions, observability hooks
- **Reproducible testing** — `FakeLLMProvider` + contract test suite for
  every abstraction

## Quickstart

```bash
pip install meta-harney[anthropic]
```

```python
import asyncio

from meta_harney import AgentRuntime, AnthropicProvider, RuntimeConfig
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink


async def main() -> None:
    store = MemorySessionStore()
    rt = AgentRuntime(
        provider=AnthropicProvider(api_key="sk-ant-..."),
        prompt_builder=MinimalPromptBuilder(session_store=store),
        permission_resolver=AllowAllPermissionResolver(),
        session_store=store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model="claude-sonnet-4-5"),
    )
    session = await rt.create_session()
    response = await rt.invoke(session.id, "What's the capital of France?")
    print(response.content[0].text)


asyncio.run(main())
```

## Core Abstractions

9 Protocol/ABC interfaces define the runtime contract:

| Abstraction | What it does |
|---|---|
| `BaseTool` | Executable capability invoked by the LLM |
| `BaseHook` | Lifecycle event subscriber (7 event kinds) |
| `PermissionResolver` | Pre-execution allow / deny / ask check |
| `PromptBuilder` | System prompt + context assembly |
| `BaseTask` | Background-task primitive |
| `SessionStore` | Session persistence with optimistic locking |
| `TraceSink` | Observability event emission |
| `MultiAgentBackend` | Child-agent spawning (blocking + detached) |
| `CompactionStrategy` | Context-window management |

See [`docs/abstractions.md`](docs/abstractions.md) for full details.

## LLM Providers

| Provider | Install | Models |
|---|---|---|
| Anthropic | `pip install meta-harney[anthropic]` | Claude family |
| OpenAI | `pip install meta-harney[openai]` | GPT family |
| Custom | implement `LLMProvider` Protocol | any backend |

See [`docs/providers.md`](docs/providers.md) for setup and the custom-provider
guide.

## Testing your agent

```python
from meta_harney.testing import FakeRound, runtime_for_testing

rt = runtime_for_testing(
    scripted_rounds=[
        FakeRound(text="Hello!", stop_reason="end_turn"),
    ],
)
session = await rt.create_session()
result = await rt.invoke(session.id, "hi")
```

See [`docs/testing.md`](docs/testing.md) for the full testing API.

## Bridge — drive AgentRuntime from another process

`meta_harney.bridge` exposes the runtime as a JSON-RPC 2.0 server over stdio,
so a non-Python client (or any out-of-process orchestrator) can drive sessions,
stream events, gate permissions, and subscribe to telemetry.

```python
import asyncio
from meta_harney import AgentRuntime
from meta_harney.bridge import BridgeServer, NewlineFraming

runtime: AgentRuntime = build_your_runtime()  # tools, permissions, sessions wired by you
server = BridgeServer(
    runtime=runtime,
    framing=NewlineFraming(),
    server_info={"name": "my-bridge", "version": "0.1.0"},
)
asyncio.run(server.serve_stdio())
```

JSON-RPC 2.0 over stdio. Methods: `initialize`, `shutdown`, `exit`,
`session.create` / `session.list` / `session.load`, `session.send_message`
(with `stream/event` notifications), `session.cancel`, `$/cancelRequest`,
`tools.list`, `permission/request` (server to client), `telemetry/subscribe`,
`telemetry/event`. Two framings supported: `NewlineFraming` (newline-delimited
JSON, default) and `ContentLengthFraming` (LSP-style headers).

## TypeScript bridge client

Want to drive the bridge from Node.js? Ship a TypeScript client lives in
[`clients/typescript/`](clients/typescript/) (`@meta-harney/bridge-client`).
It wraps the JSON-RPC protocol with a typed `BridgeClient` (initialize,
session lifecycle, streaming `sendMessage`, permission handler,
`telemetry/subscribe`, cancellation handles), two framings, and a
`ChildProcessTransport` that spawns and supervises the bridge subprocess.

```ts
import { BridgeClient, ChildProcessTransport, NewlineFraming } from "@meta-harney/bridge-client";

const transport = new ChildProcessTransport({
  command: "oh",          // or any meta-harney BridgeServer entry point
  args: ["--bridge"],
  framing: new NewlineFraming(),
});
const client = new BridgeClient({ transport });
await client.initialize({ clientInfo: { name: "my-app", version: "1.0.0" } });

const session = await client.sessionCreate({ provider: "anthropic", model: "claude-sonnet-4-5" });
const handle = client.sendMessage(session.id, "What's the capital of France?");
for await (const ev of handle.events) {
  if (ev.kind === "text-delta") process.stdout.write(ev.text);
}
await client.shutdown();
```

Reference implementation: [`oh-tui`](https://github.com/bailaohe/oh-tui) — an
Ink TUI built on top of `@meta-harney/bridge-client`.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview
- [`docs/abstractions.md`](docs/abstractions.md) — the 9 abstractions reference
- [`docs/providers.md`](docs/providers.md) — provider setup + custom-provider guide
- [`docs/testing.md`](docs/testing.md) — testing helpers
- [`clients/typescript/`](clients/typescript/) — TS bridge client
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — original design specs

## Project status

| Phase | Status |
|---|---|
| 1: Foundation (9 abstractions + builtins) | shipped |
| 2: Engine + provider Protocol | shipped |
| 3: AgentRuntime + multi-agent | shipped |
| 4: Anthropic provider + testing module | shipped (v0.0.4) |
| 5: OpenAI provider + docs | shipped (v0.0.5) |
| 10: Bridge (JSON-RPC over stdio) | shipped (v0.1.0) |
| 11a: TypeScript bridge client | shipped (v0.2.0) |

## License

Apache-2.0
