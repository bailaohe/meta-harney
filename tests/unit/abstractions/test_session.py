"""Tests for Session model + SessionStore Protocol."""

from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session, SessionStore


def test_session_minimal():
    s = Session(id="s1", created_at=datetime.now(timezone.utc))
    assert s.id == "s1"
    assert s.tenant_id is None
    assert s.user_id is None
    assert s.parent_session_id is None
    assert s.version == 0
    assert s.messages == []
    assert s.attributes == {}
    assert s.metadata == {}


def test_session_full():
    now = datetime.now(timezone.utc)
    s = Session(
        id="s1",
        tenant_id="acme",
        user_id="u1",
        parent_session_id="parent-s",
        created_at=now,
        version=3,
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        attributes={"customer_id": "C-001"},
        metadata={"app_version": "1.0"},
    )
    assert s.tenant_id == "acme"
    assert s.attributes["customer_id"] == "C-001"
    assert len(s.messages) == 1


def test_session_attributes_free_form():
    s = Session(id="s1", created_at=datetime.now(timezone.utc))
    s.attributes["nested"] = {"a": [1, 2, 3]}
    assert s.attributes["nested"]["a"] == [1, 2, 3]


async def test_protocol_satisfied_by_duck_typing():
    """SessionStore is a Protocol — duck typing suffices."""

    class FakeStore:
        def __init__(self):
            self._data: dict[str, Session] = {}

        async def load(self, session_id, *, tenant_id=None):
            s = self._data.get(session_id)
            if s and tenant_id and s.tenant_id != tenant_id:
                return None
            return s

        async def save(self, session):
            self._data[session.id] = session

        async def list(self, *, tenant_id=None, filter=None):
            results = list(self._data.values())
            if tenant_id is not None:
                results = [s for s in results if s.tenant_id == tenant_id]
            return results

        async def delete(self, session_id):
            self._data.pop(session_id, None)

    store: SessionStore = FakeStore()
    s = Session(id="s1", tenant_id="acme", created_at=datetime.now(timezone.utc))
    await store.save(s)
    assert (await store.load("s1")).id == "s1"
    assert (await store.load("s1", tenant_id="other")) is None
    assert len(await store.list(tenant_id="acme")) == 1
