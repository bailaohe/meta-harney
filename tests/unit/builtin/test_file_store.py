"""FileSessionStore: contract conformance + file-specific behavior."""

from pathlib import Path

import pytest

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
