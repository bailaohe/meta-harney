"""End-to-end subprocess test for the bridge.

Spawns ``python -m meta_harney.bridge.example`` and drives the full JSON-RPC
lifecycle over its real stdin / stdout. This proves the production code path
in ``BridgeServer.serve_stdio()`` works on the target platform (no fakes for
the transport layer — only the runtime is stubbed).
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest


async def _send(proc: asyncio.subprocess.Process, req: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(req).encode() + b"\n")
    await proc.stdin.drain()


async def _read_one(proc: asyncio.subprocess.Process) -> dict[str, Any]:
    assert proc.stdout is not None
    line = await proc.stdout.readline()
    assert line, "subprocess closed stdout unexpectedly"
    parsed: dict[str, Any] = json.loads(line)
    return parsed


@pytest.mark.asyncio
async def test_subprocess_full_lifecycle() -> None:
    """Drive the example bridge through initialize → session → stream → exit.

    Verifies (in wire order):
      1. ``initialize`` returns the example's server_info
      2. ``session.create`` returns a session id
      3. ``session.send_message`` emits ≥1 ``stream/event`` notification then
         a final response with ``stopped_reason``
      4. ``shutdown`` returns successfully
      5. ``exit`` notification causes the subprocess to exit with code 0
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "meta_harney.bridge.example",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        # 1. initialize
        await _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        resp = await asyncio.wait_for(_read_one(proc), timeout=5)
        assert resp["id"] == 1
        assert resp["result"]["server_info"]["name"] == "meta-harney-bridge-example"
        assert resp["result"]["capabilities"]["streaming"] is True

        # 2. session.create
        await _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "session.create"})
        resp = await asyncio.wait_for(_read_one(proc), timeout=5)
        assert resp["id"] == 2
        sid = resp["result"]["id"]
        assert isinstance(sid, str) and sid

        # 3. session.send_message — expect stream/event notifications then final response
        await _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session.send_message",
                "params": {
                    "session_id": sid,
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hi"}],
                    },
                },
            },
        )

        got_final = False
        stream_event_count = 0
        final_response: dict[str, Any] | None = None
        for _ in range(100):
            msg = await asyncio.wait_for(_read_one(proc), timeout=5)
            if msg.get("method") == "stream/event":
                stream_event_count += 1
                assert msg["params"]["request_id"] == 3
            elif msg.get("id") == 3:
                got_final = True
                final_response = msg
                break
        assert got_final, "never received final response for send_message"
        assert stream_event_count >= 1, "expected at least one stream/event notification"
        assert final_response is not None
        assert final_response["result"]["stopped_reason"] == "completed"

        # 4. shutdown
        await _send(proc, {"jsonrpc": "2.0", "id": 99, "method": "shutdown"})
        resp = await asyncio.wait_for(_read_one(proc), timeout=5)
        assert resp["id"] == 99

        # 5. exit notification → process should terminate cleanly
        await _send(proc, {"jsonrpc": "2.0", "method": "exit"})
        # Close stdin so any pending readline in the subprocess returns EOF.
        proc.stdin.close()

        await asyncio.wait_for(proc.wait(), timeout=5)
        assert proc.returncode == 0, (
            f"subprocess exited with code {proc.returncode}; "
            f"stderr={(await proc.stderr.read()).decode() if proc.stderr else ''}"
        )
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
