/**
 * BridgeClient — JSON-RPC 2.0 client for the meta-harney bridge.
 *
 * Responsibilities (Task 5 scope):
 *   - Lifecycle: start / initialize / shutdown / exit, mirroring the
 *     Phase 10 Python server's contract.
 *   - Read loop: pumps incoming messages from the transport and routes
 *     responses → pending request table, notifications → onNotification
 *     hook, server-initiated requests → onIncomingRequest hook.
 *   - Pending request table: correlates outbound requests with inbound
 *     responses by JSON-RPC id and rejects everything still in flight
 *     when the transport disconnects.
 *
 * Tasks 6+ wire `onNotification` / `onIncomingRequest` to higher-level
 * features (streaming events, permission/request, telemetry). This file
 * deliberately stops at the plumbing.
 */

import type { ChildProcessTransport } from "./transport.js";
import {
  encodeRequest,
  encodeNotification,
  encodeResponse,
  encodeError,
  parseIncoming,
  type IncomingMessage,
} from "./protocol.js";
import { BridgeError, BridgeDisconnected } from "./errors.js";

export interface BridgeClientOptions {
  transport: ChildProcessTransport;
}

export interface InitializeParams {
  clientInfo: { name: string; version: string };
  protocolVersion?: number;
  capabilities?: Record<string, unknown>;
}

export interface InitializeResult {
  server_info: { name: string; version: string };
  protocol_version: number;
  capabilities: Record<string, unknown>;
}

export interface SessionCreateParams {
  sessionId?: string;
  tenantId?: string;
  userId?: string;
}

export interface SessionSummary {
  id: string;
  created_at: string;
}

export interface SessionListEntry {
  id: string;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
}

export interface SessionLoadResult {
  id: string;
  created_at: string;
  messages: unknown[];
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: unknown;
}

interface PendingResolver {
  resolve: (v: unknown) => void;
  reject: (e: Error) => void;
}

interface IncomingRequest {
  id: number | string;
  method: string;
  params: unknown;
}

export class BridgeClient {
  private readonly transport: ChildProcessTransport;
  private nextId = 1;
  private readonly pending = new Map<number | string, PendingResolver>();
  private readLoopStarted = false;
  private readLoopDone: Promise<void> | null = null;
  private exited = false;

  /**
   * Hooks set by higher-level features (Task 6+ wires these). They are
   * `protected` so subclasses or the same module can install them; tests
   * reach in via a typed cast.
   */
  protected onNotification: ((method: string, params: unknown) => void) | null =
    null;
  protected onIncomingRequest:
    | ((req: IncomingRequest) => Promise<unknown>)
    | null = null;

  constructor(options: BridgeClientOptions) {
    this.transport = options.transport;
  }

  /** Spawn the transport and start the read loop. */
  async start(): Promise<void> {
    await this.transport.start();
    // Fire the read loop in the background. We hold onto the promise so
    // exit() can await its termination for orderly shutdown.
    this.readLoopDone = this.readLoop();
  }

