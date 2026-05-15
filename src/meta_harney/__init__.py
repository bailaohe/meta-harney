"""meta_harney — domain-agnostic agent runtime SDK.

Phase 10 status: Bridge (v0.1.0).
- meta_harney.bridge — JSON-RPC 2.0 server exposing AgentRuntime over stdio
  (BridgeServer, NewlineFraming/ContentLengthFraming, BridgePermissionResolver,
  BridgeTraceSink)
- Provider Catalog (Phase 9a): ProviderSpec + BUILT_IN_PROVIDERS for 9 known
  providers (anthropic, openai, moonshot, deepseek, gemini, minimax, nvidia,
  dashscope, modelscope)
- provider_from_spec() factory and register_provider() extension hook
- Anthropic extended-thinking full mode (Phase 7)
- ThinkingBlock + RedactedThinkingBlock content blocks
- OpenAIProvider (Phase 5) + AnthropicProvider (Phase 4)
- 9 core abstractions + builtin defaults
- GitHub Actions CI matrix (3.10/3.11/3.12 x ubuntu/macos)
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
    RedactedThinkingBlock,
    Session,
    SessionStore,
    SpawnHandle,
    TaskState,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolContext,
    ToolInvocation,
    ToolResult,
    ToolResultBlock,
    TraceEvent,
    TraceSink,
)
from meta_harney.bridge import (
    BridgePermissionResolver,
    BridgeServer,
    BridgeTraceSink,
    ContentLengthFraming,
    NewlineFraming,
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
    ProviderRedactedThinking,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingBlock,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
from meta_harney.providers.catalog import (
    BUILT_IN_PROVIDERS,
    ProviderSpec,
    provider_from_spec,
    register_provider,
)
from meta_harney.providers.openai import OpenAIProvider
from meta_harney.runtime import AgentRuntime
from meta_harney.testing import (
    FakeLLMProvider,
    FakeRound,
    runtime_for_testing,
)

__version__ = "0.2.4"

__all__ = [
    # provider catalog
    "BUILT_IN_PROVIDERS",
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
    # bridge (JSON-RPC over stdio)
    "BridgePermissionResolver",
    "BridgeServer",
    "BridgeTraceSink",
    # compaction
    "CompactionStrategy",
    # data contracts
    "ContentBlock",
    "ContentLengthFraming",
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
    "NewlineFraming",
    # openai provider
    "OpenAIProvider",
    # permission
    "PermissionDecision",
    "PermissionResolver",
    # prompt
    "PromptBuilder",
    # provider call config
    "ProviderCallConfig",
    "ProviderRedactedThinking",
    "ProviderSpec",
    "ProviderStreamDone",
    "ProviderStreamEvent",
    "ProviderTextDelta",
    "ProviderThinkingBlock",
    "ProviderThinkingDelta",
    "ProviderToolCall",
    # redacted thinking
    "RedactedThinkingBlock",
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
    "ThinkingBlock",
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
    "provider_from_spec",
    "register_provider",
    "run_turn",
    "runtime_for_testing",
    "tool_to_spec",
]
