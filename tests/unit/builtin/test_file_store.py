"""FileSessionStore: contract conformance + file-specific behavior."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta_harney.abstractions._types import (
    Message,
    RedactedThinkingBlock,
    ThinkingBlock,
)
from meta_harney.abstractions.session import Session
from meta_harney.builtin.session.file_store import FileSessionStore
from meta_harney.errors import SessionStoreError
from tests.contracts.session_store import SessionStoreContract


class TestFileSessionStore(SessionStoreContract):
    @pytest.fixture(autouse=True)
    def _tmp_path(self, tmp_path: Path) -> None:
        self._root = tmp_path

    def make_store(self) -> FileSessionStore:
        return FileSessionStore(self._root)


async def test_file_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path)
    with pytest.raises(SessionStoreError):
        await store.load("../etc/passwd")


async def test_file_session_store_roundtrips_thinking_blocks(tmp_path: Path) -> None:
    """ThinkingBlock + RedactedThinkingBlock survive JSON-file save/load."""
    store = FileSessionStore(tmp_path)
    session = Session(id="s1", created_at=datetime.now(timezone.utc))
    session.messages.append(
        Message(
            role="assistant",
            content=[
                ThinkingBlock(text="reasoning", signature="sig"),
                RedactedThinkingBlock(data="opaque"),
            ],
        )
    )
    await store.save(session)
    loaded = await store.load("s1")
    assert loaded is not None
    assert isinstance(loaded.messages[0].content[0], ThinkingBlock)
    assert loaded.messages[0].content[0].signature == "sig"
    assert isinstance(loaded.messages[0].content[1], RedactedThinkingBlock)
    assert loaded.messages[0].content[1].data == "opaque"