  /**
   * Send a JSON-RPC 2.0 request and await its response. The returned
   * promise rejects with `BridgeError` if the peer returns an error
   * response, or `BridgeDisconnected` if the transport closes first.
   */
  protected async sendRequest<T>(method: string, params?: unknown): Promise<T> {
    const id = this.nextId++;
    const promise = new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: resolve as (v: unknown) => void,
        reject,
      });
    });
    await this.transport.write(encodeRequest(id, method, params));
    return await promise;
  }

  /** Send a JSON-RPC 2.0 notification (fire-and-forget). */
  protected async sendNotification(
    method: string,
    params?: unknown,
  ): Promise<void> {
    await this.transport.write(encodeNotification(method, params));
  }

  /** Reply to a server-initiated request with a result. */
  protected async respondTo(
    id: number | string,
    result: unknown,
  ): Promise<void> {
    await this.transport.write(encodeResponse(id, result));
  }

  /** Reply to a server-initiated request with an error. */
  protected async respondError(
    id: number | string,
    error: { code: number; message: string; data?: unknown },
  ): Promise<void> {
    await this.transport.write(encodeError(id, error));
  }

  // -------------------------------------------------------------------------
  // Lifecycle methods
  // -------------------------------------------------------------------------

  async initialize(params: InitializeParams): Promise<InitializeResult> {
    return await this.sendRequest<InitializeResult>("initialize", {
      client_info: params.clientInfo,
      protocol_version: params.protocolVersion ?? 1,
      capabilities: params.capabilities ?? {},
    });
  }

  async shutdown(): Promise<void> {
    await this.sendRequest<null>("shutdown");
  }

  /**
   * Mark the client as closing, send the `exit` notification, stop the
   * transport, and await the read loop's termination. Idempotent: calling
   * exit() more than once is a no-op.
   */
  async exit(): Promise<void> {
    if (this.exited) return;
    this.exited = true;
    // Best-effort: if the transport is already dead, don't blow up on write.
    try {
      if (this.transport.isAlive()) {
        await this.sendNotification("exit");
      }
    } catch {
      // Swallow — the server may have closed before our notification landed.
    }
    await this.transport.stop();
    if (this.readLoopDone !== null) {
      // Wait for the loop to settle so the process can exit cleanly.
      await this.readLoopDone;
    }
  }

  // -------------------------------------------------------------------------
  // Session methods (Phase 11 Task 6)
  // -------------------------------------------------------------------------

  /**
   * Create a new session via `session.create`. All parameters are optional:
   *   - sessionId: pre-allocate a specific id; server generates one if absent.
   *   - tenantId / userId: tenancy metadata persisted alongside the session.
   *
   * Note: only fields the caller explicitly provided are serialized — we omit
   * `undefined` keys so the server sees a clean payload matching its
   * Optional[str] schema rather than `null`.
   */
  async sessionCreate(params?: SessionCreateParams): Promise<SessionSummary> {
    const payload: Record<string, string> = {};
    if (params?.sessionId !== undefined) payload.session_id = params.sessionId;
    if (params?.tenantId !== undefined) payload.tenant_id = params.tenantId;
    if (params?.userId !== undefined) payload.user_id = params.userId;
    return await this.sendRequest<SessionSummary>("session.create", payload);
  }

  /** Enumerate sessions via `session.list`. */
  async sessionList(): Promise<SessionListEntry[]> {
    return await this.sendRequest<SessionListEntry[]>("session.list");
  }

  /** Load a session (with its message history) via `session.load`. */
  async sessionLoad(sessionId: string): Promise<SessionLoadResult> {
    return await this.sendRequest<SessionLoadResult>("session.load", {
      session_id: sessionId,
    });
  }

  // -------------------------------------------------------------------------
  // Tools methods (Phase 11 Task 6)
  // -------------------------------------------------------------------------

  /** Enumerate runtime tools via `tools.list`. */
  async toolsList(): Promise<ToolSpec[]> {
    return await this.sendRequest<ToolSpec[]>("tools.list");
  }

  // -------------------------------------------------------------------------
  // Read loop
  // -------------------------------------------------------------------------

  /**
   * Pump messages from the transport. Terminates when `read()` returns
   * null (clean EOF) or throws — at which point all still-pending requests
   * are rejected with `BridgeDisconnected` (or the read error).
   *
   * Note: cleaner termination semantics than the plan's draft. We loop
   * until the transport signals EOF/error and let `exit()` await this
   * loop's settlement via `readLoopDone`.
   */
  private async readLoop(): Promise<void> {
    if (this.readLoopStarted) return;
    this.readLoopStarted = true;

    for (;;) {
      let raw: Buffer | null;
      try {
        raw = await this.transport.read();
      } catch (err) {
        this.failAllPending(err as Error);
        return;
      }
      if (raw === null) {
        this.failAllPending(new BridgeDisconnected());
        return;
      }

      let msg: IncomingMessage;
      try {
        msg = parseIncoming(raw);
      } catch {
        // Malformed frame — drop it and keep pumping. (A noisier transport
        // could log here; we stay silent for now.)
        continue;
      }

      this.dispatch(msg);
    }
  }

  /** Route a single decoded message to the right handler. */
  private dispatch(msg: IncomingMessage): void {
    if (msg.kind === "response") {
      this.handleResponse(msg.id, msg.result, msg.error);
    } else if (msg.kind === "notification") {
      // Hook may be null until a higher-level feature wires it.
      const hook = this.onNotification;
      if (hook !== null) {
        try {
          hook(msg.method, msg.params);
        } catch {
          // Notification handlers must not crash the read loop.
        }
      }
    } else {
      // kind === "request" — server-initiated.
      this.handleIncomingRequest({
        id: msg.id,
        method: msg.method,
        params: msg.params,
      });
    }
  }

  private handleResponse(
    id: number | string | null,
    result: unknown,
    error: { code: number; message: string; data?: unknown } | undefined,
  ): void {
    if (id === null) return; // Response to an unrecognized request — ignore.
    const pending = this.pending.get(id);
    if (pending === undefined) return; // Unknown id; nothing to resolve.
    this.pending.delete(id);
    if (error !== undefined) {
      pending.reject(new BridgeError(error.message, error.code, error.data));
    } else {
      pending.resolve(result);
    }
  }

  /**
   * Dispatch a server-initiated request to the configured handler and
   * write its result (or an error) back to the transport. If no handler
   * is configured we reply with method-not-found so the server doesn't
   * hang waiting on us.
   */
  private handleIncomingRequest(req: IncomingRequest): void {
    const handler = this.onIncomingRequest;
    if (handler === null) {
      void this.respondError(req.id, {
        code: -32601,
        message: `no handler for server-initiated request: ${req.method}`,
      }).catch(() => {
        /* transport may be closing; swallow */
      });
      return;
    }
    // Fire the handler once (the plan had a duplicated call here — fixed).
    handler(req)
      .then((result) => this.respondTo(req.id, result))
      .catch((err: Error) =>
        this.respondError(req.id, {
          code: -32603,
          message: err.message,
        }),
      )
      .catch(() => {
        // Either the handler chain rejected after we already attempted a
        // respond, or the transport closed mid-write. Either way, don't
        // crash the read loop.
      });
  }

  private failAllPending(err: Error): void {
    for (const [, p] of this.pending) p.reject(err);
    this.pending.clear();
  }
}
