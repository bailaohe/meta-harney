"""Tests for newline and content-length framings."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Awaitable, Iterable
from pathlib import Path

import pytest

from meta_harney.bridge.framing import ContentLengthFraming, NewlineFraming


async def _drain_to_bytes(coros: Iterable[Awaitable[None]]) -> bytes:
    """Helper: pump a list of writes through a pipe and collect bytes."""
    wr = io.BytesIO()
    for c in coros:
        await c
    return wr.getvalue()


@pytest.mark.asyncio
async def test_newline_framing_writes_one_line(tmp_path: Path) -> None:
    framing = NewlineFraming()
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"a":1}\n')
    reader.feed_eof()
    msg = await framing.read_message(reader)
    assert msg == b'{"a":1}'


@pytest.mark.asyncio
async def test_newline_framing_round_trip() -> None:
    framing = NewlineFraming()
    payload = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    # write side
    transport_buf = io.BytesIO()

    # use a simple writer shim that records into transport_buf
    class _Writer:
        def write(self, data: bytes) -> None:
            transport_buf.write(data)

        async def drain(self) -> None:
            return None

    await framing.write_message(_Writer(), payload)  # type: ignore[arg-type]
    written = transport_buf.getvalue()
    assert written == payload + b"\n"

    reader = asyncio.StreamReader()
    reader.feed_data(written)
    reader.feed_eof()
    out = await framing.read_message(reader)
    assert out == payload


@pytest.mark.asyncio
async def test_newline_framing_eof_returns_none() -> None:
    framing = NewlineFraming()
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await framing.read_message(reader) is None


@pytest.mark.asyncio
async def test_content_length_framing_round_trip() -> None:
    framing = ContentLengthFraming()
    payload = b'{"large":"' + b"x" * 1024 + b'"}'
    transport_buf = io.BytesIO()

    class _Writer:
        def write(self, data: bytes) -> None:
            transport_buf.write(data)

        async def drain(self) -> None:
            return None

    await framing.write_message(_Writer(), payload)  # type: ignore[arg-type]
    written = transport_buf.getvalue()
    assert written.startswith(b"Content-Length: ")
    assert payload in written

    reader = asyncio.StreamReader()
    reader.feed_data(written)
    reader.feed_eof()
    out = await framing.read_message(reader)
    assert out == payload


@pytest.mark.asyncio
async def test_content_length_framing_handles_multi_message_stream() -> None:
    framing = ContentLengthFraming()
    bufs = []

    class _Writer:
        def write(self, data: bytes) -> None:
            bufs.append(data)

        async def drain(self) -> None:
            return None

    w = _Writer()
    await framing.write_message(w, b'{"a":1}')  # type: ignore[arg-type]
    await framing.write_message(w, b'{"b":2}')  # type: ignore[arg-type]

    reader = asyncio.StreamReader()
    reader.feed_data(b"".join(bufs))
    reader.feed_eof()
    a = await framing.read_message(reader)
    b = await framing.read_message(reader)
    assert a == b'{"a":1}'
    assert b == b'{"b":2}'


@pytest.mark.asyncio
async def test_content_length_framing_eof_returns_none() -> None:
    framing = ContentLengthFraming()
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await framing.read_message(reader) is None
