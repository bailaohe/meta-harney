"""JsonlSink — buffers events, writes JSON-Lines to disk on flush().

Suitable for development; production should use a buffered async sink
that ships to APM/Loki/etc.
"""

from __future__ import annotations

from pathlib import Path

from meta_harney.abstractions.trace import TraceEvent


class JsonlSink:
    """Append-only JSON-Lines sink."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._buf: list[str] = []

    async def emit(self, event: TraceEvent) -> None:
        self._buf.append(event.model_dump_json())

    async def flush(self) -> None:
        if not self._buf:
            return
        with self.path.open("a", encoding="utf-8") as f:
            for line in self._buf:
                f.write(line)
                f.write("\n")
        self._buf.clear()
