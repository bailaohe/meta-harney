"""SummarizationCompactor — preserves system + recent N, summarizes the middle.

Decoupled from the provider layer: caller injects a `summarize_fn` that
turns a list of messages into a summary string. In Phase 2, the runtime
will wire this fn to call the configured LLM provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import SessionStore

SummarizeFn = Callable[[list[Message]], Awaitable[str]]


class SummarizationCompactor:
    """Compacts the middle of session.messages into a single summary message.

    Algorithm:
      1. Compute (system_msgs, middle_msgs, recent_msgs) where recent_msgs
         is the last `keep_recent` messages and system_msgs are all role==system
         messages before middle.
      2. If middle_msgs is empty, return messages unchanged.
      3. Call summarize_fn(middle_msgs) -> str.
      4. Return system_msgs + [summary_msg] + recent_msgs.
    """

    def __init__(
        self,
        session_store: SessionStore,
        summarize_fn: SummarizeFn,
        keep_recent: int = 10,
        trigger_ratio: float = 0.8,
    ) -> None:
        self._session_store = session_store
        self._summarize_fn = summarize_fn
        self._keep_recent = keep_recent
        self._trigger_ratio = trigger_ratio

    async def should_compact(
        self,
        session_id: str,
        current_tokens: int,
        window_limit: int,
    ) -> bool:
        return current_tokens > window_limit * self._trigger_ratio

    async def compact(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None or not s.messages:
            return []
        msgs = list(s.messages)

        # Partition: leading system, middle, recent
        system_msgs: list[Message] = []
        i = 0
        while i < len(msgs) and msgs[i].role == "system":
            system_msgs.append(msgs[i])
            i += 1
        rest = msgs[i:]

        if len(rest) <= self._keep_recent:
            return msgs  # nothing to summarize

        recent = rest[-self._keep_recent :]
        middle = rest[: -self._keep_recent]

        summary_text = await self._summarize_fn(middle)
        summary_msg = Message(
            role="system",
            content=[TextBlock(text=summary_text)],
        )
        return [*system_msgs, summary_msg, *recent]
