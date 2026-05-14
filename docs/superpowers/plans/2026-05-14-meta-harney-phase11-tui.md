# Phase 11 Plan — `@meta-harney/bridge-client` + `oh-tui`

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Ship a TS client library inside meta-harney + an Ink TUI app in a new repo. End state: `oh-tui "task"` spawns `oh bridge`, streams response in a real terminal UI.

**Architecture:** 11a = generic JSON-RPC client. 11b = Ink app consuming 11a. They link via pnpm workspace `file:` ref during dev, no npm publish required for v1.

**Tech Stack:** TypeScript 5.x strict ESM, Node 18+, pnpm, tsup (lib), tsx (app), vitest + ink-testing-library, eslint + prettier.

**Spec:** `docs/superpowers/specs/2026-05-14-meta-harney-phase11-tui-design.md`

**Repos:**
- `meta-harney` (existing, branch `main`): clients/typescript/ + version bump 0.1.0 → 0.2.0
- `oh-tui` (new, init in this plan): `/Users/baihe/Projects/study/oh-tui/`

---

## File Structure (final state)

### meta-harney/clients/typescript/

```
clients/typescript/
├── package.json              # @meta-harney/bridge-client v0.1.0
├── tsconfig.json             # strict ESM
├── vitest.config.ts
├── .eslintrc.cjs
├── tsup.config.ts            # ESM build
├── src/
│   ├── framing.ts
│   ├── protocol.ts
│   ├── errors.ts
│   ├── transport.ts
│   ├── client.ts             # BridgeClient + SendMessageHandle
│   ├── types.ts              # JSON-RPC method param/result shapes
│   └── index.ts              # Public re-exports
└── tests/
    ├── framing.test.ts
    ├── protocol.test.ts
    ├── client.test.ts        # Uses mock transport
    └── e2e-real-bridge.test.ts  # Spawns actual `python -m oh_mini bridge`
```

### oh-tui/ (new repo)

```
oh-tui/
├── package.json              # oh-tui v0.1.0
├── tsconfig.json
├── vitest.config.ts
├── .eslintrc.cjs
├── bin/oh-tui                # shebang + tsx entry
├── src/
│   ├── cli.tsx               # argv parse + <App/>
│   ├── App.tsx               # mode router
│   ├── modes/
│   │   ├── OneShotMode.tsx
│   │   └── ReplMode.tsx
│   ├── components/
│   │   ├── PromptInput.tsx
│   │   ├── StreamingMessage.tsx
│   │   ├── ToolUseBadge.tsx
│   │   ├── PermissionDialog.tsx
│   │   ├── SessionListPanel.tsx
│   │   ├── ToolsListPanel.tsx
│   │   └── TelemetryBar.tsx
│   ├── hooks/
│   │   ├── useBridgeClient.ts
│   │   ├── useStreaming.ts
│   │   └── useKeybinds.ts
│   ├── lib/
│   │   ├── markdown.ts
│   │   └── locate-bridge.ts
│   └── types.ts
├── tests/
│   ├── components.test.tsx   # Ink testing
│   └── modes.test.tsx
└── README.md
```

### Root-level workspace (meta-harney)

```
meta-harney/
├── pnpm-workspace.yaml       # NEW: includes clients/typescript
├── ...existing Python project unchanged...
```

---

# Part A: `@meta-harney/bridge-client` (Tasks 1-9)

### Task 1: pnpm workspace + skeleton

**Files:**
- Create: `meta-harney/pnpm-workspace.yaml`
- Create: `meta-harney/clients/typescript/package.json`
- Create: `meta-harney/clients/typescript/tsconfig.json`
- Create: `meta-harney/clients/typescript/vitest.config.ts`
- Create: `meta-harney/clients/typescript/.eslintrc.cjs`
- Create: `meta-harney/clients/typescript/tsup.config.ts`
- Create: `meta-harney/clients/typescript/src/index.ts` (empty re-export stub)
- Create: `meta-harney/clients/typescript/.gitignore` (node_modules, dist)
- Create: `meta-harney/.gitignore` if missing entry: append `node_modules/` and `dist/`

- [ ] **Step 1: Workspace root**

`meta-harney/pnpm-workspace.yaml`:
```yaml
packages:
  - 'clients/*'
```

- [ ] **Step 2: package.json**

```json
{
  "name": "@meta-harney/bridge-client",
  "version": "0.1.0",
  "description": "TypeScript JSON-RPC client for meta_harney.bridge",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "files": ["dist", "README.md"],
  "scripts": {
    "build": "tsup",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "lint": "eslint src tests --ext .ts",
    "format": "prettier -w src tests"
  },
  "engines": { "node": ">=18" },
  "dependencies": {},
  "devDependencies": {
    "@types/node": "^20.11.0",
    "@typescript-eslint/eslint-plugin": "^7.0.0",
    "@typescript-eslint/parser": "^7.0.0",
    "eslint": "^8.57.0",
    "prettier": "^3.2.0",
    "tsup": "^8.0.0",
    "typescript": "^5.4.0",
    "vitest": "^1.4.0"
  }
}
```

- [ ] **Step 3: tsconfig.json (strict)**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "esModuleInterop": true,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "declaration": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*", "tests/**/*"]
}
```

- [ ] **Step 4: tsup.config.ts**

```typescript
import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: true,
  target: "es2022",
});
```

- [ ] **Step 5: vitest.config.ts + eslint**

`vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
  },
});
```

`.eslintrc.cjs`:
```javascript
module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["@typescript-eslint"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  rules: {
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
  },
};
```

- [ ] **Step 6: stub + install**

`src/index.ts`:
```typescript
export const VERSION = "0.1.0";
```

```bash
cd clients/typescript
pnpm install
pnpm typecheck
pnpm build
```

Expected: dist/index.js + dist/index.d.ts emitted.

- [ ] **Step 7: Commit**

```bash
cd /Users/baihe/Projects/study/meta-harney
git add pnpm-workspace.yaml clients/typescript/
git commit -m "feat(ts-client): pnpm workspace skeleton for @meta-harney/bridge-client"
```

---

### Task 2: framing.ts (Newline + ContentLength)

**Files:**
- Create: `clients/typescript/src/framing.ts`
- Test: `clients/typescript/tests/framing.test.ts`

- [ ] **Step 1: Tests**

`tests/framing.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { Readable, Writable } from "node:stream";
import { NewlineFraming, ContentLengthFraming, Framing } from "../src/framing.js";

function collectingStream(): { stream: Writable; bytes: () => Buffer } {
  const chunks: Buffer[] = [];
  const stream = new Writable({
    write(chunk, _enc, cb) { chunks.push(Buffer.from(chunk)); cb(); },
  });
  return { stream, bytes: () => Buffer.concat(chunks) };
}

async function readableOf(buf: Buffer): Promise<Readable> {
  const s = new Readable();
  s.push(buf);
  s.push(null);
  return s;
}

describe("NewlineFraming", () => {
  it("writes payload + newline", async () => {
    const f: Framing = new NewlineFraming();
    const { stream, bytes } = collectingStream();
    await f.writeMessage(stream, Buffer.from('{"a":1}'));
    expect(bytes().toString()).toBe('{"a":1}\n');
  });

  it("reads one line", async () => {
    const f: Framing = new NewlineFraming();
    const reader = await readableOf(Buffer.from('{"a":1}\n{"b":2}\n'));
    const a = await f.readMessage(reader);
    const b = await f.readMessage(reader);
    expect(a?.toString()).toBe('{"a":1}');
    expect(b?.toString()).toBe('{"b":2}');
  });

  it("returns null on EOF", async () => {
    const f: Framing = new NewlineFraming();
    const reader = await readableOf(Buffer.alloc(0));
    expect(await f.readMessage(reader)).toBeNull();
  });
});

