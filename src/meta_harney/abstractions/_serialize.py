"""Tool output serialization helper.

Used by provider implementations to convert ToolResult.output (Any) into a
single string suitable for the LLM's tool_result content. Encapsulates:

- None → "" (omitted content)
- str → unchanged (preserves prose tool outputs as-is)
- structured (dict / list / number / bool) → json.dumps with default=str fallback
- circular references / unserializable → repr(...) — never raises

This is shared between AnthropicProvider and OpenAIProvider to enforce the
invariant that tool result content is always a string.
"""

from __future__ import annotations

import json
from typing import Any


def _serialize_tool_output(output: Any) -> str:
    """Convert arbitrary tool output into a string for LLM consumption."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, default=str, ensure_ascii=False)
    except (ValueError, TypeError):
        return repr(output)
