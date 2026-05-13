"""Engine runtime configuration: timeouts, retry, compaction trigger.

`tool_to_spec` converts a BaseTool subclass into a ToolSpec for the LLM
provider — derived from the tool's name, description, and Pydantic
input_schema.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import BaseTool
from meta_harney.providers.base import ToolSpec


class RuntimeConfig(BaseModel):
    """Engine runtime parameters (one-shot or per-runtime)."""

    model: str

    # Per-tool timeout resolution: overrides → tool.default_timeout → global → None
    tool_timeout_overrides: dict[str, float] = Field(default_factory=dict)
    global_default_timeout: float | None = 300.0

    # Loop bounds
    max_iterations: int = 10

    # Compaction
    context_window_tokens: int = 100_000
    compaction_trigger_tokens: int | None = None  # None ⇒ no compaction

    def resolve_tool_timeout(self, tool: BaseTool) -> float | None:
        """Resolution order per spec §7.5."""
        if tool.name in self.tool_timeout_overrides:
            return self.tool_timeout_overrides[tool.name]
        if tool.default_timeout is not None:
            return tool.default_timeout
        return self.global_default_timeout


def tool_to_spec(tool: BaseTool) -> ToolSpec:
    """Convert a BaseTool into a ToolSpec for LLM provider exposure."""
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema.model_json_schema(),
    )
