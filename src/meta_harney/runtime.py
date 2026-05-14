"""AgentRuntime — top-level SDK entry point.

Wraps the engine.run_turn primitive with session lifecycle management,
service composition, and a clean two-method API (invoke + stream).

Phase 3 scope: create_session + invoke + stream. Multi-agent backend is
wired in (Phase 3 Task 11) so tools can spawn child agents.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import BaseHook
from meta_harney.abstractions.multi_agent import MultiAgentBackend
from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.tool import BaseTool
from meta_harney.abstractions.trace import TraceSink
from meta_harney.engine.config import RuntimeConfig
from meta_harney.engine.loop import TokenCounter
from meta_harney.errors import SessionConflictError
from meta_harney.providers.base import LLMProvider


class AgentRuntime:
    """Top-level SDK facade for running agent turns.

    Holds all service dependencies as immutable attributes. Provides:
      - create_session(): create + persist a new Session
      - invoke(): run one turn, return final assistant message (blocking)
      - stream(): run one turn, yield StreamEvents
    """

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_builder: PromptBuilder,
        permission_resolver: PermissionResolver,
        session_store: SessionStore,
        trace_sink: TraceSink,
        config: RuntimeConfig,
        tools: dict[str, BaseTool] | None = None,
        hooks: list[BaseHook] | None = None,
        compaction: CompactionStrategy | None = None,
        token_counter: TokenCounter | None = None,
        multi_agent: MultiAgentBackend | None = None,
    ) -> None:
        self._provider = provider
        self._prompt_builder = prompt_builder
        self._permission_resolver = permission_resolver
        self._session_store = session_store
        self._trace_sink = trace_sink
        self._config = config
        self._tools = tools or {}
        self._hooks = hooks or []
        self._compaction = compaction
        self._token_counter = token_counter
        self._multi_agent = multi_agent

    async def create_session(
        self,
        *,
        session_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create and persist a new session.

        - `session_id`: if omitted, a UUID hex is generated.
        - If the id already exists in the store, raises SessionConflictError.
        """
        sid = session_id or uuid.uuid4().hex
        existing = await self._session_store.load(sid)
        if existing is not None:
            raise SessionConflictError(
                session_id=sid, expected_version=0, found_version=existing.version
            )
        s = Session(
            id=sid,
            tenant_id=tenant_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            attributes=dict(attributes) if attributes else {},
            metadata=dict(metadata) if metadata else {},
        )
        await self._session_store.save(s)
        return s
