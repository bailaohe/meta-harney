"""Tests for BaseTask ABC + TaskState."""

from __future__ import annotations

import pytest

from meta_harney.abstractions.task import BaseTask, TaskState


def test_task_state_values():
    assert TaskState.PENDING.value == "pending"
    assert TaskState.RUNNING.value == "running"
    assert TaskState.SUCCEEDED.value == "succeeded"
    assert TaskState.FAILED.value == "failed"
    assert TaskState.CANCELLED.value == "cancelled"


def test_base_task_is_abstract():
    with pytest.raises(TypeError):
        BaseTask()  # type: ignore[abstract]


async def test_concrete_task_subclass():
    class HelloTask(BaseTask):
        def __init__(self):
            self.task_id = "t1"
            self.state = TaskState.PENDING

        async def run(self) -> str:
            self.state = TaskState.RUNNING
            self.state = TaskState.SUCCEEDED
            return "done"

        async def cancel(self) -> None:
            self.state = TaskState.CANCELLED

    t = HelloTask()
    result = await t.run()
    assert result == "done"
    assert t.state == TaskState.SUCCEEDED
