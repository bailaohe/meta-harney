"""MemorySessionStore: contract conformance."""

from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.session_store import SessionStoreContract


class TestMemorySessionStore(SessionStoreContract):
    def make_store(self) -> MemorySessionStore:
        return MemorySessionStore()
