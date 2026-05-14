/**
 * E2E: spawn a real `oh bridge` subprocess and drive the full lifecycle
 * through BridgeClient. Proves the TS client speaks the same protocol the
 * Phase 10 Python server actually emits — unit tests here use a FakeTransport
 * so they validate framing/dispatch logic but cannot catch wire-shape drift.
 *
 * Environment hardening:
 *   - HOME pinned to /tmp/oh-tui-test-<rand>/ so the bridge's
 *     ~/.oh-mini/sessions/ landing zone is a throwaway dir.
 *   - OH_MINI_FORCE_FILE_BACKEND=1 routes credential storage to the file
 *     backend (bypasses the OS keyring entirely).
 *   - OH_MINI_TEST_FAKE_PROVIDER=1 swaps in meta_harney.testing.FakeLLMProvider
 *     so no real model is contacted.
 *   - Parent env's *_API_KEY vars are stripped and replaced with a single
 *     fake DEEPSEEK_API_KEY so CredentialResolver doesn't pull in real creds.
 *
 * Discovery: honors $OH_BIN, otherwise falls back to the oh-mini editable
 * venv install. If neither is found we `it.skip` — the test is informative
 * only when a real `oh` binary is reachable.
 */

import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  BridgeClient,
  ChildProcessTransport,
  NewlineFraming,
} from "../src/index.js";

function locateOh(): string | null {
  const explicit = process.env.OH_BIN;
  if (explicit !== undefined && explicit.length > 0 && existsSync(explicit)) {
    return explicit;
  }
  const fallback = "/Users/baihe/Projects/study/oh-mini/.venv/bin/oh";
  if (existsSync(fallback)) return fallback;
  return null;
}

const ohBin = locateOh();
const itGated = ohBin !== null ? it : it.skip;

describe("E2E real oh bridge", () => {
  itGated(
    "full lifecycle with FakeProvider",
    async () => {
      // Strip any real *_API_KEY values so the subprocess can't accidentally
      // pick up the parent's credentials. Inject a single fake key matching
      // the chosen provider so CredentialResolver is satisfied.
      const sanitized: NodeJS.ProcessEnv = {};
      for (const [k, v] of Object.entries(process.env)) {
        if (!k.endsWith("_API_KEY")) sanitized[k] = v;
      }
      const home = mkdtempSync(join(tmpdir(), "oh-tui-test-"));
      const env: NodeJS.ProcessEnv = {
        ...sanitized,
        HOME: home,
        OH_MINI_TEST_FAKE_PROVIDER: "1",
        OH_MINI_FORCE_FILE_BACKEND: "1",
        DEEPSEEK_API_KEY: "sk-fake",
      };

      const transport = new ChildProcessTransport({
        // ohBin is non-null inside the gated branch.
        command: ohBin as string,
        args: ["bridge", "--provider", "deepseek", "--yolo"],
        framing: new NewlineFraming(),
        env,
        // Silence the bridge's stderr in test output unless something breaks.
        stderrPassthrough: false,
      });
      const client = new BridgeClient({ transport });
      await client.start();

      try {
        const init = await client.initialize({
          clientInfo: { name: "e2e-test", version: "0" },
        });
        expect(init.server_info.name).toBe("oh-mini-bridge");

        const tools = await client.toolsList();
        expect(tools.map((t) => t.name)).toContain("bash");

        const { id } = await client.sessionCreate();
        const handle = client.sendMessage(id, {
          role: "user",
          content: [{ type: "text", text: "hi" }],
        });

        const events: unknown[] = [];
        handle.onEvent((e) => events.push(e));
        const final = await handle.done;
        expect(final.stopped_reason).toBe("completed");
        expect(events.length).toBeGreaterThan(0);

        await client.shutdown();
        await client.exit();
      } catch (e) {
        // Best-effort cleanup so a hung subprocess doesn't keep the test
        // runner alive when an assertion fails mid-flight.
        await client.exit().catch(() => {
          /* swallow */
        });
        throw e;
      }
    },
    15000,
  );
});
