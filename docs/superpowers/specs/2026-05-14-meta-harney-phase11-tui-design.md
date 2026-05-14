# Phase 11 — TS bridge client + oh-tui (Ink) frontend

## Goal

Ship the visible product: a React + Ink terminal UI that drives `oh bridge`
end-to-end. Factor out the generic JSON-RPC client (protocol + transport +
permission/cancel/telemetry plumbing) into meta-harney's TS client package so
future React-Native / VSCode / Go-CLI clients can reuse it.

## Two deliverables, one phase

### 11a: `@meta-harney/bridge-client` (TypeScript, lives in meta-harney)

Path: `meta-harney/clients/typescript/`

Generic JSON-RPC 2.0 client mirroring Phase 10's Python server. Spawns a
child process, frames bytes, dispatches messages, exposes high-level handles
for sessions, streaming, permissions, cancel, telemetry. Has NO Ink, NO
React, NO oh-mini imports.

### 11b: `oh-tui` (Ink app, new repo)

Path: `oh-tui/` (new repo at `/Users/baihe/Projects/study/oh-tui/`)

React + Ink CLI. Consumes `@meta-harney/bridge-client` via a workspace /
file link. Owns all UX:
- Prompt input + history
- Streaming markdown render
- Permission Y/N/A dialog
- Session list panel (`/sessions`)
- Tools list panel (`/tools`)
- Telemetry status bar
- Ctrl+C → `$/cancelRequest`

## Stack

| | Choice | Reason |
|---|---|---|
| Package manager | **pnpm** | Workspace support, fast, deterministic lockfile |
| Language | **TypeScript 5.x (strict)** | Mirror Python mypy strict discipline |
| Runtime | **Node 18+ LTS** | ESM default, fetch built-in, stable |
| Module format | **ESM only** | No CommonJS dual builds |
| Build (lib) | **tsup** | Simple, fast, dual-output unnecessary (ESM only) |
| Build (app) | **direct tsx run** | oh-tui ships sources + `bin` shebang, no bundle needed for v1 |
| Testing | **vitest + ink-testing-library** | Co-located test files, fast, Ink-aware |
| Linting | **eslint + prettier** | Standard. eslint: TypeScript + React rules; prettier: format |
| TS target | **ES2022** | Modern Node features available |

## 11a: TS bridge client architecture

```
src/
├── framing.ts          # NewlineFraming + ContentLengthFraming
├── protocol.ts         # JsonRpc{Request,Response,Notification,Error} types
├── errors.ts           # BridgeError hierarchy
├── transport.ts        # ChildProcessTransport (spawn + stdin/stdout)
├── client.ts           # BridgeClient class (high-level API)
├── types.ts            # Re-exports of method param/result shapes
└── index.ts            # Public API
```

### BridgeClient public API

```typescript
import { BridgeClient, NewlineFraming } from "@meta-harney/bridge-client";

const client = new BridgeClient({
  command: "oh",
  args: ["bridge", "--provider", "deepseek"],
  framing: new NewlineFraming(),
});

await client.start();
const init = await client.initialize({ clientInfo: { name: "oh-tui", version: "0.1.0" } });

// Sessions
const { id } = await client.sessionCreate();
const list = await client.sessionList();
const detail = await client.sessionLoad(id);

// Streaming
const handle = client.sendMessage(id, { role: "user", content: [{ type: "text", text: "hi" }] });
handle.onEvent((ev) => render(ev));
handle.onPermissionRequest(async (req) => ({ decision: await askUser(req) }));
const final = await handle.done; // { stopped_reason }
handle.cancel(); // sends $/cancelRequest

// Telemetry
await client.telemetrySubscribe(true);
client.onTelemetry((ev) => updateStatusBar(ev));

// Lifecycle
await client.shutdown();
client.exit();
```

### Permission flow API

`SendMessageHandle.onPermissionRequest(handler)` registers an async function
that returns a decision. When the bridge sends `permission/request`, the
client routes it to the handler and replies automatically. Default if no
handler: deny everything.

### Cancellation

`handle.cancel()` sends `$/cancelRequest` notification. The promise from
`handle.done` rejects with `BridgeCancelled` error.

### Transport

`ChildProcessTransport` spawns the bridge as a Node child process (`spawn`
from `node:child_process`). Reads `stdout`, writes `stdin`. stderr is
piped to the host's stderr (preserves the bridge's human logs).

Closing protocol: client `shutdown()` then `exit()` waits up to a configurable
timeout (default 5s) for clean exit; otherwise force kills.

## 11b: oh-tui architecture

