"""Task abstraction: BaseTask ABC + TaskState enum.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.6.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BaseTask(ABC):
    """Base for background tasks managed by the runtime.

    Subclasses set `task_id` and `state` in __init__ and implement async
    `run()` and `cancel()`. The TaskManager (introduced in Phase 2) owns
    a registry of running tasks.
    """

    task_id: str
    state: TaskState

    @abstractmethod
    async def run(self) -> Any: ...

    @abstractmethod
    async def cancel(self) -> None: ...