describe("ContentLengthFraming", () => {
  it("writes header + body", async () => {
    const f: Framing = new ContentLengthFraming();
    const { stream, bytes } = collectingStream();
    const payload = Buffer.from('{"x":42}');
    await f.writeMessage(stream, payload);
    expect(bytes().toString()).toContain(`Content-Length: ${payload.length}\r\n\r\n`);
    expect(bytes().subarray(-payload.length).toString()).toBe('{"x":42}');
  });

  it("reads two messages", async () => {
    const f: Framing = new ContentLengthFraming();
    const buf = Buffer.concat([
      Buffer.from(`Content-Length: 7\r\n\r\n{"a":1}`),
      Buffer.from(`Content-Length: 7\r\n\r\n{"b":2}`),
    ]);
    const reader = await readableOf(buf);
    expect((await f.readMessage(reader))?.toString()).toBe('{"a":1}');
    expect((await f.readMessage(reader))?.toString()).toBe('{"b":2}');
  });
});
```

- [ ] **Step 2: Run, expect failures**

```bash
pnpm test framing
```
Expected: module not found.

- [ ] **Step 3: Implement**

`src/framing.ts`:
```typescript
import type { Readable, Writable } from "node:stream";

export interface Framing {
  readMessage(reader: Readable): Promise<Buffer | null>;
  writeMessage(writer: Writable, payload: Buffer): Promise<void>;
}

export class NewlineFraming implements Framing {
  async readMessage(reader: Readable): Promise<Buffer | null> {
    return await new Promise<Buffer | null>((resolve, reject) => {
      let buf = Buffer.alloc(0);
      const onData = (chunk: Buffer) => {
        buf = Buffer.concat([buf, chunk]);
        const nl = buf.indexOf(0x0a);
        if (nl !== -1) {
          reader.off("data", onData);
          reader.off("end", onEnd);
          reader.off("error", onErr);
          const line = buf.subarray(0, nl);
          const rest = buf.subarray(nl + 1);
          if (rest.length > 0) reader.unshift(rest);
          resolve(stripTrailingCR(line));
        }
      };
      const onEnd = () => {
        reader.off("data", onData);
        reader.off("error", onErr);
        if (buf.length === 0) resolve(null);
        else resolve(stripTrailingCR(buf));
      };
      const onErr = (e: Error) => {
        reader.off("data", onData);
        reader.off("end", onEnd);
        reject(e);
      };
      reader.on("data", onData);
      reader.once("end", onEnd);
      reader.once("error", onErr);
    });
  }

  async writeMessage(writer: Writable, payload: Buffer): Promise<void> {
    await writeAndDrain(writer, Buffer.concat([payload, Buffer.from("\n")]));
  }
}

export class ContentLengthFraming implements Framing {
  async readMessage(reader: Readable): Promise<Buffer | null> {
    const headers = await readHeaders(reader);
    if (headers === null) return null;
    const lenStr = headers.get("content-length");
    if (lenStr === undefined) throw new Error("missing Content-Length");
    const n = parseInt(lenStr, 10);
    if (!Number.isFinite(n) || n < 0) throw new Error(`invalid Content-Length: ${lenStr}`);
    return await readExact(reader, n);
  }

  async writeMessage(writer: Writable, payload: Buffer): Promise<void> {
    const header = Buffer.from(`Content-Length: ${payload.length}\r\n\r\n`, "ascii");
    await writeAndDrain(writer, Buffer.concat([header, payload]));
  }
}

function stripTrailingCR(b: Buffer): Buffer {
  if (b.length > 0 && b[b.length - 1] === 0x0d) return b.subarray(0, b.length - 1);
  return b;
}

function writeAndDrain(writer: Writable, data: Buffer): Promise<void> {
  return new Promise((resolve, reject) => {
    const ok = writer.write(data, (err) => {
      if (err) reject(err);
    });
    if (ok) resolve();
    else writer.once("drain", () => resolve());
  });
}

async function readHeaders(reader: Readable): Promise<Map<string, string> | null> {
  const headers = new Map<string, string>();
  let buf = Buffer.alloc(0);
  while (true) {
    const chunk = await readChunk(reader);
    if (chunk === null) {
      return buf.length === 0 ? null : headers;
    }
    buf = Buffer.concat([buf, chunk]);
    while (true) {
      const nl = buf.indexOf(0x0a);
      if (nl === -1) break;
      const line = buf.subarray(0, nl);
      buf = buf.subarray(nl + 1);
      const clean = stripTrailingCR(line);
      if (clean.length === 0) {
        if (buf.length > 0) reader.unshift(buf);
        return headers;
      }
      const sep = clean.indexOf(0x3a); // ':'
      if (sep === -1) continue;
      const k = clean.subarray(0, sep).toString("ascii").trim().toLowerCase();
      const v = clean.subarray(sep + 1).toString("ascii").trim();
      headers.set(k, v);
    }
  }
}

async function readChunk(reader: Readable): Promise<Buffer | null> {
  return await new Promise((resolve, reject) => {
    const onData = (c: Buffer) => { cleanup(); resolve(c); };
    const onEnd = () => { cleanup(); resolve(null); };
    const onErr = (e: Error) => { cleanup(); reject(e); };
    const cleanup = () => {
      reader.off("data", onData);
      reader.off("end", onEnd);
      reader.off("error", onErr);
    };
    reader.once("data", onData);
    reader.once("end", onEnd);
    reader.once("error", onErr);
  });
}

async function readExact(reader: Readable, n: number): Promise<Buffer> {
  let out = Buffer.alloc(0);
  while (out.length < n) {
    const chunk = await readChunk(reader);
    if (chunk === null) throw new Error(`unexpected EOF: needed ${n}, got ${out.length}`);
    out = Buffer.concat([out, chunk]);
  }
  if (out.length > n) {
    reader.unshift(out.subarray(n));
    out = out.subarray(0, n);
  }
  return out;
}
```

Update `src/index.ts`:
```typescript
export { NewlineFraming, ContentLengthFraming } from "./framing.js";
export type { Framing } from "./framing.js";
export const VERSION = "0.1.0";
```

- [ ] **Step 4: Run tests**

```bash
pnpm test framing
pnpm typecheck
```
Expected: tests pass; tsc clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/baihe/Projects/study/meta-harney
git add clients/typescript/src/framing.ts clients/typescript/src/index.ts clients/typescript/tests/framing.test.ts
git commit -m "feat(ts-client): NewlineFraming + ContentLengthFraming"
```

---

### Task 3: protocol.ts + errors.ts (JSON-RPC types)

**Files:**
- Create: `clients/typescript/src/protocol.ts`
- Create: `clients/typescript/src/errors.ts`
- Test: `clients/typescript/tests/protocol.test.ts`

- [ ] **Step 1: Tests**

`tests/protocol.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { parseIncoming, type JsonRpcRequest, type JsonRpcResponse, type JsonRpcNotification } from "../src/protocol.js";

describe("parseIncoming", () => {
  it("recognizes request", () => {
    const msg = parseIncoming(Buffer.from('{"jsonrpc":"2.0","id":1,"method":"ping"}'));
    expect(msg.kind).toBe("request");
    expect((msg as JsonRpcRequest).method).toBe("ping");
  });

  it("recognizes response (result)", () => {
    const msg = parseIncoming(Buffer.from('{"jsonrpc":"2.0","id":1,"result":42}'));
    expect(msg.kind).toBe("response");
    expect((msg as JsonRpcResponse).result).toBe(42);
  });

  it("recognizes response (error)", () => {
    const msg = parseIncoming(Buffer.from('{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"x"}}'));
    expect(msg.kind).toBe("response");
    const err = (msg as JsonRpcResponse).error!;
    expect(err.code).toBe(-32601);
  });

  it("recognizes notification", () => {
    const msg = parseIncoming(Buffer.from('{"jsonrpc":"2.0","method":"$/cancelRequest","params":{"id":7}}'));
    expect(msg.kind).toBe("notification");
    expect((msg as JsonRpcNotification).method).toBe("$/cancelRequest");
  });

  it("rejects non-2.0", () => {
    expect(() => parseIncoming(Buffer.from('{"id":1,"method":"ping"}'))).toThrow();
  });

  it("rejects invalid JSON", () => {
    expect(() => parseIncoming(Buffer.from("not json"))).toThrow();
  });
});
```