```
src/
├── App.tsx                 # Top-level Ink app, mode router (one-shot | repl)
├── modes/
│   ├── OneShotMode.tsx     # Single prompt → stream → exit
│   └── ReplMode.tsx        # Input loop + history
├── components/
│   ├── PromptInput.tsx     # Multi-line text input (uses ink-text-input)
│   ├── StreamingMessage.tsx # Accumulates text_delta, renders Markdown
│   ├── ToolUseBadge.tsx    # Shows tool invocations inline
│   ├── PermissionDialog.tsx # Y/N/A popup, captures key
│   ├── SessionListPanel.tsx # Toggleable side panel
│   ├── ToolsListPanel.tsx   # Toggleable side panel
│   └── TelemetryBar.tsx    # Bottom status line
├── hooks/
│   ├── useBridgeClient.ts  # Lazy-init singleton, cleanup on unmount
│   ├── useStreaming.ts     # Wraps SendMessageHandle into React state
│   └── useKeybinds.ts      # Ctrl+C, /sessions, /tools, escape, etc.
├── lib/
│   ├── markdown.ts         # Ink-friendly markdown rendering (code blocks, lists)
│   └── locate-bridge.ts    # Resolves `oh` executable (PATH / explicit flag)
└── cli.tsx                 # entry: parse argv, render <App />
```

### CLI flags (oh-tui)

```
oh-tui [prompt]                  # one-shot if positional; REPL if absent
  --provider X                   # forwarded to oh bridge
  --profile P
  --model M
  --framing F                    # newline (default) | content-length
  --bridge-bin PATH              # override `oh` location
  --bridge-args "..."            # extra args appended to bridge spawn
  --yolo                         # bridge runs with --yolo; permission dialog never appears
```

### UX flows

**One-shot mode** (`oh-tui "task"`):
```
┌──────────────────────────────────────────────────────────────┐
│ oh-tui · deepseek · session 1a7c...                         │
├──────────────────────────────────────────────────────────────┤
│ > task                                                       │
│                                                              │
│ Reading file_read path=src/oh_mini/cli.py limit=20...       │
│                                                              │
│ ## Summary                                                   │
│ The CLI module dispatches subcommands…                       │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ ⏳ llm.requested  ◷ 2.3s                                     │
└──────────────────────────────────────────────────────────────┘
```

**REPL mode** (`oh-tui`):
- Bottom prompt input box, history with up/down keys
- Scrollback shows previous turns
- `/sessions` opens side panel
- `/tools` opens side panel
- `/exit` quits
- Ctrl+C cancels in-flight; double Ctrl+C exits

**Permission dialog** (overlay, modal):
```
┌─ permission required ──────────────────────────────────────┐
│ tool: bash                                                 │
│ args: { command: "echo hello-from-bash" }                  │
│                                                            │
│ [y] allow  [n] deny  [a] allow_always                      │
└────────────────────────────────────────────────────────────┘
```

## Out of scope (deferred)

- npm publish of `@meta-harney/bridge-client` (use file: link for now)
- Browser / web client (only Node terminal)
- Authentication / process trust
- Multi-bridge concurrent (one client per BridgeClient instance)
- Theming / colour customization
- Persistent settings beyond what oh-mini already stores
- WebSocket transport
- Windows-specific testing (focus macOS + Linux)

## Versioning

- `meta-harney` bumps `0.1.0` → **`0.2.0`** (new TS client subdir, no Python API change)
- `@meta-harney/bridge-client` version `0.1.0` (first release; lives under meta-harney/clients/typescript)
- `oh-tui` version `0.1.0` (new repo, new package)

## Acceptance

1. `pnpm install` in meta-harney/clients/typescript succeeds; `pnpm test` 100% green
2. `pnpm install` in oh-tui succeeds; `pnpm test` 100% green
3. `oh-tui "list py files in cwd"` (one-shot) spawns `oh bridge`, streams the
   response, exits 0 — verified manually with real deepseek
4. `oh-tui` (REPL) launches, accepts input, renders streaming response,
   `/exit` quits cleanly
5. Permission dialog appears for `bash` tool when not in `--yolo`; choosing
   `y` proceeds, `n` denies (LLM gets the deny and adjusts)
6. `Ctrl+C` mid-stream sends `$/cancelRequest`; UI shows "cancelled"
7. `/sessions` shows previous sessions; selecting one resumes via `session.load`
8. `/tools` shows the 10 oh-mini tools with descriptions
9. Telemetry bar updates with current event type + elapsed time
10. mypy n/a (TS), but TypeScript strict mode + eslint clean for both packages
11. README in both packages
12. Tag `v0.2.0` in meta-harney, push; tag `v0.1.0` in new oh-tui repo, push

## Risk callouts

- **Ink + async permission roundtrip**: permission dialog needs to suspend
  stream rendering until user decides. Mitigation: `useStreaming` state machine
  has explicit "awaiting_permission" state; dialog component reads/sets it
- **Markdown in Ink**: Ink renders nested boxes, not arbitrary HTML. Mitigation:
  ship a minimal "renderable subset" — code blocks via `<Text dim>`,
  lists via indented `<Text>`. No real markdown parser in v1; just our subset.
- **stderr from bridge**: oh-mini's bridge may emit logs to stderr (e.g.
  internal errors). Mitigation: pipe to oh-tui stderr unaltered. Optional flag
  later to capture and display in a panel.
- **Bridge crash mid-stream**: child process can die. Mitigation: client emits
  `disconnected` event; UI shows error banner + offers `/restart`.
- **pnpm workspace + meta-harney monorepo**: meta-harney is primarily a Python
  package. Adding `clients/typescript/` should NOT affect Python builds. Verify
  by running existing pytest + mypy after T1.
