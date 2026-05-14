"""Verify the public API surface from `meta_harney` package root."""


def test_public_api_exports() -> None:
    import meta_harney as mh

    # Data contracts
    assert mh.Message is not None
    assert mh.TextBlock is not None
    assert mh.ImageBlock is not None
    assert mh.ToolCallBlock is not None
    assert mh.ToolResultBlock is not None

    # Tool abstraction
    assert mh.BaseTool is not None
    assert mh.ToolInvocation is not None
    assert mh.ToolResult is not None
    assert mh.ToolContext is not None

    # Hook
    assert mh.BaseHook is not None
    assert mh.HookEvent is not None
    assert mh.HookDecision is not None

    # Permission
    assert mh.PermissionResolver is not None
    assert mh.PermissionDecision is not None

    # Prompt
    assert mh.PromptBuilder is not None

    # Task
    assert mh.BaseTask is not None
    assert mh.TaskState is not None

    # Session
    assert mh.Session is not None
    assert mh.SessionStore is not None

    # Trace
    assert mh.TraceEvent is not None
    assert mh.TraceSink is not None

    # MultiAgent
    assert mh.MultiAgentBackend is not None
    assert mh.AgentSpec is not None
    assert mh.SpawnHandle is not None

    # Compaction
    assert mh.CompactionStrategy is not None

    # Errors (root only at top level; full hierarchy under meta_harney.errors)
    assert mh.MetaHarneyError is not None

    # Phase 3: runtime facade + builtin backend
    assert mh.AgentRuntime is not None
    assert mh.InProcessMultiAgentBackend is not None


def test_builtin_namespace() -> None:
    from meta_harney.builtin.compaction.summarization import SummarizationCompactor
    from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
    from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
    from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
    from meta_harney.builtin.session.file_store import FileSessionStore
    from meta_harney.builtin.session.memory_store import MemorySessionStore
    from meta_harney.builtin.trace.jsonl_sink import JsonlSink
    from meta_harney.builtin.trace.null_sink import NullSink

    # smoke: names must exist and not be None
    assert AllowAllPermissionResolver is not None
    assert DenyAllPermissionResolver is not None
    assert MemorySessionStore is not None
    assert FileSessionStore is not None
    assert NullSink is not None
    assert JsonlSink is not None
    assert MinimalPromptBuilder is not None
    assert SummarizationCompactor is not None