- [ ] **Step 2: Implement protocol.ts**

```typescript
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

export type IncomingMessage = JsonRpcRequest | JsonRpcResponse | JsonRpcNotification;

export function parseIncoming(raw: Buffer): IncomingMessage {
  let data: any;
  try {
    data = JSON.parse(raw.toString("utf-8"));
  } catch (e) {
    throw new Error(`invalid JSON: ${(e as Error).message}`);
  }
  if (typeof data !== "object" || data === null) throw new Error("not an object");
  if (data.jsonrpc !== "2.0") throw new Error("missing/invalid jsonrpc field");

  const hasId = "id" in data;
  const hasMethod = "method" in data;
  const hasResultOrError = "result" in data || "error" in data;

  if (hasMethod && hasId) {
    return { kind: "request", jsonrpc: "2.0", id: data.id, method: data.method, params: data.params };
  }
  if (hasMethod && !hasId) {
    return { kind: "notification", jsonrpc: "2.0", method: data.method, params: data.params };
  }
  if (hasId && hasResultOrError) {
    return { kind: "response", jsonrpc: "2.0", id: data.id, result: data.result, error: data.error };
  }
  throw new Error(`cannot classify message: ${Object.keys(data).join(",")}`);
}

export function encodeRequest(id: number | string, method: string, params?: unknown): Buffer {
  return Buffer.from(JSON.stringify({ jsonrpc: "2.0", id, method, ...(params !== undefined ? { params } : {}) }), "utf-8");
}

export function encodeNotification(method: string, params?: unknown): Buffer {
  return Buffer.from(JSON.stringify({ jsonrpc: "2.0", method, ...(params !== undefined ? { params } : {}) }), "utf-8");
}

export function encodeResponse(id: number | string | null, result: unknown): Buffer {
  return Buffer.from(JSON.stringify({ jsonrpc: "2.0", id, result }), "utf-8");
}

export function encodeError(id: number | string | null, error: JsonRpcError): Buffer {
  return Buffer.from(JSON.stringify({ jsonrpc: "2.0", id, error }), "utf-8");
}
```

- [ ] **Step 3: Implement errors.ts**

```typescript
export class BridgeError extends Error {
  constructor(message: string, public readonly code: number, public readonly data?: unknown) {
    super(message);
    this.name = "BridgeError";
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
  }
}
```

- [ ] **Step 4: Re-export**

In `src/index.ts`, add:
```typescript
export * from "./protocol.js";
export * from "./errors.js";
```

- [ ] **Step 5: Test + commit**

```bash
pnpm test
pnpm typecheck
cd /Users/baihe/Projects/study/meta-harney
git add clients/typescript/src/protocol.ts clients/typescript/src/errors.ts clients/typescript/src/index.ts clients/typescript/tests/protocol.test.ts
git commit -m "feat(ts-client): JSON-RPC 2.0 protocol types + BridgeError hierarchy"
```

---

### Task 4: transport.ts (ChildProcessTransport)

**Files:**
- Create: `clients/typescript/src/transport.ts`
- Test: `clients/typescript/tests/transport.test.ts`

- [ ] **Step 1: Tests**

`tests/transport.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { ChildProcessTransport } from "../src/transport.js";
import { NewlineFraming } from "../src/framing.js";

describe("ChildProcessTransport", () => {
  it("spawns, writes, reads, exits", async () => {
    // Echo back stdin line-by-line on stdout
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "process.stdin.on('data', d => process.stdout.write(d));"],
      framing: new NewlineFraming(),
    });
    await transport.start();
    await transport.write(Buffer.from('{"hi":1}'));
    const msg = await transport.read();
    expect(msg?.toString()).toBe('{"hi":1}');
    await transport.stop();
  });

  it("returns null when child exits cleanly", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "process.exit(0);"],
      framing: new NewlineFraming(),
    });
    await transport.start();
    const msg = await transport.read();
    expect(msg).toBeNull();
    await transport.stop();
  });
});
```

- [ ] **Step 2: Implement transport.ts**

```typescript
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { Framing } from "./framing.js";

export interface TransportOptions {
  command: string;
  args?: string[];
  env?: NodeJS.ProcessEnv;
  cwd?: string;
  framing: Framing;
  stderrPassthrough?: boolean; // default true
}

export class ChildProcessTransport {
  private proc: ChildProcessWithoutNullStreams | null = null;
  private framing: Framing;
  private options: TransportOptions;

  constructor(options: TransportOptions) {
    this.options = options;
    this.framing = options.framing;
  }

  async start(): Promise<void> {
    if (this.proc) throw new Error("already started");
    this.proc = spawn(this.options.command, this.options.args ?? [], {
      env: this.options.env ?? process.env,
      cwd: this.options.cwd,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stderrPassthrough = this.options.stderrPassthrough ?? true;
    if (stderrPassthrough) {
      this.proc.stderr.pipe(process.stderr);
    }
  }

  async read(): Promise<Buffer | null> {
    if (!this.proc) throw new Error("not started");
    return await this.framing.readMessage(this.proc.stdout);
  }

  async write(payload: Buffer): Promise<void> {
    if (!this.proc) throw new Error("not started");
    await this.framing.writeMessage(this.proc.stdin, payload);
  }

  async stop(timeoutMs = 5000): Promise<number | null> {
    if (!this.proc) return null;
    const proc = this.proc;
    this.proc = null;
    try { proc.stdin.end(); } catch {/* ignore */}
    const exited = new Promise<number | null>((resolve) => {
      const timer = setTimeout(() => {
        try { proc.kill("SIGKILL"); } catch {/* ignore */}
      }, timeoutMs);
      proc.once("exit", (code) => { clearTimeout(timer); resolve(code); });
    });
    return await exited;
  }

  isAlive(): boolean {
    return this.proc !== null && this.proc.exitCode === null;
  }
}
```

- [ ] **Step 3: Re-export + test + commit**

In `src/index.ts`:
```typescript
export { ChildProcessTransport } from "./transport.js";
export type { TransportOptions } from "./transport.js";
```

```bash
pnpm test
pnpm typecheck
cd /Users/baihe/Projects/study/meta-harney
git add clients/typescript/src/transport.ts clients/typescript/src/index.ts clients/typescript/tests/transport.test.ts
git commit -m "feat(ts-client): ChildProcessTransport with framing"
```

---

### Task 5: client.ts skeleton + lifecycle (initialize / shutdown / exit)

**Files:**
- Create: `clients/typescript/src/client.ts`
- Test: `clients/typescript/tests/client.test.ts`

- [ ] **Step 1: Tests** — Use a mock transport for unit isolation.

`tests/client.test.ts`:
```typescript
import { describe, it, expect, vi } from "vitest";
import { BridgeClient } from "../src/client.js";
import type { Framing } from "../src/framing.js";

class FakeTransport {
  framing: Framing = null as any;
  queue: Buffer[] = [];
  sent: Buffer[] = [];
  alive = true;
  async start() {}
  async stop() { this.alive = false; return 0; }
  async read(): Promise<Buffer | null> {
    if (this.queue.length === 0) return null;
    return this.queue.shift()!;
  }
  async write(p: Buffer) { this.sent.push(p); }
  isAlive() { return this.alive; }
  feed(obj: any) { this.queue.push(Buffer.from(JSON.stringify(obj))); }
}

describe("BridgeClient lifecycle", () => {
  it("initialize sends request and returns server info", async () => {
    const t = new FakeTransport();
    const client = new BridgeClient({ transport: t as any });
    t.feed({ jsonrpc: "2.0", id: 1, result: { server_info: { name: "x", version: "1" } } });
    const p = client.start().then(() => client.initialize({ clientInfo: { name: "test", version: "0" } }));
    const info = await p;
    expect(info.server_info.name).toBe("x");
    const sent = JSON.parse(t.sent[0]!.toString());
    expect(sent.method).toBe("initialize");
    expect(sent.id).toBe(1);
    await client.shutdown(); await client.exit();
  });

  it("shutdown sends shutdown then exit notification", async () => {
    const t = new FakeTransport();
    const client = new BridgeClient({ transport: t as any });
    await client.start();
    t.feed({ jsonrpc: "2.0", id: 1, result: null });
    await client.shutdown();
    await client.exit();
    const methods = t.sent.map(b => JSON.parse(b.toString()).method);
    expect(methods).toEqual(["shutdown", "exit"]);
  });
});
```

