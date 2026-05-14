/**
 * BridgeClient lifecycle + read loop + pending request table.
 *
 * Uses a FakeTransport so the tests stay deterministic and avoid spawning
 * real subprocesses — the ChildProcessTransport integration is already
 * covered by tests/transport.test.ts.
 */

import { describe, it, expect } from "vitest";
import { BridgeClient } from "../src/client.js";
import type { Framing } from "../src/framing.js";
import type { ChildProcessTransport } from "../src/transport.js";
import { BridgeError, BridgeCancelled, BridgeDisconnected } from "../src/errors.js";

interface JsonRpcLike {
  jsonrpc: "2.0";
  id?: number | string | null;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

class FakeTransport {
  framing: Framing = null as unknown as Framing;
  queue: Buffer[] = [];
  sent: Buffer[] = [];
  alive = true;
  started = false;
  stopped = false;
  // A queue of pending read() resolvers, so we can `feed()` after a read has
  // started waiting and have the read complete asynchronously.
  private waiters: Array<(b: Buffer | null) => void> = [];
  // When set, the next read() returns null to signal EOF.
  private eof = false;
  // When set, the next read() rejects with this error.
  private readError: Error | null = null;

  start(): Promise<void> {
    this.started = true;
    return Promise.resolve();
  }

  stop(): Promise<number | null> {
    this.alive = false;
    this.stopped = true;
    // Wake any pending readers with EOF so the read loop can exit cleanly.
    this.eof = true;
    const ws = this.waiters;
    this.waiters = [];
    for (const w of ws) w(null);
    return Promise.resolve(0);
  }

  read(): Promise<Buffer | null> {
    if (this.readError !== null) {
      const err = this.readError;
      this.readError = null;
      return Promise.reject(err);
    }
    if (this.queue.length > 0) {
      return Promise.resolve(this.queue.shift() ?? null);
    }
    if (this.eof) {
      return Promise.resolve(null);
    }
    return new Promise<Buffer | null>((resolve) => {
      this.waiters.push(resolve);
    });
  }

  write(p: Buffer): Promise<void> {
    this.sent.push(p);
    return Promise.resolve();
  }

  isAlive(): boolean {
    return this.alive;
  }

  /** Push a response/notification onto the inbound queue. */
  feed(obj: JsonRpcLike): void {
    const buf = Buffer.from(JSON.stringify(obj));
    if (this.waiters.length > 0) {
      const w = this.waiters.shift();
      if (w) {
        w(buf);
        return;
      }
    }
    this.queue.push(buf);
  }

  /** Force the next read() to throw. */
  failNextRead(err: Error): void {
    this.readError = err;
    const w = this.waiters.shift();
    if (w) {
      // Hand the error off via the waiter path — re-set so read() picks it up.
      // We resolve with null but flip the error flag for the next call instead.
      // Simplest: just push an immediate-fail sentinel.
      this.readError = err;
      w(null); // wake; the caller (BridgeClient.readLoop) will see null and exit.
      // Actually we want the error to surface, so swap: keep readError and signal EOF.
    }
  }

