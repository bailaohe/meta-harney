import { describe, it, expect } from "vitest";
import {
  parseIncoming,
  encodeRequest,
  encodeNotification,
  encodeResponse,
  encodeError,
  type JsonRpcRequest,
  type JsonRpcResponse,
  type JsonRpcNotification,
} from "../src/protocol.js";
import {
  BridgeError,
  BridgeCancelled,
  BridgeDisconnected,
} from "../src/errors.js";

describe("parseIncoming", () => {
  it("recognizes request", () => {
    const msg = parseIncoming(
      Buffer.from('{"jsonrpc":"2.0","id":1,"method":"ping"}'),
    );
    expect(msg.kind).toBe("request");
    expect((msg as JsonRpcRequest).method).toBe("ping");
    expect((msg as JsonRpcRequest).id).toBe(1);
  });

  it("recognizes request with string id and params", () => {
    const msg = parseIncoming(
      Buffer.from(
        '{"jsonrpc":"2.0","id":"abc","method":"foo","params":{"x":1}}',
      ),
    );
    expect(msg.kind).toBe("request");
    const req = msg as JsonRpcRequest;
    expect(req.id).toBe("abc");
    expect(req.method).toBe("foo");
    expect(req.params).toEqual({ x: 1 });
  });

  it("recognizes response (result)", () => {
    const msg = parseIncoming(
      Buffer.from('{"jsonrpc":"2.0","id":1,"result":42}'),
    );
    expect(msg.kind).toBe("response");
    expect((msg as JsonRpcResponse).result).toBe(42);
  });

  it("recognizes response (error)", () => {
    const msg = parseIncoming(
      Buffer.from(
        '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"x"}}',
      ),
    );
    expect(msg.kind).toBe("response");
    const err = (msg as JsonRpcResponse).error;
    expect(err).toBeDefined();
    expect(err?.code).toBe(-32601);
    expect(err?.message).toBe("x");
  });

  it("recognizes notification", () => {
    const msg = parseIncoming(
      Buffer.from(
        '{"jsonrpc":"2.0","method":"$/cancelRequest","params":{"id":7}}',
      ),
    );
    expect(msg.kind).toBe("notification");
    expect((msg as JsonRpcNotification).method).toBe("$/cancelRequest");
    expect((msg as JsonRpcNotification).params).toEqual({ id: 7 });
  });

  it("rejects non-2.0", () => {
    expect(() =>
      parseIncoming(Buffer.from('{"id":1,"method":"ping"}')),
    ).toThrow(/jsonrpc/);
  });

  it("rejects invalid JSON", () => {
    expect(() => parseIncoming(Buffer.from("not json"))).toThrow(/invalid/i);
  });

  it("rejects non-object payload", () => {
    expect(() => parseIncoming(Buffer.from("42"))).toThrow();
  });

  it("rejects message that cannot be classified", () => {
    // jsonrpc-only object: no method, no id+result/error
    expect(() => parseIncoming(Buffer.from('{"jsonrpc":"2.0"}'))).toThrow(
      /classify/,
    );
  });
});

describe("encoders", () => {
  it("encodeRequest produces canonical JSON-RPC 2.0 request", () => {
    const buf = encodeRequest(1, "ping");
    const obj = JSON.parse(buf.toString("utf-8"));
    expect(obj).toEqual({ jsonrpc: "2.0", id: 1, method: "ping" });
  });

  it("encodeRequest includes params when provided", () => {
    const buf = encodeRequest("req-1", "echo", { hi: 1 });
    const obj = JSON.parse(buf.toString("utf-8"));
    expect(obj).toEqual({
      jsonrpc: "2.0",
      id: "req-1",
      method: "echo",
      params: { hi: 1 },
    });
  });

  it("encodeNotification omits id", () => {
    const buf = encodeNotification("$/cancelRequest", { id: 7 });
    const obj = JSON.parse(buf.toString("utf-8"));
    expect(obj).toEqual({
      jsonrpc: "2.0",
      method: "$/cancelRequest",
      params: { id: 7 },
    });
    expect("id" in obj).toBe(false);
  });

  it("encodeResponse carries result", () => {
    const buf = encodeResponse(1, { ok: true });
    const obj = JSON.parse(buf.toString("utf-8"));
    expect(obj).toEqual({ jsonrpc: "2.0", id: 1, result: { ok: true } });
  });

  it("encodeError carries error object", () => {
    const buf = encodeError(1, { code: -32601, message: "Method not found" });
    const obj = JSON.parse(buf.toString("utf-8"));
    expect(obj).toEqual({
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32601, message: "Method not found" },
    });
  });

  it("round-trips request through parseIncoming", () => {
    const buf = encodeRequest(7, "do", { a: 1 });
    const msg = parseIncoming(buf);
    expect(msg.kind).toBe("request");
    const req = msg as JsonRpcRequest;
    expect(req.id).toBe(7);
    expect(req.method).toBe("do");
    expect(req.params).toEqual({ a: 1 });
  });
});

describe("BridgeError hierarchy", () => {
  it("BridgeError carries code + optional data", () => {
    const e = new BridgeError("boom", -32000, { detail: "x" });
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("BridgeError");
    expect(e.message).toBe("boom");
    expect(e.code).toBe(-32000);
    expect(e.data).toEqual({ detail: "x" });
  });

  it("BridgeCancelled is a BridgeError with code -32002", () => {
    const e = new BridgeCancelled();
    expect(e).toBeInstanceOf(BridgeError);
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("BridgeCancelled");
    expect(e.code).toBe(-32002);
  });

  it("BridgeDisconnected is plain Error (no code)", () => {
    const e = new BridgeDisconnected();
    expect(e).toBeInstanceOf(Error);
    expect(e).not.toBeInstanceOf(BridgeError);
    expect(e.name).toBe("BridgeDisconnected");
  });
});
