"""Reusable contract test suite for SessionStore implementations.

Any concrete SessionStore (builtin or business-supplied) should subclass
this and provide `make_store()`. The subclass automatically inherits all
contract checks.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.errors import SessionConflictError


def _make_session(
    *,
    id: str = "s1",
    tenant_id: str | None = None,
    user_id: str | None = None,
    version: int = 0,
) -> Session:
    return Session(
        id=id,
        tenant_id=tenant_id,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        version=version,
    )


class SessionStoreContract:
    """Contract tests every SessionStore implementation must pass.

    Subclass and implement `make_store()`. Concrete subclasses must be
    valid pytest test classes (start with `Test...`).
    """

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    async def test_load_returns_none_for_missing(self) -> None:
        store = self.make_store()
        assert await store.load("does-not-exist") is None

    async def test_save_then_load_roundtrip(self) -> None:
        store = self.make_store()
        s = _make_session(id="s1", tenant_id="acme")
        s.attributes["customer_id"] = "C-1"
        await store.save(s)
        loaded = await store.load("s1")
        assert loaded is not None
        assert loaded.id == "s1"
        assert loaded.tenant_id == "acme"
        assert loaded.attributes["customer_id"] == "C-1"

    async def test_save_increments_version(self) -> None:
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)
        # The stored copy has version 1
        loaded = await store.load(s.id)
        assert loaded is not None
        assert loaded.version == 1

    async def test_save_with_stale_version_raises_conflict(self) -> None:
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)  # stored as version 1
        stale = _make_session(version=0)  # caller still thinks v0
        with pytest.raises(SessionConflictError):
            await store.save(stale)

    async def test_save_then_save_with_fresh_version_succeeds(self) -> None:
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)  # version 1
        s2 = _make_session(version=1)  # caller knows current is v1
        s2.messages.append(Message(role="user", content=[TextBlock(text="hi")]))
        await store.save(s2)  # version 2
        loaded = await store.load("s1")
        assert loaded is not None
        assert loaded.version == 2
        assert len(loaded.messages) == 1

    async def test_tenant_filter_load_isolation(self) -> None:
        store = self.make_store()
        s = _make_session(id="s1", tenant_id="acme")
        await store.save(s)
        assert (await store.load("s1", tenant_id="acme")) is not None
        assert (await store.load("s1", tenant_id="other")) is None

    async def test_tenant_filter_list(self) -> None:
        store = self.make_store()
        await store.save(_make_session(id="a", tenant_id="acme"))
        await store.save(_make_session(id="b", tenant_id="other"))
        await store.save(_make_session(id="c", tenant_id="acme"))
        acme = await store.list(tenant_id="acme")
        ids = sorted(s.id for s in acme)
        assert ids == ["a", "c"]

    async def test_list_no_filter_returns_all(self) -> None:
        store = self.make_store()
        await store.save(_make_session(id="a"))
        await store.save(_make_session(id="b"))
        all_ = await store.list()
        assert len(all_) == 2

    async def test_delete_then_load_returns_none(self) -> None:
        store = self.make_store()
        await store.save(_make_session(id="s1"))
        await store.delete("s1")
        assert await store.load("s1") is None

    async def test_delete_missing_is_idempotent(self) -> None:
        store = self.make_store()
        await store.delete("never-existed")  # must not raise

    async def test_load_returns_independent_copy(self) -> None:
        """Mutating returned Session must not corrupt the stored copy."""
        store = self.make_store()
        s = _make_session(id="s1")
        await store.save(s)
        loaded = await store.load("s1")
        assert loaded is not None
        loaded.attributes["leak"] = "bad"
        loaded2 = await store.load("s1")
        assert loaded2 is not None
        assert "leak" not in loaded2.attributes
