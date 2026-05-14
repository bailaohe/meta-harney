"""Tests for JSON-RPC 2.0 protocol models."""

from __future__ import annotations

import json

import pytest

from meta_harney.bridge.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_incoming,
)


def test_request_roundtrip() -> None:
    r = JsonRpcRequest(id=1, method="ping", params={"x": 1})
    raw = r.model_dump_json()
    parsed = JsonRpcRequest.model_validate_json(raw)
    assert parsed == r
    assert parsed.jsonrpc == "2.0"


def test_response_success_roundtrip() -> None:
    r = JsonRpcResponse(id=1, result={"pong": True})
    raw = r.model_dump_json()
    parsed = JsonRpcResponse.model_validate_json(raw)
    assert parsed.result == {"pong": True}
    assert parsed.error is None


def test_response_error_roundtrip() -> None:
    err = JsonRpcError(code=-32601, message="method not found")
    r = JsonRpcResponse(id=1, error=err)
    parsed = JsonRpcResponse.model_validate_json(r.model_dump_json())
    assert parsed.error is not None
    assert parsed.error.code == -32601


def test_notification_has_no_id() -> None:
    n = JsonRpcNotification(method="$/cancelRequest", params={"id": 7})
    raw = json.loads(n.model_dump_json())
    assert "id" not in raw
    assert raw["method"] == "$/cancelRequest"


def test_parse_incoming_dispatches_by_shape() -> None:
    # request
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"method":"ping"}')
    assert isinstance(msg, JsonRpcRequest)
    # response with result
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"result":42}')
    assert isinstance(msg, JsonRpcResponse)
    # response with error
    msg = parse_incoming(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"x"}}')
    assert isinstance(msg, JsonRpcResponse)
    # notification (no id)
    msg = parse_incoming(b'{"jsonrpc":"2.0","method":"hello"}')
    assert isinstance(msg, JsonRpcNotification)


def test_parse_incoming_rejects_non_jsonrpc() -> None:
    with pytest.raises(ValueError):
        parse_incoming(b"not json")


def test_parse_incoming_rejects_missing_jsonrpc_field() -> None:
    with pytest.raises(ValueError):
        parse_incoming(b'{"id":1,"method":"ping"}')
