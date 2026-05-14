"""JSON-RPC 2.0 message models."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class JsonRpcError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    message: str
    data: Any = None


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JsonRpcError | None = None


class JsonRpcNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None


IncomingMessage = JsonRpcRequest | JsonRpcResponse | JsonRpcNotification


def parse_incoming(raw: bytes) -> IncomingMessage:
    """Parse a JSON-RPC frame into the right typed model.

    Dispatch by shape:
    - Has `id` AND `method` -> Request
    - Has `id` AND (`result` OR `error`) -> Response
    - Has `method` AND no `id` -> Notification
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON-RPC message must be an object")
    if data.get("jsonrpc") != "2.0":
        raise ValueError("missing or invalid 'jsonrpc' field (must be '2.0')")

    has_id = "id" in data
    has_method = "method" in data
    has_result_or_error = "result" in data or "error" in data

    if has_method and has_id:
        return JsonRpcRequest.model_validate(data)
    if has_method and not has_id:
        return JsonRpcNotification.model_validate(data)
    if has_id and has_result_or_error:
        return JsonRpcResponse.model_validate(data)
    raise ValueError(f"cannot classify JSON-RPC message: keys={sorted(data.keys())}")
