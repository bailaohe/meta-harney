/**
 * JSON-RPC 2.0 protocol types and codec for the meta-harney bridge.
 *
 * Mirrors the Phase 10 Python protocol layer:
 *   - `parseIncoming` decodes a single framed payload into a discriminated
 *     union of {request, response, notification}.
 *   - `encodeRequest` / `encodeNotification` / `encodeResponse` / `encodeError`
 *     produce canonical JSON-RPC 2.0 payloads suitable for any `Framing`.
 *
 * Framing (newline / Content-Length) is intentionally out of scope here; the
 * codec works at the payload level so the same types can ride on either
 * framing strategy.
 */

export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export interface JsonRpcRequest {
  kind: "request";
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params?: unknown;
}

export interface JsonRpcResponse {
  kind: "response";
  jsonrpc: "2.0";
  id: number | string | null;
  result?: unknown;
  error?: JsonRpcError;
}

export interface JsonRpcNotification {
  kind: "notification";
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
}

export type IncomingMessage =
  | JsonRpcRequest
  | JsonRpcResponse
  | JsonRpcNotification;

interface RawJsonRpc {
  jsonrpc?: unknown;
  id?: unknown;
  method?: unknown;
  params?: unknown;
  result?: unknown;
  error?: unknown;
}

function isPlainObject(v: unknown): v is RawJsonRpc {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isValidId(v: unknown): v is number | string {
  return typeof v === "number" || typeof v === "string";
}

function isValidIdOrNull(v: unknown): v is number | string | null {
  return v === null || isValidId(v);
}

function isJsonRpcError(v: unknown): v is JsonRpcError {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false;
  const o = v as { code?: unknown; message?: unknown };
  return typeof o.code === "number" && typeof o.message === "string";
}

/**
 * Decode one JSON-RPC 2.0 payload. Throws on invalid JSON, non-object roots,
 * missing/wrong `jsonrpc` version, or shapes that don't match any known
 * message kind.
 */
export function parseIncoming(raw: Buffer): IncomingMessage {
  let data: unknown;
  try {
    data = JSON.parse(raw.toString("utf-8"));
  } catch (e) {
    throw new Error(`invalid JSON: ${(e as Error).message}`);
  }
  if (!isPlainObject(data)) {
    throw new Error("invalid JSON-RPC payload: not a JSON object");
  }
  if (data.jsonrpc !== "2.0") {
    throw new Error("missing/invalid jsonrpc field (must be '2.0')");
  }

  const hasId = "id" in data;
  const hasMethod = "method" in data;
  const hasResult = "result" in data;
  const hasError = "error" in data;

  if (hasMethod && hasId) {
    if (typeof data.method !== "string") {
      throw new Error("invalid request: method must be a string");
    }
    if (!isValidId(data.id)) {
      throw new Error("invalid request: id must be number or string");
    }
    const req: JsonRpcRequest = {
      kind: "request",
      jsonrpc: "2.0",
      id: data.id,
      method: data.method,
    };
    if ("params" in data) req.params = data.params;
    return req;
  }
  if (hasMethod && !hasId) {
    if (typeof data.method !== "string") {
      throw new Error("invalid notification: method must be a string");
    }
    const note: JsonRpcNotification = {
      kind: "notification",
      jsonrpc: "2.0",
      method: data.method,
    };
    if ("params" in data) note.params = data.params;
    return note;
  }
  if (hasId && (hasResult || hasError)) {
    if (!isValidIdOrNull(data.id)) {
      throw new Error("invalid response: id must be number, string, or null");
    }
    const resp: JsonRpcResponse = {
      kind: "response",
      jsonrpc: "2.0",
      id: data.id,
    };
    if (hasResult) resp.result = data.result;
    if (hasError) {
      if (!isJsonRpcError(data.error)) {
        throw new Error(
          "invalid response: error must be {code:number,message:string}",
        );
      }
      resp.error = data.error;
    }
    return resp;
  }
  throw new Error(
    `cannot classify message: keys=[${Object.keys(data).join(",")}]`,
  );
}

/** Encode a JSON-RPC 2.0 request payload (no framing applied). */
export function encodeRequest(
  id: number | string,
  method: string,
  params?: unknown,
): Buffer {
  const obj: Record<string, unknown> = { jsonrpc: "2.0", id, method };
  if (params !== undefined) obj.params = params;
  return Buffer.from(JSON.stringify(obj), "utf-8");
}

/** Encode a JSON-RPC 2.0 notification payload (no id, no framing applied). */
export function encodeNotification(method: string, params?: unknown): Buffer {
  const obj: Record<string, unknown> = { jsonrpc: "2.0", method };
  if (params !== undefined) obj.params = params;
  return Buffer.from(JSON.stringify(obj), "utf-8");
}

/** Encode a successful JSON-RPC 2.0 response payload (no framing applied). */
export function encodeResponse(
  id: number | string | null,
  result: unknown,
): Buffer {
  return Buffer.from(
    JSON.stringify({ jsonrpc: "2.0", id, result }),
    "utf-8",
  );
}

/** Encode an error JSON-RPC 2.0 response payload (no framing applied). */
export function encodeError(
  id: number | string | null,
  error: JsonRpcError,
): Buffer {
  return Buffer.from(
    JSON.stringify({ jsonrpc: "2.0", id, error }),
    "utf-8",
  );
}