  /** Force the inbound stream to EOF (read() resolves null) without stopping. */
  signalEof(): void {
    this.eof = true;
    const ws = this.waiters;
    this.waiters = [];
    for (const w of ws) w(null);
  }
}

function decode(buf: Buffer): JsonRpcLike {
  return JSON.parse(buf.toString()) as JsonRpcLike;
}

function makeClient(t: FakeTransport): BridgeClient {
  return new BridgeClient({ transport: t as unknown as ChildProcessTransport });
}

describe("BridgeClient lifecycle", () => {
  it("initialize sends request and returns server info", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // Pre-feed the response; readLoop pumps it as soon as initialize writes.
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: {
        server_info: { name: "x", version: "1" },
        protocol_version: 1,
        capabilities: {},
      },
    });
    const info = await client.initialize({
      clientInfo: { name: "test", version: "0" },
    });
    expect(info.server_info.name).toBe("x");
    expect(info.protocol_version).toBe(1);
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("initialize");
    expect(sent.id).toBe(1);
    const params = sent.params as { client_info: { name: string } };
    expect(params.client_info.name).toBe("test");
    await client.exit();
  });

  it("shutdown sends shutdown request, exit sends notification", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({ jsonrpc: "2.0", id: 1, result: null });
    await client.shutdown();
    await client.exit();
    const methods = t.sent.map((b) => decode(b).method);
    expect(methods).toEqual(["shutdown", "exit"]);
    // shutdown is a request (has id); exit is a notification (no id).
    expect(decode(t.sent[0]!).id).toBe(1);
    expect("id" in decode(t.sent[1]!)).toBe(false);
    expect(t.stopped).toBe(true);
  });

  it("monotonically allocates request ids", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // Issue the first request, then feed its response; repeat.
    type SR = <T>(method: string, params?: unknown) => Promise<T>;
    const send = (
      client as unknown as { sendRequest: SR }
    ).sendRequest.bind(client) as SR;
    const pa = send<{ ok: number }>("a");
    t.feed({ jsonrpc: "2.0", id: 1, result: { ok: 1 } });
    const a = await pa;
    const pb = send<{ ok: number }>("b");
    t.feed({ jsonrpc: "2.0", id: 2, result: { ok: 2 } });
    const b = await pb;
    expect(a.ok).toBe(1);
    expect(b.ok).toBe(2);
    expect(decode(t.sent[0]!).id).toBe(1);
    expect(decode(t.sent[1]!).id).toBe(2);
    await client.exit();
  });

  it("rejects pending requests with BridgeError on error response", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32601, message: "method not found" },
    });
    await expect(client.shutdown()).rejects.toMatchObject({
      name: "BridgeError",
      code: -32601,
      message: "method not found",
    });
    await client.exit();
  });

  it("ignores responses with unknown ids without crashing", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // Unknown id — should be silently ignored.
    t.feed({ jsonrpc: "2.0", id: 999, result: { stray: true } });
    // Subsequent legitimate request still works.
    t.feed({ jsonrpc: "2.0", id: 1, result: null });
    await client.shutdown();
    await client.exit();
  });

  it("fails inflight requests with BridgeDisconnected on EOF", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // Launch a request that never gets a response.
    const pending = client.shutdown();
    // Simulate the bridge closing its stdout.
    t.signalEof();
    await expect(pending).rejects.toBeInstanceOf(BridgeDisconnected);
  });

  it("dispatches notifications to onNotification hook", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    const received: Array<{ method: string; params: unknown }> = [];
    // Hook is protected; test via a subclass-equivalent assignment.
    (client as unknown as {
      onNotification: (m: string, p: unknown) => void;
    }).onNotification = (method, params) => {
      received.push({ method, params });
    };
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      method: "stream/event",
      params: { request_id: 1, event: { type: "x" } },
    });
    // Give the read loop a tick to pump the message.
    await new Promise((r) => setTimeout(r, 5));
    expect(received).toHaveLength(1);
    expect(received[0]!.method).toBe("stream/event");
    await client.exit();
  });

  it("routes incoming requests via onIncomingRequest and writes the response", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    (client as unknown as {
      onIncomingRequest: (req: {
        id: number | string;
        method: string;
        params: unknown;
      }) => Promise<unknown>;
    }).onIncomingRequest = (req) => {
      if (req.method === "permission/request") {
        return Promise.resolve({ decision: "allow" });
      }
      return Promise.reject(new Error("nope"));
    };
    await client.start();
    // Server-initiated request:
    t.feed({
      jsonrpc: "2.0",
      id: -1,
      method: "permission/request",
      params: { tool: "bash" },
    });
    // Wait for handler to respond.
    await new Promise((r) => setTimeout(r, 10));
    expect(t.sent).toHaveLength(1);
    const resp = decode(t.sent[0]!);
    expect(resp.id).toBe(-1);
    expect(resp.result).toEqual({ decision: "allow" });
    await client.exit();
  });

  it("converts incoming-request handler errors into JSON-RPC error responses", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    (client as unknown as {
      onIncomingRequest: (req: {
        id: number | string;
        method: string;
        params: unknown;
      }) => Promise<unknown>;
    }).onIncomingRequest = () => Promise.reject(new Error("boom"));
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: -2,
      method: "permission/request",
      params: {},
    });
    await new Promise((r) => setTimeout(r, 10));
    const resp = decode(t.sent[0]!);
    expect(resp.id).toBe(-2);
    expect(resp.error?.code).toBe(-32603);
    expect(resp.error?.message).toBe("boom");
    await client.exit();
  });

  it("replies with method-not-found for unknown server-initiated requests", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // The default onIncomingRequest hook (installed in the constructor) only
    // knows `permission/request`; everything else round-trips as -32601 so a
    // misbehaving server doesn't hang waiting on us.
    t.feed({
      jsonrpc: "2.0",
      id: -3,
      method: "some/unknown",
      params: {},
    });
    await new Promise((r) => setTimeout(r, 10));
    const resp = decode(t.sent[0]!);
    expect(resp.id).toBe(-3);
    expect(resp.error?.code).toBe(-32601);
    await client.exit();
  });

  it("skips unparseable inbound payloads without crashing", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // Garbage frame:
    t.queue.push(Buffer.from("not json"));
    // Followed by a real response that should still resolve.
    t.feed({ jsonrpc: "2.0", id: 1, result: null });
    await client.shutdown();
    await client.exit();
  });

  it("exit is idempotent / safe to call after stop", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    await client.exit();
    // Second call must not throw.
    await client.exit();
  });

  // Ensure that the BridgeError export is wired up for downstream consumers
  // that catch errors from sendRequest.
  it("BridgeError surface remains stable", () => {
    const e = new BridgeError("x", -32601);
    expect(e).toBeInstanceOf(BridgeError);
    expect(e.code).toBe(-32601);
  });
});