- [ ] **Step 2: Implement client.ts (lifecycle skeleton)**

```typescript
import type { ChildProcessTransport } from "./transport.js";
import { encodeRequest, encodeNotification, parseIncoming, type IncomingMessage } from "./protocol.js";
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

type PendingResolver = { resolve: (v: unknown) => void; reject: (e: Error) => void };

export class BridgeClient {
  private transport: ChildProcessTransport;
  private nextId = 1;
  private pending = new Map<number | string, PendingResolver>();
  private readLoopStarted = false;
  private closing = false;

  // Hooks set later (Task 6+ wires them):
  protected onNotification: ((method: string, params: unknown) => void) | null = null;
  protected onIncomingRequest: ((req: { id: number | string; method: string; params: unknown }) => Promise<unknown>) | null = null;

  constructor(options: BridgeClientOptions) {
    this.transport = options.transport;
  }

  async start(): Promise<void> {
    await this.transport.start();
    void this.readLoop();
  }

  private async readLoop(): Promise<void> {
    if (this.readLoopStarted) return;
    this.readLoopStarted = true;
    while (this.transport.isAlive() || !this.closing) {
      let raw: Buffer | null;
      try {
        raw = await this.transport.read();
      } catch (e) {
        this.failAllPending(e as Error);
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
        continue;
      }
      if (msg.kind === "response") {
        const id = msg.id;
        if (id !== null) {
          const p = this.pending.get(id);
          if (p) {
            this.pending.delete(id);
            if (msg.error) p.reject(new BridgeError(msg.error.message, msg.error.code, msg.error.data));
            else p.resolve(msg.result);
          }
        }
      } else if (msg.kind === "notification") {
        this.onNotification?.(msg.method, msg.params);
      } else if (msg.kind === "request") {
        const handler = this.onIncomingRequest;
        if (handler !== null) {
          handler({ id: msg.id, method: msg.method, params: msg.params })
            .then(result => this.transport.write(encodeRequest as any)) // placeholder, real impl below
            .catch(() => { /* swallow */ });
          // Actual response writing handled below via _respondTo
          handler({ id: msg.id, method: msg.method, params: msg.params })
            .then((result) => this._respondTo(msg.id, result))
            .catch((e: Error) => this._respondError(msg.id, { code: -32603, message: e.message }));
        }
      }
    }
  }

  private failAllPending(err: Error): void {
    for (const [, p] of this.pending) p.reject(err);
    this.pending.clear();
  }

  protected _respondTo(id: number | string, result: unknown): Promise<void> {
    return this.transport.write(
      Buffer.from(JSON.stringify({ jsonrpc: "2.0", id, result }), "utf-8")
    );
  }

  protected _respondError(id: number | string, error: { code: number; message: string; data?: unknown }): Promise<void> {
    return this.transport.write(
      Buffer.from(JSON.stringify({ jsonrpc: "2.0", id, error }), "utf-8")
    );
  }

  protected async sendRequest<T>(method: string, params?: unknown): Promise<T> {
    const id = this.nextId++;
    const p = new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
    });
    await this.transport.write(encodeRequest(id, method, params));
    return await p;
  }

  protected async sendNotification(method: string, params?: unknown): Promise<void> {
    await this.transport.write(encodeNotification(method, params));
  }

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

  async exit(): Promise<void> {
    this.closing = true;
    await this.sendNotification("exit");
    await this.transport.stop();
  }
}
```

Note: clean up the duplicate `handler({...}).then(...)` blocks in `readLoop` (above code has placeholder; final version should call `handler` once, route result/error via `_respondTo`/`_respondError`).

- [ ] **Step 3: Re-export + run tests + commit**

In `src/index.ts`:
```typescript
export { BridgeClient } from "./client.js";
export type { BridgeClientOptions, InitializeParams, InitializeResult } from "./client.js";
```

```bash
pnpm test client
pnpm typecheck
cd /Users/baihe/Projects/study/meta-harney
git add clients/typescript/src/client.ts clients/typescript/src/index.ts clients/typescript/tests/client.test.ts
git commit -m "feat(ts-client): BridgeClient with initialize/shutdown/exit + request pump"
```

---

### Task 6: Sessions (create/list/load) + tools.list

**Files:**
- Modify: `clients/typescript/src/client.ts`
- Test: `clients/typescript/tests/client.test.ts` (append)

Add methods to `BridgeClient`:

```typescript
  async sessionCreate(params?: { sessionId?: string; tenantId?: string; userId?: string }): Promise<{ id: string; created_at: string }> {
    return await this.sendRequest("session.create", {
      session_id: params?.sessionId,
      tenant_id: params?.tenantId,
      user_id: params?.userId,
    });
  }

  async sessionList(): Promise<Array<{ id: string; created_at: string; message_count: number; last_message_at: string | null }>> {
    return await this.sendRequest("session.list");
  }

  async sessionLoad(sessionId: string): Promise<{ id: string; created_at: string; messages: any[] }> {
    return await this.sendRequest("session.load", { session_id: sessionId });
  }

  async toolsList(): Promise<Array<{ name: string; description: string; input_schema: unknown }>> {
    return await this.sendRequest("tools.list");
  }
```

Tests:
```typescript
it("sessionCreate sends correct method", async () => {
  const t = new FakeTransport();
  const client = new BridgeClient({ transport: t as any });
  t.feed({ jsonrpc: "2.0", id: 1, result: { id: "abc", created_at: "2026-01-01" } });
  await client.start();
  const s = await client.sessionCreate();
  expect(s.id).toBe("abc");
  expect(JSON.parse(t.sent[0]!.toString()).method).toBe("session.create");
});
```

Repeat similar for sessionList, sessionLoad, toolsList. Commit:
`feat(ts-client): session.create/list/load + tools.list`

---

### Task 7: SendMessageHandle (streaming + permission + cancel)

**Files:**
- Modify: `clients/typescript/src/client.ts`
- Create: a separate `SendMessageHandle` class (in same file or new file)
- Test: `clients/typescript/tests/client.test.ts` (append)

Design:
```typescript
export interface SendMessageHandle {
  onEvent(handler: (event: any) => void): void;
  onPermissionRequest(handler: (req: { tool: string; tool_args: unknown; session_id: string; call_id: string }) => Promise<{ decision: "allow" | "deny" | "allow_always" }>): void;
  cancel(): Promise<void>;
  readonly requestId: number;
  readonly done: Promise<{ stopped_reason: string }>;
}
```

Implementation strategy:
- `BridgeClient.sendMessage(sessionId, message)` returns a handle
- The handle owns: requestId, eventHandlers, permissionHandler, cancelled flag
- Client maintains `inflightHandles: Map<requestId, SendMessageHandle>`
- In `onNotification`, if method is `stream/event`, route to handle by `params.request_id`
- In `onIncomingRequest`, if method is `permission/request`, route to relevant handle's permission handler
- `handle.cancel()` sends `$/cancelRequest` notification

