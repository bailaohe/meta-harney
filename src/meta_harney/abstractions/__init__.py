"""meta_harney abstractions: the 9 core protocol/ABC interfaces.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.
"""

from meta_harney.abstractions._types import (
    ContentBlock,
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import (
    BaseHook,
    HookDecision,
    HookEvent,
    HookEventKind,
)
from meta_harney.abstractions.multi_agent import (
    AgentSpec,
    MultiAgentBackend,
    SpawnHandle,
)
from meta_harney.abstractions.permission import (
    PermissionDecision,
    PermissionResolver,
)
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.task import BaseTask, TaskState
from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)
from meta_harney.abstractions.trace import TraceEvent, TraceSink

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
    # types
    "ContentBlock",
    "HookDecision",
    "HookEvent",
    "HookEventKind",
    "ImageBlock",
    "Message",
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
]
