"""Compaction abstraction: CompactionStrategy Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.10.
"""

from __future__ import annotations

from typing import Protocol

from meta_harney.abstractions._types import Message


class CompactionStrategy(Protocol):
    """Decides when to compact a session's messages and how.

    The engine asks `should_compact()` once per loop iteration when
    `current_tokens > window_limit * 0.8` (default heuristic, configurable).
    If True, the engine calls `compact()` and replaces session.messages
    with the returned list.
    """

    async def should_compact(
        self,
        session_id: str,
        current_tokens: int,
        window_limit: int,
    ) -> bool: ...

    async def compact(self, session_id: str) -> list[Message]:
        """Return the new compacted message list."""