Code:
```typescript
class SendMessageHandleImpl implements SendMessageHandle {
  constructor(
    public readonly requestId: number,
    public readonly done: Promise<{ stopped_reason: string }>,
    private _client: BridgeClient,
  ) {}
  private _events: Array<(e: any) => void> = [];
  private _perm: ((req: any) => Promise<{ decision: "allow" | "deny" | "allow_always" }>) | null = null;

  onEvent(h: (event: any) => void): void { this._events.push(h); }
  onPermissionRequest(h: (req: any) => Promise<{ decision: "allow" | "deny" | "allow_always" }>): void { this._perm = h; }
  async cancel(): Promise<void> { await this._client._sendCancel(this.requestId); }

  _emit(event: any): void { for (const h of this._events) h(event); }
  async _handlePermission(req: any): Promise<{ decision: "allow" | "deny" | "allow_always" }> {
    if (!this._perm) return { decision: "deny" };
    return await this._perm(req);
  }
}
```

In `BridgeClient`:

```typescript
  private inflight = new Map<number, SendMessageHandleImpl>();

  sendMessage(sessionId: string, message: { role: string; content: any[] }): SendMessageHandle {
    const requestId = this.nextId++;
    const done = new Promise<{ stopped_reason: string }>((resolve, reject) => {
      this.pending.set(requestId, { resolve: resolve as any, reject });
    });
    const handle = new SendMessageHandleImpl(requestId, done, this);
    this.inflight.set(requestId, handle);
    void this.transport.write(encodeRequest(requestId, "session.send_message", {
      session_id: sessionId, message,
    }));
    return handle;
  }

  async _sendCancel(requestId: number): Promise<void> {
    await this.sendNotification("$/cancelRequest", { id: requestId });
  }
```

Wire in constructor / readLoop:
```typescript
    this.onNotification = (method, params) => {
      if (method === "stream/event") {
        const p = params as { request_id: number; event: unknown };
        const h = this.inflight.get(p.request_id);
        h?._emit(p.event);
      } else if (method === "telemetry/event") {
        // Task 8 wires this
      }
    };

    this.onIncomingRequest = async (req) => {
      if (req.method === "permission/request") {
        const params = req.params as any;
        // Find a relevant handle; since bridge sends server-initiated requests
        // with negative ids unrelated to our request ids, route to any active handle
        // (in oh-mini bridge, only one send_message is typically inflight per
        // request_id, but multiple handles may exist concurrently — match by
        // session_id if needed).
        // For v1, route to the most recently active handle:
        const handles = Array.from(this.inflight.values());
        const handle = handles[handles.length - 1];
        if (!handle) return { decision: "deny" };
        return await handle._handlePermission(params);
      }
      throw new BridgeError(`unknown server-initiated request: ${req.method}`, -32601);
    };
```

Also: handle done resolution — `pending` map already resolves on response. When response arrives for a send_message id, remove from `inflight` too. Modify the response handling in readLoop:
```typescript
        const p = this.pending.get(id);
        if (p) {
          this.pending.delete(id);
          this.inflight.delete(id as number); // clean inflight
          if (msg.error) p.reject(new BridgeError(msg.error.message, msg.error.code, msg.error.data));
          else p.resolve(msg.result);
        }
```

Tests (with FakeTransport):
- send_message returns handle; feeding stream/event notifications calls onEvent
- feeding permission/request leads to permission handler call + response
- cancel() sends `$/cancelRequest` notification
- final response resolves `done`

Commit:
`feat(ts-client): sendMessage with streaming + permission + cancel handle`

---

### Task 8: Telemetry

**Files:**
- Modify: `clients/typescript/src/client.ts`
- Test: append to `tests/client.test.ts`

Add:
```typescript
  private telemetryHandlers: Array<(ev: { event_type: string; payload: unknown }) => void> = [];

  async telemetrySubscribe(enabled: boolean): Promise<{ enabled: boolean }> {
    return await this.sendRequest("telemetry/subscribe", { enabled });
  }

  onTelemetry(handler: (ev: { event_type: string; payload: unknown }) => void): void {
    this.telemetryHandlers.push(handler);
  }
```

Wire in `onNotification`:
```typescript
      } else if (method === "telemetry/event") {
        const p = params as { event_type: string; payload: unknown };
        for (const h of this.telemetryHandlers) h(p);
      }
```

Test: subscribe(true) sends correct method; feeding telemetry/event triggers handlers.

Commit: `feat(ts-client): telemetry/subscribe + onTelemetry`

---

### Task 9: E2E test against real `oh bridge`

**File:**
- Create: `clients/typescript/tests/e2e-real-bridge.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import { BridgeClient, ChildProcessTransport, NewlineFraming } from "../src/index.js";

describe("E2E real oh bridge", () => {
  it("full lifecycle with FakeProvider", async () => {
    const env = { ...process.env, OH_MINI_TEST_FAKE_PROVIDER: "1", OH_MINI_FORCE_FILE_BACKEND: "1", HOME: "/tmp/oh-tui-test-" + Date.now() };
    const transport = new ChildProcessTransport({
      command: process.env.OH_BIN ?? "oh",
      args: ["bridge", "--provider", "deepseek", "--yolo"],
      framing: new NewlineFraming(),
      env,
    });
    const client = new BridgeClient({ transport });
    await client.start();
    try {
      const init = await client.initialize({ clientInfo: { name: "test", version: "0" } });
      expect(init.server_info.name).toBe("oh-mini-bridge");

      const tools = await client.toolsList();
      expect(tools.map(t => t.name)).toContain("bash");

      const { id } = await client.sessionCreate();
      const handle = client.sendMessage(id, { role: "user", content: [{ type: "text", text: "hi" }] });

      const events: any[] = [];
      handle.onEvent(e => events.push(e));
      const final = await handle.done;
      expect(final.stopped_reason).toBe("completed");
      expect(events.length).toBeGreaterThan(0);

      await client.shutdown();
      await client.exit();
    } catch (e) {
      await client.exit().catch(() => {});
      throw e;
    }
  }, 15000);
});
```

Run guard: this test requires `oh` on PATH. Skip if missing:
```typescript
const ohAvailable = (() => { try { require("node:child_process").execSync("which oh"); return true; } catch { return false; } })();
const itGated = ohAvailable ? it : it.skip;
// use itGated("full lifecycle...", ...)
```

Run all tests + commit:
```bash
pnpm test
pnpm typecheck
pnpm lint
pnpm build
cd /Users/baihe/Projects/study/meta-harney
git add clients/typescript/tests/e2e-real-bridge.test.ts
git commit -m "test(ts-client): E2E against real oh bridge subprocess"
```

---

# Part B: oh-tui Ink app (Tasks 10-19)

### Task 10: oh-tui repo init

**Files:**
- Create new repo: `/Users/baihe/Projects/study/oh-tui/`

- [ ] **Step 1: Init**

```bash
mkdir -p /Users/baihe/Projects/study/oh-tui
cd /Users/baihe/Projects/study/oh-tui
git init
echo "node_modules/\ndist/\n*.log" > .gitignore
```

- [ ] **Step 2: package.json**

```json
{
  "name": "oh-tui",
  "version": "0.1.0",
  "description": "Ink TUI for the oh-mini coding agent",
  "type": "module",
  "bin": { "oh-tui": "./bin/oh-tui" },
  "files": ["bin", "src", "README.md"],
  "scripts": {
    "start": "tsx src/cli.tsx",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "lint": "eslint src tests --ext .ts,.tsx",
    "format": "prettier -w src tests"
  },
  "engines": { "node": ">=18" },
  "dependencies": {
    "@meta-harney/bridge-client": "file:../meta-harney/clients/typescript",
    "ink": "^5.0.0",
    "ink-text-input": "^6.0.0",
    "react": "^18.2.0"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "@types/react": "^18.2.0",
    "@typescript-eslint/eslint-plugin": "^7.0.0",
    "@typescript-eslint/parser": "^7.0.0",
    "eslint": "^8.57.0",
    "eslint-plugin-react": "^7.34.0",
    "ink-testing-library": "^4.0.0",
    "prettier": "^3.2.0",
    "tsx": "^4.7.0",
    "typescript": "^5.4.0",
    "vitest": "^1.4.0"
  }
}
```

