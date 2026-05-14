"""Tests for PromptBuilder Protocol."""

from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.prompt import PromptBuilder


async def test_protocol_satisfied_by_duck_typing():
    class Fake:
        async def build_system_prompt(self, session_id: str) -> str:
            return f"hi from {session_id}"

        async def build_context_messages(self, session_id: str) -> list[Message]:
            return [Message(role="user", content=[TextBlock(text="prior")])]

    builder: PromptBuilder = Fake()
    sp = await builder.build_system_prompt("s1")
    assert sp == "hi from s1"

    msgs = await builder.build_context_messages("s1")
    assert len(msgs) == 1
    first_block = msgs[0].content[0]
    assert isinstance(first_block, TextBlock)
    assert first_block.text == "prior"
