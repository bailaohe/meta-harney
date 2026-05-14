/**
 * BridgeClient — JSON-RPC 2.0 client for the meta-harney bridge.
 *
 * Responsibilities:
 *   - Lifecycle: start / initialize / shutdown / exit, mirroring the
 *     Phase 10 Python server's contract.
 *   - Read loop: pumps incoming messages from the transport and routes
 *     responses → pending request table, notifications → onNotification
 *     hook, server-initiated requests → onIncomingRequest hook.
 *   - Pending request table: correlates outbound requests with inbound
 *     responses by JSON-RPC id and rejects everything still in flight
 *     when the transport disconnects.
 *   - SendMessage handle (Task 7): `sendMessage()` returns a handle that
 *     surfaces `stream/event` notifications, dispatches server-initiated
 *     `permission/request`s to a user-supplied handler, and supports
 *     `$/cancelRequest` cancellation.
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
import { BridgeError, BridgeCancelled, BridgeDisconnected } from "./errors.js";

export interface BridgeClientOptions {
  transport: ChildProcessTransport;
}

export interface InitializeParams {
  clientInfo: { name: string; version: string };
  protocolVersion?: number;
  capabilities?: Record<string, unknown>;
}

/**
 * Optional metadata about the runtime the server wired up — typically the
 * smart-picked provider/model when the host doesn't pin them explicitly.
 * Both fields are optional so older servers that omit the block, or hosts
 * that only know one of the two, still type-check.
 */
export interface RuntimeInfo {
  provider?: string;
  model?: string;
}

export interface InitializeResult {
  server_info: { name: string; version: string };
  protocol_version: number;
  capabilities: Record<string, unknown>;
  runtime_info?: RuntimeInfo;
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

// ---------------------------------------------------------------------------
// Telemetry types (Phase 11 Task 8)
// ---------------------------------------------------------------------------

/**
 * Payload shape of a `telemetry/event` notification, as emitted by the
 * bridge's `BridgeTraceSink`. `event_type` mirrors the underlying
 * `TraceEvent.kind` (e.g. "turn_started", "tool_call_completed"); `payload`
 * is the model-dumped TraceEvent (shape is event-kind-dependent and stays
 * opaque at this layer so we don't lock the client to a specific schema).
 */
export interface TelemetryEvent {
  event_type: string;
  payload: unknown;
}

/** Result of `telemetry/subscribe` — server echoes the requested state. */
export interface TelemetrySubscribeResult {
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// SendMessage types (Phase 11 Task 7)
// ---------------------------------------------------------------------------

/**
 * Wire shape for a chat message accepted by `session.send_message`. The
 * bridge accepts a Pydantic `Message` so this stays intentionally loose;
 * higher-level callers (oh-tui) supply a typed structure.
 */
export interface ChatMessage {
  role: string;
  content: unknown[];
}

/** Outcome of a `permission/request` reply expected by the bridge. */
export type PermissionDecision = "allow" | "deny" | "allow_always";

export interface PermissionRequest {
  tool: string;
  tool_args: unknown;
  session_id: string;
  call_id: string;
}

export interface PermissionResponse {
  decision: PermissionDecision;
}

/** Streaming event payload — opaque to the client (runtime-defined shape). */
export type StreamEvent = unknown;

/** Final response shape of `session.send_message`. */
export interface SendMessageResult {
  stopped_reason: string;
}

/**
 * Handle returned by `BridgeClient.sendMessage()`. Wraps a single in-flight
 * `session.send_message` request:
 *   - `onEvent(fn)` registers an event sink for `stream/event` notifications.
 *   - `onPermissionRequest(fn)` installs the answer routine for incoming
 *     `permission/request` requests targeting this send.
 *   - `cancel()` fires `$/cancelRequest`; the matching `done` promise then
 *     rejects with `BridgeCancelled` once the bridge confirms.
 *   - `done` resolves to the final `{stopped_reason}` response, or rejects
 *     with `BridgeError` / `BridgeCancelled` / `BridgeDisconnected`.
 */
export interface SendMessageHandle {
  readonly requestId: number;
  readonly done: Promise<SendMessageResult>;
  onEvent(handler: (event: StreamEvent) => void): void;
  onPermissionRequest(
    handler: (req: PermissionRequest) => Promise<PermissionResponse>,
  ): void;
  cancel(): Promise<void>;
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

/**
 * Internal handle implementation. Not exported — callers get the
 * `SendMessageHandle` interface back from `BridgeClient.sendMessage()`.
 *
 * Underscore-prefixed methods are package-internal hooks fired by the
 * surrounding `BridgeClient` instance.
 */
class SendMessageHandleImpl implements SendMessageHandle {
  public readonly requestId: number;
  public readonly done: Promise<SendMessageResult>;
  private readonly client: BridgeClient;
  private readonly eventHandlers: Array<(e: StreamEvent) => void> = [];
  private permissionHandler:
    | ((req: PermissionRequest) => Promise<PermissionResponse>)
    | null = null;

