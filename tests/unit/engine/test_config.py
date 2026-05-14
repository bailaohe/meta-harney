"""Tests for RuntimeConfig + ToolSpec helpers."""

from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions.tool import BaseTool, ToolContext, ToolInvocation, ToolResult
from meta_harney.engine.config import RuntimeConfig, tool_to_spec
from meta_harney.engine.retry import RetryConfig


class _EchoInput(BaseModel):
    text: str


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes input."
    input_schema = _EchoInput
    default_timeout = 5.0

    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return ToolResult(success=True, output=inv.args)


def test_runtime_config_defaults() -> None:
    c = RuntimeConfig(model="gpt-test")
    assert c.model == "gpt-test"
    assert c.tool_timeout_overrides == {}
    assert c.global_default_timeout == 300.0
    assert c.max_iterations == 10
    assert c.compaction_trigger_tokens is None
    assert c.context_window_tokens == 100_000


def test_tool_timeout_resolution_uses_override() -> None:
    c = RuntimeConfig(
        model="x",
        tool_timeout_overrides={"echo": 1.5},
    )
    assert c.resolve_tool_timeout(_EchoTool()) == 1.5


def test_tool_timeout_resolution_uses_tool_default() -> None:
    c = RuntimeConfig(model="x")
    assert c.resolve_tool_timeout(_EchoTool()) == 5.0


def test_tool_timeout_resolution_falls_back_to_global() -> None:
    class _NoTimeoutTool(BaseTool):
        name = "nt"
        description = "no timeout"
        input_schema = _EchoInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output=None)

    c = RuntimeConfig(model="x", global_default_timeout=42.0)
    assert c.resolve_tool_timeout(_NoTimeoutTool()) == 42.0


def test_tool_timeout_resolution_none_when_all_unset() -> None:
    class _NoTimeoutTool(BaseTool):
        name = "nt"
        description = "no timeout"
        input_schema = _EchoInput

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output=None)

    c = RuntimeConfig(model="x", global_default_timeout=None)
    assert c.resolve_tool_timeout(_NoTimeoutTool()) is None


def test_tool_to_spec_basic() -> None:
    spec = tool_to_spec(_EchoTool())
    assert spec.name == "echo"
    assert spec.description == "Echoes input."
    assert "properties" in spec.input_schema
    assert "text" in spec.input_schema["properties"]


def test_runtime_config_new_fields_defaults() -> None:
    c = RuntimeConfig(model="x")
    assert c.max_tokens is None
    assert c.temperature is None
    assert c.retry == RetryConfig()  # default retry config


def test_runtime_config_custom_provider_params() -> None:
    c = RuntimeConfig(
        model="x",
        max_tokens=4096,
        temperature=0.7,
    )
    assert c.max_tokens == 4096
    assert c.temperature == 0.7


def test_runtime_config_custom_retry() -> None:
    c = RuntimeConfig(
        model="x",
        retry=RetryConfig(max_attempts=5, initial_delay_s=0.5),
    )
    assert c.retry.max_attempts == 5
    assert c.retry.initial_delay_s == 0.5


def test_runtime_config_to_provider_call_config() -> None:
    """Helper produces a ProviderCallConfig with all relevant fields."""
    from meta_harney.providers.base import ProviderCallConfig

    c = RuntimeConfig(model="x", max_tokens=1024, temperature=0.5)
    pc = c.to_provider_call_config()
    assert isinstance(pc, ProviderCallConfig)
    assert pc.model == "x"
    assert pc.max_tokens == 1024
    assert pc.temperature == 0.5
