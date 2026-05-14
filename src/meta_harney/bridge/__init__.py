"""meta_harney.bridge — JSON-RPC 2.0 server exposing AgentRuntime over stdio."""

from meta_harney.bridge.errors import (
    BridgeError,
    Cancelled,
    InternalError,
    InvalidParams,
    InvalidRequest,
    MethodNotFound,
    ParseError,
    PermissionDenied,
    SessionNotFound,
    ShuttingDown,
)
from meta_harney.bridge.framing import (
    ContentLengthFraming,
    Framing,
    NewlineFraming,
)
from meta_harney.bridge.permission import BridgePermissionResolver
from meta_harney.bridge.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_incoming,
)
from meta_harney.bridge.server import BridgeServer
from meta_harney.bridge.trace import BridgeTraceSink

__all__ = [
    "BridgeError",
    "BridgePermissionResolver",
    "BridgeServer",
    "BridgeTraceSink",
    "Cancelled",
    "ContentLengthFraming",
    "Framing",
    "InternalError",
    "InvalidParams",
    "InvalidRequest",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "MethodNotFound",
    "NewlineFraming",
    "ParseError",
    "PermissionDenied",
    "SessionNotFound",
    "ShuttingDown",
    "parse_incoming",
]
