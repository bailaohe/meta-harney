"""meta_harney — domain-agnostic agent runtime SDK.

Phase 1 status: abstractions and builtin defaults only. Engine, providers,
runtime, and multi-agent backends land in subsequent phases.
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
from meta_harney.errors import MetaHarneyError

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
    "Message",
    # errors
    "MetaHarneyError",
    "MultiAgentBackend",
    # permission
    "PermissionDecision",
    "PermissionResolver",
    # prompt
    "PromptBuilder",
    # session
    "Session",
    "SessionStore",
    "SpawnHandle",
    "TaskState",
    "TextBlock",
    "ToolCallBlock",
    "ToolContext",
    "ToolInvocation",
    "ToolResult",
    "ToolResultBlock",
    # trace
    "TraceEvent",
    "TraceSink",
    "__version__",
]
