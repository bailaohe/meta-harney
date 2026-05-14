"""meta_harney.testing — public testing helpers for SDK consumers.

Re-exports FakeLLMProvider + scripted FakeRound from providers/fake.py
under a clean test-oriented namespace.

`runtime_for_testing()` builds an AgentRuntime with sensible test defaults:
- AllowAllPermissionResolver
- MemorySessionStore
- NullSink (no trace I/O)
- MinimalPromptBuilder
- Scripted FakeLLMProvider (from caller-provided rounds)

Business apps test their custom tools/hooks/permission policies via this
factory without rebuilding the dependency graph each time.
"""
from __future__ import annotations

from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import MultiAgentBackend
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import SessionStore
from meta_harney.abstractions.tool import BaseTool
from meta_harney.abstractions.trace import TraceSink
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.providers.fake import FakeLLMProvider, FakeRound, RecordedCall
from meta_harney.runtime import AgentRuntime


def runtime_for_testing(
    *,
    scripted_rounds: list[FakeRound],
    tools: dict[str, BaseTool] | None = None,
    hooks: list[BaseHook] | None = None,
    permission_resolver: PermissionResolver | None = None,
    prompt_builder: PromptBuilder | None = None,
    session_store: SessionStore | None = None,
    trace_sink: TraceSink | None = None,
    compaction: CompactionStrategy | None = None,
    multi_agent: MultiAgentBackend | None = None,
    model: str = "test-model",
) -> AgentRuntime:
    """Build an AgentRuntime with sensible test defaults.

    Only `scripted_rounds` is required. Any other dependency is constructed
    if not provided. The returned runtime is fully wired and ready for
    `create_session()` + `invoke()`.
    """
    store = session_store if session_store is not None else MemorySessionStore()
    return AgentRuntime(
        provider=FakeLLMProvider(rounds=scripted_rounds),
        prompt_builder=(
            prompt_builder
            if prompt_builder is not None
            else MinimalPromptBuilder(session_store=store)
        ),
        permission_resolver=(
            permission_resolver
            if permission_resolver is not None
            else AllowAllPermissionResolver()
        ),
        session_store=store,
        trace_sink=trace_sink if trace_sink is not None else NullSink(),
        config=RuntimeConfig(model=model),
        tools=tools or {},
        hooks=hooks or [],
        compaction=compaction,
        multi_agent=multi_agent,
    )


__all__ = [
    "FakeLLMProvider",
    "FakeRound",
    "RecordedCall",
    "runtime_for_testing",
]
