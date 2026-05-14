"""MemorySessionStore: contract conformance."""

from datetime import datetime, timezone

from meta_harney.abstractions._types import (
    Message,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
)
from meta_harney.abstractions.session import Session
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.session_store import SessionStoreContract


class TestMemorySessionStore(SessionStoreContract):
    def make_store(self) -> MemorySessionStore:
        return MemorySessionStore()


async def test_memory_session_store_roundtrips_thinking_blocks() -> None:
    """ThinkingBlock + RedactedThinkingBlock survive save/load cycle."""
    store = MemorySessionStore()
    session = Session(id="s1", created_at=datetime.now(timezone.utc))
    session.messages.append(
        Message(
            role="assistant",
            content=[
                ThinkingBlock(text="reasoning", signature="sig"),
                RedactedThinkingBlock(data="opaque"),
                TextBlock(text="answer"),
            ],
        )
    )
    await store.save(session)
    loaded = await store.load("s1")
    assert loaded is not None
    msg = loaded.messages[0]
    assert isinstance(msg.content[0], ThinkingBlock)
    assert msg.content[0].text == "reasoning"
    assert msg.content[0].signature == "sig"
    assert isinstance(msg.content[1], RedactedThinkingBlock)
    assert msg.content[1].data == "opaque"
    assert isinstance(msg.content[2], TextBlock)
