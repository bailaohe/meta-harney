/**
 * ChildProcessTransport — spawn a bridge child process and shuttle framed
 * messages over its stdio.
 *
 * Mirrors the Phase 10 Python transport layer:
 *   - `start()` spawns the process with piped stdin/stdout/stderr.
 *   - `read()` / `write()` delegate to a `Framing` strategy.
 *   - `stop()` ends stdin gracefully, escalating to SIGKILL on timeout.
 *   - `isAlive()` reports whether the child is still running.
 *
 * Stderr is piped through to the parent's stderr by default so a misbehaving
 * bridge surfaces its diagnostics; opt out via `stderrPassthrough: false` for
 * tests that need silence.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { Framing } from "./framing.js";

export interface TransportOptions {
  /** Executable to spawn (e.g. "node", "python3"). */
  command: string;
  /** Arguments passed to the executable. */
  args?: string[];
  /** Environment for the child. Defaults to `process.env`. */
  env?: NodeJS.ProcessEnv;
  /** Working directory for the child. */
  cwd?: string;
  /** Framing strategy used for read/write. */
  framing: Framing;
  /** Pipe child stderr to parent stderr. Default: true. */
  stderrPassthrough?: boolean;
}

export class ChildProcessTransport {
  private proc: ChildProcessWithoutNullStreams | null = null;
  private readonly options: TransportOptions;
  private readonly framing: Framing;

  constructor(options: TransportOptions) {
    this.options = options;
    this.framing = options.framing;
  }

  /**
   * Spawn the child process. Throws if already started.
   *
   * `start` is async by design even though `spawn` is synchronous: it keeps
   * the transport lifecycle symmetric (`start`/`read`/`write`/`stop` all
   * return promises) and leaves room for future readiness handshakes.
   */
  // eslint-disable-next-line @typescript-eslint/require-await
  async start(): Promise<void> {
    if (this.proc !== null) {
      throw new Error("ChildProcessTransport already started");
    }
    const spawnOpts: {
      env: NodeJS.ProcessEnv;
      cwd?: string;
      stdio: ["pipe", "pipe", "pipe"];
    } = {
      env: this.options.env ?? process.env,
      stdio: ["pipe", "pipe", "pipe"],
    };
    if (this.options.cwd !== undefined) spawnOpts.cwd = this.options.cwd;
    const proc = spawn(this.options.command, this.options.args ?? [], spawnOpts);
    this.proc = proc;

    // Avoid unhandled 'error' events crashing the process; surface via stderr.
    proc.on("error", (err) => {
      // Best-effort logging; tests can override stderrPassthrough to silence.
      if (this.options.stderrPassthrough !== false) {
        process.stderr.write(
          `ChildProcessTransport: spawn error: ${err.message}\n`,
        );
      }
    });

    const stderrPassthrough = this.options.stderrPassthrough ?? true;
    if (stderrPassthrough) {
      proc.stderr.pipe(process.stderr);
    } else {
      // Drain stderr so the child doesn't block on a full pipe buffer.
      proc.stderr.resume();
    }
  }

  /** Read one framed message. Resolves to null on clean EOF. */
  async read(): Promise<Buffer | null> {
    if (this.proc === null) {
      throw new Error("ChildProcessTransport not started");
    }
    return await this.framing.readMessage(this.proc.stdout);
  }

  /** Write one framed message, awaiting backpressure drain if needed. */
  async write(payload: Buffer): Promise<void> {
    if (this.proc === null) {
      throw new Error("ChildProcessTransport not started");
    }
    await this.framing.writeMessage(this.proc.stdin, payload);
  }

  /**
   * Stop the child:
   *   1. End stdin gracefully so well-behaved bridges can shut down on EOF.
   *   2. If the child does not exit within `timeoutMs`, send SIGKILL.
   *
   * Returns the child's exit code (number) or null when terminated by signal.
   * Returns null if the transport was never started.
   */
  async stop(timeoutMs = 5000): Promise<number | null> {
    if (this.proc === null) return null;
    const proc = this.proc;
    // Detach so subsequent calls are no-ops and isAlive() reports false.
    this.proc = null;

    // If the child already exited, just resolve with its code.
    if (proc.exitCode !== null || proc.signalCode !== null) {
      return proc.exitCode;
    }

    try {
      proc.stdin.end();
    } catch {
      // stdin may already be closed; ignore.
    }

    return await new Promise<number | null>((resolve) => {
      const timer = setTimeout(() => {
        try {
          proc.kill("SIGKILL");
        } catch {
          // Process may have exited between the timeout firing and the kill.
        }
      }, timeoutMs);
      proc.once("exit", (code) => {
        clearTimeout(timer);
        resolve(code);
      });
    });
  }

  /** True iff the child is spawned and has not yet exited. */
  isAlive(): boolean {
    return (
      this.proc !== null &&
      this.proc.exitCode === null &&
      this.proc.signalCode === null
    );
  }
}
