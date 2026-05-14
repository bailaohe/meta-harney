"""meta_harney — domain-agnostic agent runtime SDK.

Phase 5 status: OpenAIProvider (second real LLM backend) added alongside
AnthropicProvider. User-facing documentation shipped: README, architecture,
abstractions, providers, and testing reference docs.

Public surface:
- AgentRuntime facade (create_session, invoke, stream)
- LLMProvider Protocol + ProviderStreamEvent variants
- FakeLLMProvider + runtime_for_testing for SDK consumers' tests
- AnthropicProvider (optional 'anthropic' extra)
- OpenAIProvider (optional 'openai' extra)
- InProcessMultiAgentBackend
- 9 core abstractions + builtin defaults (Phase 1)
- StreamEvent types, RetryConfig, RuntimeConfig (Phase 2-3)
"""

from meta_harney.abstractions import (
    AgentSpec,
    BaseHook,
    BaseTask,
    BaseTool,
    CompactionStrategy,
    ContentBlock,
    HookDecision,
    HookEvent,
    HookEventKind,
    ImageBlock,
    Message,
    MultiAgentBackend,
    PermissionDecision,
    PermissionResolver,
    PromptBuilder,
    Session,
    SessionStore,
    SpawnHandle,
    TaskState,
    TextBlock,
    ToolCallBlock,
    ToolContext,
    ToolInvocation,
    ToolResult,
    ToolResultBlock,
    TraceEvent,
    TraceSink,
)
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
from meta_harney.engine.loop import run_turn
from meta_harney.engine.retry import RetryConfig
from meta_harney.engine.stream_events import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.errors import MetaHarneyError
from meta_harney.providers.anthropic import AnthropicProvider
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)
from meta_harney.providers.openai import OpenAIProvider
from meta_harney.runtime import AgentRuntime
from meta_harney.testing import (
    FakeLLMProvider,
    FakeRound,
    runtime_for_testing,
)

__version__ = "0.0.5"

__all__ = [
    # runtime facade
    "AgentRuntime",
    # multi-agent
    "AgentSpec",
    # providers
    "AnthropicProvider",
    # hook
    "BaseHook",
    # task
    "BaseTask",
    # tool
    "BaseTool",
    # compaction
    "CompactionStrategy",
    # data contracts
    "ContentBlock",
    # testing
    "FakeLLMProvider",
    "FakeRound",
    "HookDecision",
    "HookEvent",
    "HookEventKind",
    "ImageBlock",
    # builtin backends
    "InProcessMultiAgentBackend",
    # engine stream events
    "IterationCompleted",
    # provider protocol
    "LLMProvider",
    "Message",
    # errors
    "MetaHarneyError",
    "MultiAgentBackend",
    # openai provider
    "OpenAIProvider",
    # permission
    "PermissionDecision",
    "PermissionResolver",
    # prompt
    "PromptBuilder",
    # provider call config
    "ProviderCallConfig",
    "ProviderStreamDone",
    "ProviderStreamEvent",
    "ProviderTextDelta",
    "ProviderToolCall",
    # retry
    "RetryConfig",
    # engine config
    "RuntimeConfig",
    # session
    "Session",
    "SessionStore",
    "SpawnHandle",
    "StreamEvent",
    "TaskState",
    "TextBlock",
    "TextDelta",
    "ThinkingDelta",
    "ToolCallBlock",
    "ToolCallCompleted",
    "ToolCallStarted",
    "ToolContext",
    "ToolInvocation",
    "ToolResult",
    "ToolResultBlock",
    # provider tool spec
    "ToolSpec",
    # trace
    "TraceEvent",
    "TraceSink",
    "TurnCompleted",
    "__version__",
    # engine entry point
    "run_turn",
    "runtime_for_testing",
    "tool_to_spec",
]
