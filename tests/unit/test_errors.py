"""Tests for the meta_harney exception hierarchy."""

import pytest

from meta_harney.errors import (
    ChildTimeoutError,
    CompactionError,
    ConfigurationError,
    HookError,
    HookExecutionError,
    HookHaltError,
    MetaHarneyError,
    MultiAgentError,
    NonRetryableProviderError,
    PermissionDeniedError,
    ProviderError,
    RetryableProviderError,
    SessionConflictError,
    SessionError,
    SessionNotFoundError,
    SessionStoreError,
    SpawnError,
    ToolError,
    ToolExecutionError,
    ToolInvalidArgsError,
    ToolNotFoundError,
    ToolTimeoutError,
)


def test_root_is_exception():
    assert issubclass(MetaHarneyError, Exception)


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigurationError,
        ProviderError,
        ToolError,
        PermissionDeniedError,
        HookError,
        SessionError,
        CompactionError,
        MultiAgentError,
    ],
)
def test_top_level_subclasses_root(exc_cls):
    assert issubclass(exc_cls, MetaHarneyError)


@pytest.mark.parametrize(
    "child,parent",
    [
        (RetryableProviderError, ProviderError),
        (NonRetryableProviderError, ProviderError),
        (ToolNotFoundError, ToolError),
        (ToolInvalidArgsError, ToolError),
        (ToolExecutionError, ToolError),
        (ToolTimeoutError, ToolError),
        (HookHaltError, HookError),
        (HookExecutionError, HookError),
        (SessionNotFoundError, SessionError),
        (SessionConflictError, SessionError),
        (SessionStoreError, SessionError),
        (SpawnError, MultiAgentError),
        (ChildTimeoutError, MultiAgentError),
    ],
)
def test_nested_hierarchy(child, parent):
    assert issubclass(child, parent)


def test_hook_halt_carries_reason():
    err = HookHaltError(reason="user requested stop")
    assert err.reason == "user requested stop"
    assert "user requested stop" in str(err)


def test_session_conflict_carries_versions():
    err = SessionConflictError(session_id="s1", expected_version=3, found_version=5)
    assert err.session_id == "s1"
    assert err.expected_version == 3
    assert err.found_version == 5


def test_tool_timeout_carries_timeout_value():
    err = ToolTimeoutError(tool_name="my_tool", timeout_s=10.0)
    assert err.tool_name == "my_tool"
    assert err.timeout_s == 10.0
