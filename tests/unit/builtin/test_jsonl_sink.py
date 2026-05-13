import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.builtin.trace.jsonl_sink import JsonlSink
from tests.contracts.trace_sink import TraceSinkContract


class TestJsonlSink(TraceSinkContract):
    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path: Path) -> None:
        self._path = tmp_path / "trace.jsonl"

    def make_sink(self) -> JsonlSink:
        return JsonlSink(self._path)


# JsonlSink-specific behavior checks:


async def test_jsonl_writes_after_flush(tmp_path: Path) -> None:
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="tool.invoked",
        span_id="x",
        payload={"a": 1},
    )
    await sink.emit(ev)
    assert not log.exists() or log.read_text() == ""
    await sink.flush()
    assert log.exists()
    parsed = json.loads(log.read_text().strip())
    assert parsed["kind"] == "tool.invoked"
    assert parsed["payload"] == {"a": 1}


async def test_jsonl_appends_across_flushes(tmp_path: Path) -> None:
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    for i in range(3):
        await sink.emit(
            TraceEvent(
                ts=datetime.now(timezone.utc),
                session_id="s",
                kind="x.y",
                span_id=str(i),
                payload={},
            )
        )
    await sink.flush()
    for i in range(3, 5):
        await sink.emit(
            TraceEvent(
                ts=datetime.now(timezone.utc),
                session_id="s",
                kind="x.y",
                span_id=str(i),
                payload={},
            )
        )
    await sink.flush()
    assert len(log.read_text().splitlines()) == 5