  constructor(
    requestId: number,
    done: Promise<SendMessageResult>,
    client: BridgeClient,
  ) {
    this.requestId = requestId;
    this.done = done;
    this.client = client;
  }

  onEvent(handler: (event: StreamEvent) => void): void {
    this.eventHandlers.push(handler);
  }

  onPermissionRequest(
    handler: (req: PermissionRequest) => Promise<PermissionResponse>,
  ): void {
    this.permissionHandler = handler;
  }

  async cancel(): Promise<void> {
    await this.client._sendCancel(this.requestId);
  }

  /** Fire `stream/event` payloads at every registered handler. */
  _emit(event: StreamEvent): void {
    for (const h of this.eventHandlers) {
      try {
        h(event);
      } catch {
        // Event handlers must not crash the read loop.
      }
    }
  }

  /**
   * Dispatch a server-initiated `permission/request` to the user handler.
   * Defaults to `deny` when no handler is installed so the bridge doesn't
   * hang waiting on the client.
   */
  async _handlePermission(req: PermissionRequest): Promise<PermissionResponse> {
    if (this.permissionHandler === null) return { decision: "deny" };
    return await this.permissionHandler(req);
  }
}

export class BridgeClient {
  private readonly transport: ChildProcessTransport;
  private nextId = 1;
  private readonly pending = new Map<number | string, PendingResolver>();
  /**
   * Active send_message handles keyed by JSON-RPC request id. Populated by
   * `sendMessage()` and cleared when the corresponding response (success,
   * error, or cancel) lands.
   */
  private readonly inflight = new Map<number, SendMessageHandleImpl>();
  /**
   * Registered telemetry sinks. Populated by `onTelemetry()`; fired by the
   * default `onNotification` hook on every inbound `telemetry/event`. Kept
   * as a list (rather than a single handler) because multiple consumers may
   * want to observe the stream — e.g. a status bar + a debug log + an
   * external aggregator — without trampling on each other.
   */
  private readonly telemetryHandlers: Array<(ev: TelemetryEvent) => void> = [];
  private readLoopStarted = false;
  private readLoopDone: Promise<void> | null = null;
  private exited = false;

  /**
   * Notification hook. Installed by the constructor with a default that
   * routes `stream/event` to the matching in-flight handle. Tests (and
   * higher-level features like telemetry, Task 8) may overwrite this.
   */
  protected onNotification: ((method: string, params: unknown) => void) | null =
    null;
  /**
   * Server-initiated request hook. Installed by the constructor with a
   * default that routes `permission/request` to the most recently active
   * handle (v1 routing — see Task 7 design notes).
   */
  protected onIncomingRequest:
    | ((req: IncomingRequest) => Promise<unknown>)
    | null = null;

  constructor(options: BridgeClientOptions) {
    this.transport = options.transport;
    this.installDefaultHooks();
  }

