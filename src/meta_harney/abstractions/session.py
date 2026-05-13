"""Session abstraction: Session model + SessionStore Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.7.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from meta_harney.abstractions._types import Message


class Session(BaseModel):
    """Authoritative session state.

    `attributes` is the business self-service area: customer ids, order
    numbers, anything outside of message content. `version` is the
    optimistic-lock token enforced by SessionStore implementations.
    """

    id: str
    tenant_id: str | None = None
    user_id: str | None = None
    parent_session_id: str | None = None
    created_at: datetime
    version: int = 0
    messages: list[Message] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionStore(Protocol):
    """Persistence backend for Session.

    Implementations MUST:
    - Support tenant filtering on `load()` and `list()`.
    - Enforce optimistic locking on `save()` — raise `SessionConflictError`
      when the in-store version doesn't match the incoming session's version.
    - Increment `session.version` on every successful save.

    These contracts are validated by `SessionStoreContract` test suite.
    """

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None: ...

    async def save(self, session: Session) -> None: ...

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]: ...

    async def delete(self, session_id: str) -> None: ...