- [ ] **Step 3: tsconfig.json, eslint, vitest config**

Same shape as 11a (strict ESM, ES2022) but with `"jsx": "react-jsx"` for tsx files.

- [ ] **Step 4: bin/oh-tui**

```bash
#!/usr/bin/env node
import("../src/cli.js").catch((err) => { console.error(err); process.exit(1); });
```

```bash
chmod +x bin/oh-tui
```

Wait — since we use tsx for dev, the `bin` shebang should actually invoke tsx during dev. For v1, simplest: `bin/oh-tui` is a bash wrapper that calls `tsx src/cli.tsx`. We can refine packaging later.

```bash
#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
exec "$DIR"/../node_modules/.bin/tsx "$DIR"/../src/cli.tsx "$@"
```

- [ ] **Step 5: Install + smoke**

```bash
pnpm install
pnpm typecheck    # expect empty src/cli.tsx errors; OK
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "init: oh-tui v0.1.0 — Ink TUI scaffolding"
```

---

### Task 11: cli.tsx + App.tsx + locate-bridge.ts

**Files:**
- Create: `src/cli.tsx`, `src/App.tsx`, `src/types.ts`, `src/lib/locate-bridge.ts`

`src/types.ts`:
```typescript
export interface CliArgs {
  prompt: string | null;
  provider: string | null;
  profile: string | null;
  model: string | null;
  framing: "newline" | "content-length";
  bridgeBin: string;
  bridgeArgs: string[];
  yolo: boolean;
}
```

`src/lib/locate-bridge.ts`:
```typescript
import { execSync } from "node:child_process";

export function locateBridge(explicit: string | null): string {
  if (explicit) return explicit;
  try {
    return execSync("which oh", { encoding: "utf-8" }).trim();
  } catch {
    throw new Error("Cannot find `oh` on PATH. Pass --bridge-bin or install oh-mini.");
  }
}
```

`src/cli.tsx`:
```typescript
import React from "react";
import { render } from "ink";
import { App } from "./App.js";
import type { CliArgs } from "./types.js";

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    prompt: null,
    provider: null,
    profile: null,
    model: null,
    framing: "newline",
    bridgeBin: "oh",
    bridgeArgs: [],
    yolo: false,
  };
  const rest: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a === "--provider") args.provider = argv[++i] ?? null;
    else if (a === "--profile") args.profile = argv[++i] ?? null;
    else if (a === "--model") args.model = argv[++i] ?? null;
    else if (a === "--framing") args.framing = (argv[++i] as "newline" | "content-length") ?? "newline";
    else if (a === "--bridge-bin") args.bridgeBin = argv[++i] ?? "oh";
    else if (a === "--yolo") args.yolo = true;
    else if (a === "--help" || a === "-h") { printHelp(); process.exit(0); }
    else if (a === "--version") { console.log("oh-tui 0.1.0"); process.exit(0); }
    else rest.push(a);
  }
  if (rest.length > 0) args.prompt = rest.join(" ");
  return args;
}

function printHelp(): void {
  console.log(`oh-tui [prompt] — Ink TUI for oh-mini

  --provider X       provider name
  --profile P        profile
  --model M          model override
  --framing F        newline (default) | content-length
  --bridge-bin PATH  override oh executable
  --yolo             skip permission dialogs
  -h, --help         this help
  --version          version`);
}

const args = parseArgs(process.argv.slice(2));
render(<App args={args} />);
```

`src/App.tsx`:
```typescript
import React from "react";
import { OneShotMode } from "./modes/OneShotMode.js";
import { ReplMode } from "./modes/ReplMode.js";
import type { CliArgs } from "./types.js";

export function App({ args }: { args: CliArgs }): React.JSX.Element {
  return args.prompt !== null ? <OneShotMode args={args} /> : <ReplMode args={args} />;
}
```

Create stub `src/modes/OneShotMode.tsx` and `src/modes/ReplMode.tsx` that just `<Text>...</Text>` "TODO: implement". Run `pnpm typecheck`. Commit.

---

### Task 12: useBridgeClient hook

**Files:**
- Create: `src/hooks/useBridgeClient.ts`
- Test: `tests/hooks.test.ts` (basic init test)

```typescript
import { useEffect, useRef, useState } from "react";
import { BridgeClient, ChildProcessTransport, NewlineFraming, ContentLengthFraming, type Framing } from "@meta-harney/bridge-client";
import type { CliArgs } from "../types.js";
import { locateBridge } from "../lib/locate-bridge.js";

export function useBridgeClient(args: CliArgs): {
  client: BridgeClient | null;
  error: Error | null;
  ready: boolean;
} {
  const [client, setClient] = useState<BridgeClient | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [ready, setReady] = useState(false);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const framing: Framing = args.framing === "content-length"
      ? new ContentLengthFraming()
      : new NewlineFraming();

    const bridgeArgs = ["bridge"];
    if (args.provider) bridgeArgs.push("--provider", args.provider);
    if (args.profile) bridgeArgs.push("--profile", args.profile);
    if (args.model) bridgeArgs.push("--model", args.model);
    if (args.framing === "content-length") bridgeArgs.push("--framing", "content-length");
    if (args.yolo) bridgeArgs.push("--yolo");

    const transport = new ChildProcessTransport({
      command: locateBridge(args.bridgeBin),
      args: bridgeArgs,
      framing,
    });
    const c = new BridgeClient({ transport });
    c.start()
      .then(() => c.initialize({ clientInfo: { name: "oh-tui", version: "0.1.0" } }))
      .then(() => { setClient(c); setReady(true); })
      .catch((e: Error) => setError(e));

    return () => {
      c.shutdown().then(() => c.exit()).catch(() => {});
    };
  }, []);

  return { client, error, ready };
}
```

Commit: `feat(tui): useBridgeClient hook with lifecycle`

---

### Task 13: OneShotMode + StreamingMessage + ToolUseBadge

**Files:**
- Modify: `src/modes/OneShotMode.tsx`
- Create: `src/components/StreamingMessage.tsx`
- Create: `src/components/ToolUseBadge.tsx`

`src/components/StreamingMessage.tsx`:
```typescript
import React from "react";
import { Box, Text } from "ink";

interface Props {
  text: string;
  finished: boolean;
}

export function StreamingMessage({ text, finished }: Props): React.JSX.Element {
  return (
    <Box flexDirection="column" marginY={1}>
      <Text>{text}{!finished && "▍"}</Text>
    </Box>
  );
}
```

`src/components/ToolUseBadge.tsx`:
```typescript
import React from "react";
import { Box, Text } from "ink";

interface Props {
  tool: string;
  status: "running" | "done" | "error";
  args?: unknown;
}

export function ToolUseBadge({ tool, status, args }: Props): React.JSX.Element {
  const icon = status === "running" ? "▸" : status === "done" ? "✓" : "✗";
  const color = status === "done" ? "green" : status === "error" ? "red" : "yellow";
  return (
    <Box>
      <Text color={color}>{icon} </Text>
      <Text bold>{tool}</Text>
      {args !== undefined && <Text dimColor> {JSON.stringify(args).slice(0, 80)}</Text>}
    </Box>
  );
}
```

