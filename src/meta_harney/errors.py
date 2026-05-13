"""meta_harney exception hierarchy.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §7.1.
"""

from __future__ import annotations


class MetaHarneyError(Exception):
    """Root of all meta_harney exceptions."""


# ---- Configuration ----


class ConfigurationError(MetaHarneyError):
    """Raised at runtime construction time (fail-fast)."""


# ---- LLM Provider ----


class ProviderError(MetaHarneyError):
    """Base for all LLM provider issues."""


class RetryableProviderError(ProviderError):
    """429, 5xx, network blips — engine will retry."""


class NonRetryableProviderError(ProviderError):
    """Auth failures, invalid request, etc. — propagate immediately."""


# ---- Tool ----


class ToolError(MetaHarneyError):
    """Base for tool-execution failures (converted to ToolResult)."""


class ToolNotFoundError(ToolError):
    """Tool name not registered."""


class ToolInvalidArgsError(ToolError):
    """Tool arg schema validation failed."""


class ToolExecutionError(ToolError):
    """Tool raised during execute()."""


class ToolTimeoutError(ToolError):
    """Tool exceeded its configured timeout."""

    def __init__(self, tool_name: str, timeout_s: float):
        super().__init__(f"Tool {tool_name!r} timed out after {timeout_s}s")
        self.tool_name = tool_name
        self.timeout_s = timeout_s


# ---- Permission ----


class PermissionDeniedError(MetaHarneyError):
    """Permission resolver returned 'deny'. Converted to ToolResult by engine."""


# ---- Hook ----


class HookError(MetaHarneyError):
    """Base for hook subsystem errors."""


class HookHaltError(HookError):
    """Business hook explicitly halts the agent loop. Propagates to invoke caller."""

    def __init__(self, reason: str):
        super().__init__(f"Hook halt: {reason}")
        self.reason = reason


class HookExecutionError(HookError):
    """Hook raised unexpectedly. Engine logs and continues (fail-open)."""


# ---- Session ----


class SessionError(MetaHarneyError):
    """Base for session/store errors."""


class SessionNotFoundError(SessionError):
    """Session id does not exist in the store."""


class SessionConflictError(SessionError):
    """Optimistic-lock conflict on save."""

    def __init__(self, session_id: str, expected_version: int, found_version: int):
        super().__init__(
            f"Session {session_id!r} version mismatch: expected {expected_version}, "
            f"found {found_version}"
        )
        self.session_id = session_id
        self.expected_version = expected_version
        self.found_version = found_version


class SessionStoreError(SessionError):
    """Underlying store I/O failure."""


# ---- Compaction ----


class CompactionError(MetaHarneyError):
    """Compactor raised. Engine logs and skips this compaction (fail-open)."""


# ---- MultiAgent ----


class MultiAgentError(MetaHarneyError):
    """Base for multi-agent backend errors."""


class SpawnError(MultiAgentError):
    """Failed to spawn a child agent."""


class ChildTimeoutError(MultiAgentError):
    """Child agent did not return within the join timeout."""