  /**
   * Wire the default `onNotification` / `onIncomingRequest` handlers so a
   * freshly constructed client correctly demuxes streaming events and
   * permission requests without any extra setup. Higher-level features
   * (telemetry) and tests can still overwrite the protected fields.
   */
  private installDefaultHooks(): void {
    this.onNotification = (method, params) => {
      if (method === "stream/event") {
        const p = params as { request_id?: unknown; event?: unknown } | null;
        if (p === null || typeof p !== "object") return;
        const rid = p.request_id;
        if (typeof rid !== "number") return;
        const handle = this.inflight.get(rid);
        if (handle !== undefined) handle._emit(p.event);
      } else if (method === "telemetry/event") {
        // Validate the shape lightly so a malformed payload from a buggy
        // server doesn't crash subscribers. We trust `event_type` to be a
        // string (per the bridge's `BridgeTraceSink` contract) but keep
        // `payload` opaque.
        if (params === null || typeof params !== "object") return;
        const p = params as { event_type?: unknown; payload?: unknown };
        if (typeof p.event_type !== "string") return;
        const ev: TelemetryEvent = {
          event_type: p.event_type,
          payload: p.payload,
        };
        for (const h of this.telemetryHandlers) {
          try {
            h(ev);
          } catch {
            // Handlers must not crash the read loop.
          }
        }
      }
    };

    this.onIncomingRequest = (req) => {
      if (req.method === "permission/request") {
        // The bridge does not currently include the originating request_id in
        // the permission payload, so we route to the most recently registered
        // handle. With a single in-flight send_message this is exact; with
        // multiple, the v1 contract documents this as the supported behavior.
        const handles = Array.from(this.inflight.values());
        const handle = handles[handles.length - 1];
        if (handle === undefined) {
          return Promise.resolve({ decision: "deny" as PermissionDecision });
        }
        return handle._handlePermission(req.params as PermissionRequest);
      }
      return Promise.reject(
        new BridgeError(
          `unknown server-initiated request: ${req.method}`,
          -32601,
        ),
      );
    };
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
  // SendMessage (Phase 11 Task 7)
  // -------------------------------------------------------------------------

  /**
   * Issue a `session.send_message` request and return a handle for the
   * resulting interactive flow.
   *
   * Behavior:
   *   - The handle's `done` promise resolves with the final
   *     `{stopped_reason}` response or rejects with `BridgeError`
   *     (server error), `BridgeCancelled` (code -32002 cancellation), or
   *     `BridgeDisconnected` (transport closed mid-flight).
   *   - Streaming `stream/event` notifications are routed to handlers
   *     registered via `handle.onEvent(...)`.
   *   - Server-initiated `permission/request` calls are routed to the
   *     handler registered via `handle.onPermissionRequest(...)`.
   *   - `handle.cancel()` sends `$/cancelRequest` (LSP-style notification);
   *     the bridge replies to the original send_message with `-32002`
   *     which surfaces as `BridgeCancelled`.
   *
   * Note: returns synchronously (not async) — the wire-write happens
   * eagerly but the caller doesn't need to await it before attaching
   * handlers. Write failures are propagated through `done`.
   */
  sendMessage(sessionId: string, message: ChatMessage): SendMessageHandle {
    const requestId = this.nextId++;
    const done = new Promise<SendMessageResult>((resolve, reject) => {
      this.pending.set(requestId, {
        resolve: resolve as (v: unknown) => void,
        reject,
      });
    });
    const handle = new SendMessageHandleImpl(requestId, done, this);
    this.inflight.set(requestId, handle);

    // Fire the wire request. If the write rejects (e.g., transport already
    // dead), surface that through `done` so the caller's await fails cleanly
    // rather than leaving an unhandled rejection.
    this.transport
      .write(
        encodeRequest(requestId, "session.send_message", {
          session_id: sessionId,
          message,
        }),
      )
      .catch((err: Error) => {
        const pending = this.pending.get(requestId);
        if (pending !== undefined) {
          this.pending.delete(requestId);
          this.inflight.delete(requestId);
          pending.reject(err);
        }
      });

    return handle;
  }

  /**
   * Internal: send `$/cancelRequest` for the given send_message id. The
   * server replies to the original send_message with a `-32002` error
   * which surfaces as `BridgeCancelled` through the handle's `done`.
   */
  async _sendCancel(requestId: number): Promise<void> {
    await this.sendNotification("$/cancelRequest", { id: requestId });
  }

  // -------------------------------------------------------------------------
  // Telemetry (Phase 11 Task 8)
  // -------------------------------------------------------------------------

  /**
   * Toggle bridge-side forwarding of trace events as `telemetry/event`
   * notifications. The server echoes the resolved state back so the caller
   * can drive UI affordances (e.g. a "telemetry on" status indicator) off
   * of the authoritative response rather than guessing.
   *
   * Note: subscription is independent of `onTelemetry` — local handlers
   * fire whenever the bridge sends an event regardless of who toggled it,
   * but the bridge won't emit anything until at least one client calls
   * `telemetrySubscribe(true)`.
   */
  async telemetrySubscribe(
    enabled: boolean,
  ): Promise<TelemetrySubscribeResult> {
    return await this.sendRequest<TelemetrySubscribeResult>(
      "telemetry/subscribe",
      { enabled },
    );
  }

  /**
   * Register a sink for `telemetry/event` notifications. Multiple sinks
   * are supported — each is invoked in registration order. Handlers must
   * not throw; any thrown error is swallowed so a single buggy subscriber
   * can't break the read loop or starve other subscribers.
   */
  onTelemetry(handler: (event: TelemetryEvent) => void): void {
    this.telemetryHandlers.push(handler);
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
    // send_message handles live alongside `pending`; the response we just
    // observed (success OR error) ends the in-flight stream.
    if (typeof id === "number") this.inflight.delete(id);
    if (error !== undefined) {
      // -32002 is the LSP-style cancellation code. Surface it as a typed
      // `BridgeCancelled` so callers can distinguish "user pressed Ctrl+C"
      // from arbitrary server errors.
      const err =
        error.code === -32002
          ? new BridgeCancelled(error.message)
          : new BridgeError(error.message, error.code, error.data);
      pending.reject(err);
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
      .catch((err: Error) => {
        // Preserve the structured JSON-RPC code when the handler rejected
        // with a `BridgeError` (e.g., the default hook signaling -32601 for
        // unknown server-initiated methods); otherwise fall back to the
        // generic internal-error code.
        const isBridgeErr = err instanceof BridgeError;
        return this.respondError(req.id, {
          code: isBridgeErr ? err.code : -32603,
          message: err.message,
          ...(isBridgeErr && err.data !== undefined ? { data: err.data } : {}),
        });
      })
      .catch(() => {
        // Either the handler chain rejected after we already attempted a
        // respond, or the transport closed mid-write. Either way, don't
        // crash the read loop.
      });
  }

  private failAllPending(err: Error): void {
    for (const [, p] of this.pending) p.reject(err);
    this.pending.clear();
    // Any handle still in-flight is now defunct — its `done` promise was
    // already rejected via the matching `pending` entry above.
    this.inflight.clear();
  }
}