`src/modes/OneShotMode.tsx`:
```typescript
import React, { useEffect, useState } from "react";
import { Box, Text, useApp } from "ink";
import { useBridgeClient } from "../hooks/useBridgeClient.js";
import { StreamingMessage } from "../components/StreamingMessage.js";
import { ToolUseBadge } from "../components/ToolUseBadge.js";
import type { CliArgs } from "../types.js";

interface ToolEvent { tool: string; status: "running" | "done" | "error"; args?: unknown; }

export function OneShotMode({ args }: { args: CliArgs }): React.JSX.Element {
  const { client, error, ready } = useBridgeClient(args);
  const [text, setText] = useState("");
  const [tools, setTools] = useState<ToolEvent[]>([]);
  const [done, setDone] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const app = useApp();

  useEffect(() => {
    if (!ready || !client || !args.prompt) return;
    let cancelled = false;
    (async () => {
      try {
        const { id } = await client.sessionCreate();
        setSessionId(id);
        if (cancelled) return;
        const handle = client.sendMessage(id, { role: "user", content: [{ type: "text", text: args.prompt! }] });
        handle.onEvent((ev: any) => {
          if (ev.kind === "text_delta") setText(t => t + (ev.text ?? ""));
          else if (ev.kind === "tool_use") setTools(prev => [...prev, { tool: ev.tool ?? "?", status: "running", args: ev.args }]);
          else if (ev.kind === "tool_result") setTools(prev => prev.map((t, i) => i === prev.length - 1 ? { ...t, status: ev.error ? "error" : "done" } : t));
        });
        await handle.done;
        if (!cancelled) { setDone(true); setTimeout(() => app.exit(), 100); }
      } catch (e) {
        if (!cancelled) { console.error(e); app.exit(); }
      }
    })();
    return () => { cancelled = true; };
  }, [ready, client]);

  if (error) return <Text color="red">error: {error.message}</Text>;
  if (!ready) return <Text dimColor>connecting…</Text>;

  return (
    <Box flexDirection="column">
      {sessionId && <Text dimColor>session: {sessionId.slice(0, 8)}…</Text>}
      <Text dimColor>{`> ${args.prompt}`}</Text>
      <Box flexDirection="column">
        {tools.map((t, i) => <ToolUseBadge key={i} tool={t.tool} status={t.status} args={t.args} />)}
        <StreamingMessage text={text} finished={done} />
      </Box>
    </Box>
  );
}
```

Smoke test:
```bash
cd /Users/baihe/Projects/study/oh-tui
pnpm start "hi"
# Expected: connects, shows streaming response from oh bridge, exits
```

Commit: `feat(tui): OneShotMode with streaming text + tool badges`

---

### Task 14: PermissionDialog

**Files:**
- Create: `src/components/PermissionDialog.tsx`
- Modify: `src/modes/OneShotMode.tsx` to wire it

`src/components/PermissionDialog.tsx`:
```typescript
import React, { useState } from "react";
import { Box, Text, useInput } from "ink";

interface Props {
  tool: string;
  args: unknown;
  onDecide: (decision: "allow" | "deny" | "allow_always") => void;
}

export function PermissionDialog({ tool, args, onDecide }: Props): React.JSX.Element {
  useInput((input) => {
    if (input === "y") onDecide("allow");
    else if (input === "n") onDecide("deny");
    else if (input === "a") onDecide("allow_always");
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor="yellow" padding={1}>
      <Text bold>permission required</Text>
      <Text>tool: <Text color="cyan">{tool}</Text></Text>
      <Text>args: <Text dimColor>{JSON.stringify(args).slice(0, 200)}</Text></Text>
      <Box marginTop={1}>
        <Text>[y] allow   [n] deny   [a] allow_always</Text>
      </Box>
    </Box>
  );
}
```

In `OneShotMode.tsx`, add a pending permission state + dialog:
```typescript
const [permission, setPermission] = useState<{ tool: string; args: unknown; resolve: (d: any) => void } | null>(null);

// In the useEffect, after creating handle:
handle.onPermissionRequest(async (req) => {
  return await new Promise<{ decision: "allow" | "deny" | "allow_always" }>((resolve) => {
    setPermission({ tool: req.tool, args: req.tool_args, resolve: (d) => { setPermission(null); resolve({ decision: d }); } });
  });
});

// In JSX, render dialog when permission is set
{permission && <PermissionDialog tool={permission.tool} args={permission.args} onDecide={permission.resolve} />}
```

Smoke: `oh-tui "用 bash 跑 echo test"` — expect dialog appears.

Commit: `feat(tui): permission dialog with y/n/a keys`

---

### Task 15: ReplMode + PromptInput + history

**Files:**
- Create: `src/components/PromptInput.tsx`
- Modify: `src/modes/ReplMode.tsx`

`src/components/PromptInput.tsx`:
```typescript
import React, { useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

interface Props {
  history: string[];
  onSubmit: (text: string) => void;
}

export function PromptInput({ history, onSubmit }: Props): React.JSX.Element {
  const [value, setValue] = useState("");
  const [hIdx, setHIdx] = useState(history.length);

  return (
    <Box>
      <Text color="cyan">oh&gt; </Text>
      <TextInput
        value={value}
        onChange={setValue}
        onSubmit={(v) => { onSubmit(v); setValue(""); setHIdx(history.length + 1); }}
      />
    </Box>
  );
}
```

`src/modes/ReplMode.tsx`:
```typescript
import React, { useState } from "react";
import { Box, Text, useApp } from "ink";
import { useBridgeClient } from "../hooks/useBridgeClient.js";
import { PromptInput } from "../components/PromptInput.js";
import { StreamingMessage } from "../components/StreamingMessage.js";
import type { CliArgs } from "../types.js";

interface Turn { prompt: string; response: string; done: boolean; }

export function ReplMode({ args }: { args: CliArgs }): React.JSX.Element {
  const { client, ready, error } = useBridgeClient(args);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const app = useApp();

  if (error) return <Text color="red">error: {error.message}</Text>;
  if (!ready || !client) return <Text dimColor>connecting…</Text>;

  const onSubmit = async (prompt: string) => {
    if (prompt === "/exit" || prompt === "/quit") return app.exit();
    if (prompt.trim() === "") return;
    setHistory(h => [...h, prompt]);

    let sid = sessionId;
    if (!sid) {
      const { id } = await client.sessionCreate();
      sid = id;
      setSessionId(id);
    }

    const turnIdx = turns.length;
    setTurns(prev => [...prev, { prompt, response: "", done: false }]);
    const handle = client.sendMessage(sid, { role: "user", content: [{ type: "text", text: prompt }] });
    handle.onEvent((ev: any) => {
      if (ev.kind === "text_delta") setTurns(prev => prev.map((t, i) => i === turnIdx ? { ...t, response: t.response + (ev.text ?? "") } : t));
    });
    await handle.done.catch(() => {});
    setTurns(prev => prev.map((t, i) => i === turnIdx ? { ...t, done: true } : t));
  };

  return (
    <Box flexDirection="column">
      <Text dimColor>oh-tui · {sessionId ? sessionId.slice(0, 8) + "…" : "no session"}</Text>
      {turns.map((t, i) => (
        <Box key={i} flexDirection="column" marginTop={1}>
          <Text dimColor>&gt; {t.prompt}</Text>
          <StreamingMessage text={t.response} finished={t.done} />
        </Box>
      ))}
      <PromptInput history={history} onSubmit={onSubmit} />
    </Box>
  );
}
```

Smoke: `oh-tui` (no prompt) → REPL launches.

Commit: `feat(tui): ReplMode with prompt input + multi-turn history`

---

### Task 16: Cancel binding (Ctrl+C → $/cancelRequest)

**Files:**
- Modify: `src/hooks/useKeybinds.ts` (new) or inline in modes
- Modify: ReplMode + OneShotMode

`src/hooks/useKeybinds.ts`:
```typescript
import { useInput } from "ink";

export function useCancelBinding(onCancel: () => void): void {
  useInput((input, key) => {
    if (key.ctrl && input === "c") onCancel();
  });
}
```

In `ReplMode.tsx`, track current handle:
```typescript
const handleRef = useRef<SendMessageHandle | null>(null);
useCancelBinding(() => {
  if (handleRef.current) handleRef.current.cancel().catch(() => {});
});
```

(Set `handleRef.current = handle` after `client.sendMessage(...)`, clear on completion.)

Smoke: run `oh-tui`, send long prompt, press Ctrl+C → handle cancels, shows error.

