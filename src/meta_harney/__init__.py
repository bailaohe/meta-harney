"""meta_harney — domain-agnostic agent runtime SDK.

Phase 7 status: extended-thinking full mode + GitHub Actions CI.
- ThinkingBlock + RedactedThinkingBlock content blocks (persisted, round-tripped)
- ProviderThinkingBlock + ProviderRedactedThinking stream events
- AnthropicProvider buffers thinking_delta + signature_delta, emits at content_block_stop
- Engine appends thinking blocks to assistant Message.content (entering session.messages)
- OpenAIProvider silently skips thinking blocks (no concept)
- GitHub repo + Actions CI matrix (Python 3.10/3.11/3.12 x ubuntu/macos)
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
from meta_harney.providers.openai import OpenAIProvider
from meta_harney.runtime import AgentRuntime
from meta_harney.testing import (
    FakeLLMProvider,
    FakeRound,
    runtime_for_testing,
)

__version__ = "0.0.7"

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
    "ProviderRedactedThinking",
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
    "run_turn",
    "runtime_for_testing",
    "tool_to_spec",
]
