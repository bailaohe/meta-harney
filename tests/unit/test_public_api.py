"""Verify the public API surface from `meta_harney` package root."""


def test_public_api_exports():
    import meta_harney as mh

    # Data contracts
    assert mh.Message
    assert mh.TextBlock
    assert mh.ImageBlock
    assert mh.ToolCallBlock
    assert mh.ToolResultBlock

    # Tool abstraction
    assert mh.BaseTool
    assert mh.ToolInvocation
    assert mh.ToolResult
    assert mh.ToolContext

    # Hook
    assert mh.BaseHook
    assert mh.HookEvent
    assert mh.HookDecision

    # Permission
    assert mh.PermissionResolver
    assert mh.PermissionDecision

    # Prompt
    assert mh.PromptBuilder

    # Task
    assert mh.BaseTask
    assert mh.TaskState

    # Session
    assert mh.Session
    assert mh.SessionStore

    # Trace
    assert mh.TraceEvent
    assert mh.TraceSink

    # MultiAgent
    assert mh.MultiAgentBackend
    assert mh.AgentSpec
    assert mh.SpawnHandle

    # Compaction
    assert mh.CompactionStrategy

    # Errors (root only at top level; full hierarchy under meta_harney.errors)
    assert mh.MetaHarneyError


def test_builtin_namespace():
    from meta_harney.builtin.compaction.summarization import SummarizationCompactor
    from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
    from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
    from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
    from meta_harney.builtin.session.file_store import FileSessionStore
    from meta_harney.builtin.session.memory_store import MemorySessionStore
    from meta_harney.builtin.trace.jsonl_sink import JsonlSink
    from meta_harney.builtin.trace.null_sink import NullSink

    # smoke
    assert AllowAllPermissionResolver
    assert DenyAllPermissionResolver
    assert MemorySessionStore
    assert FileSessionStore
    assert NullSink
    assert JsonlSink
    assert MinimalPromptBuilder
    assert SummarizationCompactor