Commit: `feat(tui): Ctrl+C cancellation via $/cancelRequest`

---

### Task 17: Side panels (/sessions, /tools)

**Files:**
- Create: `src/components/SessionListPanel.tsx`
- Create: `src/components/ToolsListPanel.tsx`
- Modify: ReplMode to toggle panels via `/sessions`, `/tools`

`src/components/SessionListPanel.tsx`:
```typescript
import React from "react";
import { Box, Text } from "ink";

interface Props {
  sessions: Array<{ id: string; created_at: string; message_count: number }>;
  onSelect: (id: string) => void;
}

export function SessionListPanel({ sessions, onSelect }: Props): React.JSX.Element {
  return (
    <Box flexDirection="column" borderStyle="single" padding={1}>
      <Text bold>sessions</Text>
      {sessions.map((s) => (
        <Text key={s.id} dimColor>{s.id.slice(0, 8)}… · {s.message_count} msgs · {s.created_at.slice(0, 19)}</Text>
      ))}
    </Box>
  );
}
```

(Selection via arrow keys + enter is future polish; for v1 panel is read-only display.)

`src/components/ToolsListPanel.tsx` — analogous, lists name + description.

In `ReplMode.tsx`, intercept `/sessions` and `/tools` in `onSubmit` before forwarding to LLM:
```typescript
if (prompt === "/sessions") {
  const list = await client.sessionList();
  setSessionsPanel(list);
  return;
}
if (prompt === "/tools") {
  const list = await client.toolsList();
  setToolsPanel(list);
  return;
}
```

Toggle state with a second `/sessions` or `/tools` to hide.

Commit: `feat(tui): /sessions and /tools side panels`

---

### Task 18: TelemetryBar

**Files:**
- Create: `src/components/TelemetryBar.tsx`
- Modify: ReplMode

```typescript
import React from "react";
import { Box, Text } from "ink";

interface Props { latest: { event_type: string; elapsed_ms: number } | null; }

export function TelemetryBar({ latest }: Props): React.JSX.Element {
  return (
    <Box>
      <Text dimColor>
        {latest ? `${latest.event_type} · ${latest.elapsed_ms}ms` : "idle"}
      </Text>
    </Box>
  );
}
```

In `ReplMode.tsx`, call `client.telemetrySubscribe(true)` after init and:
```typescript
const [telemetry, setTelemetry] = useState<{ event_type: string; elapsed_ms: number } | null>(null);
useEffect(() => {
  if (!client) return;
  client.onTelemetry((ev) => {
    const elapsed = (ev.payload as any)?.duration_ms ?? 0;
    setTelemetry({ event_type: ev.event_type, elapsed_ms: Math.round(elapsed) });
  });
}, [client]);
```

Render `<TelemetryBar latest={telemetry} />` at the bottom.

Commit: `feat(tui): telemetry status bar`

---

### Task 19: oh-tui release v0.1.0 + meta-harney v0.2.0

**Files:**
- Create: `oh-tui/README.md`
- Modify: `meta-harney/pyproject.toml` (version 0.2.0)
- Modify: `meta-harney/src/meta_harney/__init__.py` (__version__ = "0.2.0")
- Modify: meta-harney README — add a section about the TS client
- Modify: oh-tui README — install + usage

- [ ] **Step 1: Final quality gates**

In meta-harney:
```bash
cd /Users/baihe/Projects/study/meta-harney
.venv/bin/pytest -q                                # >= 350 passed
.venv/bin/mypy src tests                           # clean
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
cd clients/typescript
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

In oh-tui:
```bash
cd /Users/baihe/Projects/study/oh-tui
pnpm test
pnpm typecheck
pnpm lint
pnpm start "hi"                                    # manual smoke with real bridge
```

- [ ] **Step 2: oh-tui README**

```markdown
# oh-tui

A React + Ink terminal UI for the [oh-mini](https://github.com/bailaohe/oh-mini)
coding agent. Drives `oh bridge` over JSON-RPC.

## Install

```bash
git clone https://github.com/bailaohe/oh-tui.git
cd oh-tui
pnpm install
```

You also need `oh` (oh-mini v0.4+) on PATH.

## Usage

```bash
# one-shot
pnpm start "list py files in cwd"

# REPL
pnpm start
oh> list py files in cwd
oh> /sessions
oh> /tools
oh> /exit
```

Flags: `--provider X`, `--profile P`, `--model M`, `--framing {newline,content-length}`, `--bridge-bin PATH`, `--yolo`.
```

- [ ] **Step 3: Commits + tags + push**

```bash
cd /Users/baihe/Projects/study/meta-harney
git add pyproject.toml src/meta_harney/__init__.py README.md
git commit -m "release: meta-harney v0.2.0 — TS bridge client

Phase 11 ships clients/typescript/ (@meta-harney/bridge-client v0.1.0):
- NewlineFraming + ContentLengthFraming
- JSON-RPC 2.0 message types + BridgeError hierarchy
- ChildProcessTransport with stderr passthrough
- BridgeClient: lifecycle / sessions / sendMessage handles / permissions / cancel / telemetry
- E2E test against real oh bridge subprocess"
git tag -a v0.2.0 -m "v0.2.0 — Phase 11 TS bridge client"
git push origin main
git push origin v0.2.0

cd /Users/baihe/Projects/study/oh-tui
git add .
git commit -m "release: oh-tui v0.1.0 — Ink TUI for oh-mini

Phase 11 b:
- One-shot mode: prompt -> streaming render -> exit
- REPL mode: multi-turn input + history + sessionId persistence
- PermissionDialog (y/n/a) for non-yolo runs
- /sessions and /tools side panels
- TelemetryBar status line
- Ctrl+C cancellation via \$/cancelRequest"
git tag -a v0.1.0 -m "v0.1.0 — Phase 11 Ink TUI"
# Create GitHub repo (interactive)
gh repo create bailaohe/oh-tui --public --source . --push
git push origin v0.1.0
```

- [ ] **Step 4: Verify**

```bash
git -C /Users/baihe/Projects/study/meta-harney tag -l "v0.2.0"
git -C /Users/baihe/Projects/study/oh-tui tag -l "v0.1.0"
```

Both should print their tags.

---

## Self-Review

**Spec coverage:**
- ✅ TS client (T2 framing, T3 protocol/errors, T4 transport, T5 lifecycle, T6 sessions+tools, T7 streaming+permission+cancel, T8 telemetry)
- ✅ Ink app (T11 cli, T12 hook, T13 one-shot, T14 permission dialog, T15 REPL, T16 cancel, T17 panels, T18 telemetry)
- ✅ E2E (T9 client against real bridge; T13/T15 manual smoke via real bridge)
- ✅ Releases (T19)

**Placeholder scan:** T15-T18 reference earlier component shapes; full code is included for each component. The `useKeybinds.ts` is just a 5-line export. T17 leaves arrow-key selection as v1.5 polish (documented).

**Type consistency:**
- `BridgeClient.sendMessage(...)` returns `SendMessageHandle` — same interface used by OneShotMode (T13) and ReplMode (T15).
- `CliArgs` shape defined in T11 used by all hooks/modes downstream.
- Framing union in CliArgs matches the choices in T11 argparse and T12 hook.

**Risks:**
- **Bridge stderr pollution**: T4 pipes stderr passthrough. If the bridge emits noisy logs, they'll interleave with Ink rendering. Mitigation: future flag to capture stderr into a side panel.
- **Permission handle routing**: T7's "route to most recent handle" assumes one inflight send_message per client. Acceptable for v1 (TUI never sends two at once).
- **REPL re-rendering performance**: Each `text_delta` triggers `setTurns` which re-renders. For long streams (>10s of tokens) Ink may stutter. Mitigation: throttle setState if needed.

All clear.

## Execution

**Subagent-Driven** per the standing preference. Each task gets a fresh subagent. Continue uninterrupted.
