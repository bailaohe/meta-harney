"""meta_harney — domain-agnostic agent runtime SDK.

Phase 2 status: engine + provider layer added. Runtime config, streaming
event types, retry policy, and LLMProvider Protocol are now part of the
public surface. Abstractions and builtin defaults from Phase 1 are retained.
Multi-agent backends land in subsequent phases.
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
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ToolSpec,
)

__version__ = "0.0.1"

__all__ = [
    # multi-agent
    "AgentSpec",
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
    "HookDecision",
    "HookEvent",
    "HookEventKind",
    "ImageBlock",
    # engine stream events
    "IterationCompleted",
    # provider protocol
    "LLMProvider",
    "Message",
    # errors
    "MetaHarneyError",
    "MultiAgentBackend",
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
    "tool_to_spec",
]
