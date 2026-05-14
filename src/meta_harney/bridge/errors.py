"""JSON-RPC error codes + bridge-specific exception hierarchy."""

from __future__ import annotations

# Standard JSON-RPC 2.0 codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Bridge-specific codes (in the implementation-defined server-error range)
SESSION_NOT_FOUND = -32000
PERMISSION_DENIED = -32001
CANCELLED = -32002
SHUTDOWN = -32003


class BridgeError(Exception):
    """Base for bridge-specific exceptions. Carries a JSON-RPC error code."""

    code: int = INTERNAL_ERROR

    def __init__(self, message: str = "", *, data: object | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.data = data


class ParseError(BridgeError):
    code = PARSE_ERROR


class InvalidRequest(BridgeError):
    code = INVALID_REQUEST


class MethodNotFound(BridgeError):
    code = METHOD_NOT_FOUND


class InvalidParams(BridgeError):
    code = INVALID_PARAMS


class InternalError(BridgeError):
    code = INTERNAL_ERROR


class SessionNotFound(BridgeError):
    code = SESSION_NOT_FOUND


class PermissionDenied(BridgeError):
    code = PERMISSION_DENIED


class Cancelled(BridgeError):
    code = CANCELLED


class ShuttingDown(BridgeError):
    code = SHUTDOWN
