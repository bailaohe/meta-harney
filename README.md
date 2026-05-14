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

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview
- [`docs/abstractions.md`](docs/abstractions.md) — the 9 abstractions reference
- [`docs/providers.md`](docs/providers.md) — provider setup + custom-provider guide
- [`docs/testing.md`](docs/testing.md) — testing helpers
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — original design specs

## Project status

| Phase | Status |
|---|---|
| 1: Foundation (9 abstractions + builtins) | shipped |
| 2: Engine + provider Protocol | shipped |
| 3: AgentRuntime + multi-agent | shipped |
| 4: Anthropic provider + testing module | shipped (v0.0.4) |
| 5: OpenAI provider + docs | shipped (v0.0.5) |

## License

Apache-2.0
