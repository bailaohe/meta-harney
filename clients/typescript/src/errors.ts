/**
 * Bridge error hierarchy.
 *
 *   BridgeError       — JSON-RPC error response surfaced to the caller.
 *                       Carries the numeric `code` and optional `data` payload
 *                       from the wire format.
 *   BridgeCancelled   — server-side cancellation (code -32002), thrown when a
 *                       request is cancelled via `$/cancelRequest`.
 *   BridgeDisconnected — the bridge child process exited or its stdio closed
 *                        while a request was in flight. Not a JSON-RPC error,
 *                        so it does NOT extend BridgeError.
 */

export class BridgeError extends Error {
  public readonly code: number;
  public readonly data?: unknown;

  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
    if (data !== undefined) this.data = data;
    // Restore prototype chain across down-level targets so
    // `instanceof BridgeError` works on subclasses too.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class BridgeCancelled extends BridgeError {
  constructor(message = "request cancelled") {
    super(message, -32002);
    this.name = "BridgeCancelled";
  }
}

export class BridgeDisconnected extends Error {
  constructor(message = "bridge process disconnected") {
    super(message);
    this.name = "BridgeDisconnected";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
