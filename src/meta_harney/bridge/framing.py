"""Framing strategies for the bridge transport.

Two framings are supported. Callers pick one when constructing BridgeServer.

- NewlineFraming: one JSON object per `\n`-terminated line. Debuggable with cat.
- ContentLengthFraming: LSP-style `Content-Length: N\r\n\r\n<bytes>`.
"""

from __future__ import annotations

import asyncio
from typing import Protocol


class Framing(Protocol):
    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        """Read one complete message. Return None on EOF before any bytes."""
        ...

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        """Frame and write one message. Caller is responsible for flushing if needed."""
        ...


class NewlineFraming:
    """Newline-delimited JSON. One message per line, terminated by '\\n'."""

    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        line = await reader.readline()
        if not line:
            return None
        # Strip the trailing newline (always exactly one '\n', no '\r')
        return line.rstrip(b"\r\n")

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        writer.write(payload + b"\n")
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()


class ContentLengthFraming:
    """LSP-style framing: `Content-Length: N\\r\\n\\r\\n<N bytes>`."""

    _HEADER_TERMINATOR = b"\r\n\r\n"

    async def read_message(self, reader: asyncio.StreamReader) -> bytes | None:
        # Read header lines until blank line
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line:
                return None
            if line == b"\r\n" or line == b"\n":
                break
            try:
                k, _, v = line.decode("ascii", errors="replace").partition(":")
            except Exception:
                continue
            headers[k.strip().lower()] = v.strip()

        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"missing or invalid Content-Length header: {headers!r}") from exc

        body = await reader.readexactly(length)
        return body

    async def write_message(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        writer.write(header + payload)
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()