describe("BridgeClient sessions + tools", () => {
  it("sessionCreate sends session.create with empty payload by default", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: { id: "abc", created_at: "2026-01-01T00:00:00" },
    });
    const s = await client.sessionCreate();
    expect(s.id).toBe("abc");
    expect(s.created_at).toBe("2026-01-01T00:00:00");
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("session.create");
    // No optional fields supplied — params is an empty object, not `null`.
    expect(sent.params).toEqual({});
    await client.exit();
  });

  it("sessionCreate forwards sessionId/tenantId/userId in snake_case", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: { id: "sess-1", created_at: "2026-01-01T00:00:00" },
    });
    await client.sessionCreate({
      sessionId: "sess-1",
      tenantId: "acme",
      userId: "u-42",
    });
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("session.create");
    expect(sent.params).toEqual({
      session_id: "sess-1",
      tenant_id: "acme",
      user_id: "u-42",
    });
    await client.exit();
  });

  it("sessionCreate omits undefined optional fields", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: { id: "x", created_at: "2026-01-01T00:00:00" },
    });
    await client.sessionCreate({ tenantId: "acme" });
    const sent = decode(t.sent[0]!);
    expect(sent.params).toEqual({ tenant_id: "acme" });
    await client.exit();
  });

  it("sessionList sends session.list and returns the array", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const entries = [
      {
        id: "s1",
        created_at: "2026-01-01T00:00:00",
        message_count: 3,
        last_message_at: "2026-01-01T00:01:00",
      },
      {
        id: "s2",
        created_at: "2026-01-02T00:00:00",
        message_count: 0,
        last_message_at: null,
      },
    ];
    t.feed({ jsonrpc: "2.0", id: 1, result: entries });
    const out = await client.sessionList();
    expect(out).toEqual(entries);
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("session.list");
    // No params should be sent on the wire (sendRequest passes undefined).
    expect(sent.params).toBeUndefined();
    await client.exit();
  });

  it("sessionLoad sends session.load with session_id and returns messages", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const result = {
      id: "sess-1",
      created_at: "2026-01-01T00:00:00",
      messages: [
        { role: "user", content: "hi" },
        { role: "assistant", content: "hello" },
      ],
    };
    t.feed({ jsonrpc: "2.0", id: 1, result });
    const loaded = await client.sessionLoad("sess-1");
    expect(loaded.id).toBe("sess-1");
    expect(loaded.messages).toHaveLength(2);
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("session.load");
    expect(sent.params).toEqual({ session_id: "sess-1" });
    await client.exit();
  });

  it("toolsList sends tools.list and returns the array", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const tools = [
      {
        name: "bash",
        description: "Run a shell command",
        input_schema: { type: "object" },
      },
    ];
    t.feed({ jsonrpc: "2.0", id: 1, result: tools });
    const out = await client.toolsList();
    expect(out).toEqual(tools);
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("tools.list");
    expect(sent.params).toBeUndefined();
    await client.exit();
  });

  it("session methods propagate BridgeError on error responses", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32004, message: "session not found" },
    });
    await expect(client.sessionLoad("missing")).rejects.toMatchObject({
      name: "BridgeError",
      code: -32004,
      message: "session not found",
    });
    await client.exit();
  });
});

