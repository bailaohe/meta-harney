import { describe, it, expect } from "vitest";
import { ChildProcessTransport } from "../src/transport.js";
import { NewlineFraming, ContentLengthFraming } from "../src/framing.js";

describe("ChildProcessTransport", () => {
  it("spawns, writes, reads, exits", async () => {
    // Echo back stdin line-by-line on stdout.
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "process.stdin.on('data', d => process.stdout.write(d));"],
      framing: new NewlineFraming(),
    });
    await transport.start();
    expect(transport.isAlive()).toBe(true);
    await transport.write(Buffer.from('{"hi":1}'));
    const msg = await transport.read();
    expect(msg?.toString()).toBe('{"hi":1}');
    await transport.stop();
    expect(transport.isAlive()).toBe(false);
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

  it("works with ContentLengthFraming", async () => {
    // Echo subprocess that copies stdin -> stdout (header + body together).
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "process.stdin.on('data', d => process.stdout.write(d));"],
      framing: new ContentLengthFraming(),
    });
    await transport.start();
    await transport.write(Buffer.from('{"a":42}'));
    const msg = await transport.read();
    expect(msg?.toString()).toBe('{"a":42}');
    await transport.stop();
  });

  it("rejects start() when already started", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "setTimeout(() => {}, 10000);"],
      framing: new NewlineFraming(),
    });
    await transport.start();
    await expect(transport.start()).rejects.toThrow(/already started/);
    await transport.stop(1000);
  });

  it("read() throws when not started", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", ""],
      framing: new NewlineFraming(),
    });
    await expect(transport.read()).rejects.toThrow(/not started/);
  });

  it("write() throws when not started", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", ""],
      framing: new NewlineFraming(),
    });
    await expect(transport.write(Buffer.from("x"))).rejects.toThrow(/not started/);
  });

  it("stop() returns null when never started", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", ""],
      framing: new NewlineFraming(),
    });
    expect(await transport.stop()).toBeNull();
  });

  it("isAlive() is false before start and after exit", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: ["-e", "process.exit(0);"],
      framing: new NewlineFraming(),
    });
    expect(transport.isAlive()).toBe(false);
    await transport.start();
    // Wait for the child to exit.
    await transport.read();
    // exitCode should now be set; give the event loop a tick to settle.
    await new Promise((r) => setTimeout(r, 20));
    expect(transport.isAlive()).toBe(false);
    await transport.stop();
  });

  it("stop() SIGKILLs a process that refuses to exit on stdin close", async () => {
    // Child ignores stdin end and sleeps forever; stop() must SIGKILL it.
    const transport = new ChildProcessTransport({
      command: "node",
      args: [
        "-e",
        // Resume stdin but never end; keep the loop alive.
        "process.stdin.resume(); setInterval(() => {}, 1000);",
      ],
      framing: new NewlineFraming(),
    });
    await transport.start();
    const start = Date.now();
    const code = await transport.stop(200);
    const elapsed = Date.now() - start;
    // Killed by signal -> exit code is null on Node when terminated by signal.
    expect(code === null || typeof code === "number").toBe(true);
    // Should not block much longer than the timeout.
    expect(elapsed).toBeLessThan(2000);
  });

  it("passes env vars to the child", async () => {
    const transport = new ChildProcessTransport({
      command: "node",
      args: [
        "-e",
        "process.stdout.write(process.env.MH_TEST_VAR + '\\n');",
      ],
      env: { ...process.env, MH_TEST_VAR: "hello-bridge" },
      framing: new NewlineFraming(),
    });
    await transport.start();
    const msg = await transport.read();
    expect(msg?.toString()).toBe("hello-bridge");
    await transport.stop();
  });
});
