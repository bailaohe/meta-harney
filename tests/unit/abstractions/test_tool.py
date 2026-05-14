"""Tests for BaseTool, ToolInvocation, ToolResult, ToolContext."""

from __future__ import annotations

import uuid

import pytest
from pydantic import BaseModel, ValidationError

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)


def test_tool_invocation_fields():
    inv = ToolInvocation(
        name="my_tool",
        args={"x": 1},
        invocation_id="inv-1",
        session_id="s-1",
    )
    assert inv.name == "my_tool"
    assert inv.session_id == "s-1"


def test_tool_invocation_session_id_required():
    with pytest.raises(ValidationError):
        ToolInvocation(name="t", args={}, invocation_id="i")  # type: ignore


def test_tool_result_success():
    r = ToolResult(success=True, output={"ok": True})
    assert r.success
    assert r.error is None
    assert r.metadata == {}


def test_tool_result_failure():
    r = ToolResult(success=False, output=None, error="bad input")
    assert not r.success
    assert r.error == "bad input"


def test_tool_context_dataclass_fields():
    """ToolContext is a dataclass exposing runtime services to tools."""
    ctx = ToolContext(
        session_store=object(),  # type: ignore  # placeholder for protocol
        trace_sink=object(),  # type: ignore
        current_span_id="span-1",
        new_span_id=lambda: uuid.uuid4().hex[:16],
    )
    assert ctx.current_span_id == "span-1"
    assert isinstance(ctx.new_span_id(), str)


def test_base_tool_is_abstract():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore[abstract]


def test_concrete_tool_can_subclass():
    class EchoInput(BaseModel):
        text: str

    class EchoTool(BaseTool):
        name = "echo"
        description = "Echoes input."
        input_schema = EchoInput
        default_timeout = 5.0

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output=inv.args)

    assert EchoTool.name == "echo"
    assert EchoTool.default_timeout == 5.0
    assert issubclass(EchoTool, BaseTool)


def test_concrete_tool_without_required_classvars_fails():
    class Broken(BaseTool):
        async def execute(self, inv, ctx):
            return ToolResult(success=True, output=None)

    # missing required ClassVars: name, description, input_schema
    # Note: Python doesn't enforce ClassVar presence at class-creation;
    # we instead rely on type-checker. We test that the class instantiates
    # but accessing the unset ClassVar raises AttributeError.
    t = Broken()
    with pytest.raises(AttributeError):
        _ = t.name


def test_tool_context_multi_agent_field_defaults_to_none() -> None:
    """ToolContext gains optional multi_agent field for child-agent spawning."""
    import uuid as _uuid

    ctx = ToolContext(
        session_store=object(),  # type: ignore[arg-type]
        trace_sink=object(),  # type: ignore[arg-type]
        current_span_id="x",
        new_span_id=lambda: _uuid.uuid4().hex[:16],
    )
    # New field exists with default None
    assert ctx.multi_agent is None


def test_tool_context_multi_agent_field_accepts_backend() -> None:
    """When provided, multi_agent is exposed verbatim to tools."""
    import uuid as _uuid

    class FakeBackend:
        async def spawn(self, spec, initial_message, parent_session_id, mode="blocking"):
            raise NotImplementedError

        async def join(self, child_session_id, timeout=None):
            raise NotImplementedError

        async def status(self, child_session_id):
            raise NotImplementedError

        async def cancel(self, child_session_id):
            raise NotImplementedError

    backend = FakeBackend()
    ctx = ToolContext(
        session_store=object(),  # type: ignore[arg-type]
        trace_sink=object(),  # type: ignore[arg-type]
        current_span_id="x",
        new_span_id=lambda: _uuid.uuid4().hex[:16],
        multi_agent=backend,  # type: ignore[arg-type]
    )
    assert ctx.multi_agent is backend