describe("BridgeClient sendMessage handle", () => {
  /**
   * Tick the event loop a few times so the read loop can pump pending
   * inbound frames AND any handler-triggered writes settle on `t.sent`.
   */
  const flush = async (n = 3): Promise<void> => {
    for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r));
  };

  const userMsg = {
    role: "user",
    content: [{ type: "text", text: "hi" }],
  };

  it("sends session.send_message with the expected payload", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    expect(handle.requestId).toBe(1);
    const sent = decode(t.sent[0]!);
    expect(sent.method).toBe("session.send_message");
    expect(sent.id).toBe(1);
    expect(sent.params).toEqual({ session_id: "sess-1", message: userMsg });
    // Resolve the inflight request so exit() can shut down cleanly.
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: { stopped_reason: "completed" },
    });
    await handle.done;
    await client.exit();
  });

  it("routes stream/event notifications to onEvent handlers by request_id", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    const events: unknown[] = [];
    handle.onEvent((e) => events.push(e));
    t.feed({
      jsonrpc: "2.0",
      method: "stream/event",
      params: { request_id: handle.requestId, event: { type: "text_delta", delta: "he" } },
    });
    t.feed({
      jsonrpc: "2.0",
      method: "stream/event",
      params: { request_id: handle.requestId, event: { type: "text_delta", delta: "llo" } },
    });
    await flush();
    expect(events).toEqual([
      { type: "text_delta", delta: "he" },
      { type: "text_delta", delta: "llo" },
    ]);
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      result: { stopped_reason: "completed" },
    });
    await expect(handle.done).resolves.toEqual({ stopped_reason: "completed" });
    await client.exit();
  });

  it("ignores stream/event notifications for unknown request ids", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    const events: unknown[] = [];
    handle.onEvent((e) => events.push(e));
    // Stray event targeted at some other inflight request — must not leak.
    t.feed({
      jsonrpc: "2.0",
      method: "stream/event",
      params: { request_id: 999, event: { type: "x" } },
    });
    await flush();
    expect(events).toEqual([]);
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      result: { stopped_reason: "completed" },
    });
    await handle.done;
    await client.exit();
  });

  it("invokes the permission handler and writes the decision back", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    const seen: Array<{ tool: string }> = [];
    handle.onPermissionRequest((req) => {
      seen.push({ tool: req.tool });
      return Promise.resolve({ decision: "allow" });
    });
    // Server-initiated permission/request.
    t.feed({
      jsonrpc: "2.0",
      id: -10,
      method: "permission/request",
      params: {
        tool: "bash",
        tool_args: { cmd: "ls" },
        session_id: "sess-1",
        call_id: "c1",
      },
    });
    await flush();
    expect(seen).toEqual([{ tool: "bash" }]);
    // The reply is the second frame (the first being session.send_message).
    expect(t.sent).toHaveLength(2);
    const reply = decode(t.sent[1]!);
    expect(reply.id).toBe(-10);
    expect(reply.result).toEqual({ decision: "allow" });
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      result: { stopped_reason: "completed" },
    });
    await handle.done;
    await client.exit();
  });

  it("defaults permission decisions to deny when no handler is registered", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    // Note: no onPermissionRequest registered.
    t.feed({
      jsonrpc: "2.0",
      id: -11,
      method: "permission/request",
      params: {
        tool: "bash",
        tool_args: {},
        session_id: "sess-1",
        call_id: "c1",
      },
    });
    await flush();
    const reply = decode(t.sent[1]!);
    expect(reply.id).toBe(-11);
    expect(reply.result).toEqual({ decision: "deny" });
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      result: { stopped_reason: "completed" },
    });
    await handle.done;
    await client.exit();
  });

  it("cancel() emits a $/cancelRequest notification carrying the requestId", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    await handle.cancel();
    const cancelFrame = decode(t.sent[t.sent.length - 1]!);
    expect(cancelFrame.method).toBe("$/cancelRequest");
    expect("id" in cancelFrame).toBe(false); // notification — no id at root
    expect(cancelFrame.params).toEqual({ id: handle.requestId });
    // The server's response then surfaces as BridgeCancelled via `done`.
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      error: { code: -32002, message: "request cancelled" },
    });
    await expect(handle.done).rejects.toBeInstanceOf(BridgeCancelled);
    await client.exit();
  });

  it("rejects done with BridgeError on non-cancellation error responses", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    t.feed({
      jsonrpc: "2.0",
      id: handle.requestId,
      error: { code: -32603, message: "boom" },
    });
    await expect(handle.done).rejects.toMatchObject({
      name: "BridgeError",
      code: -32603,
      message: "boom",
    });
    await client.exit();
  });

  it("rejects done with BridgeDisconnected on transport EOF mid-flight", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    const handle = client.sendMessage("sess-1", userMsg);
    await flush();
    t.signalEof();
    await expect(handle.done).rejects.toBeInstanceOf(BridgeDisconnected);
  });

  it("uses sequential request ids that interleave with other requests", async () => {
    const t = new FakeTransport();
    const client = makeClient(t);
    await client.start();
    // First, a session.create (id=1).
    t.feed({
      jsonrpc: "2.0",
      id: 1,
      result: { id: "sess-1", created_at: "2026-01-01T00:00:00" },
    });
    await client.sessionCreate();
    // Then sendMessage should claim id=2.
    const handle = client.sendMessage("sess-1", userMsg);
    expect(handle.requestId).toBe(2);
    t.feed({
      jsonrpc: "2.0",
      id: 2,
      result: { stopped_reason: "completed" },
    });
    await handle.done;
    await client.exit();
  });
});
