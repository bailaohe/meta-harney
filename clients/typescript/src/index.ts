/**
 * @meta-harney/bridge-client
 *
 * TypeScript JSON-RPC client for the meta-harney bridge protocol.
 */

export { NewlineFraming, ContentLengthFraming } from "./framing.js";
export type { Framing } from "./framing.js";

export {
  parseIncoming,
  encodeRequest,
  encodeNotification,
  encodeResponse,
  encodeError,
} from "./protocol.js";
export type {
  JsonRpcError,
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcNotification,
  IncomingMessage,
} from "./protocol.js";

export { BridgeError, BridgeCancelled, BridgeDisconnected } from "./errors.js";

export { ChildProcessTransport } from "./transport.js";
export type { TransportOptions } from "./transport.js";

export { BridgeClient } from "./client.js";
export type {
  BridgeClientOptions,
  InitializeParams,
  InitializeResult,
  SessionCreateParams,
  SessionSummary,
  SessionListEntry,
  SessionLoadResult,
  ToolSpec,
} from "./client.js";

export const VERSION = "0.1.0";
