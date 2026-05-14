import { describe, it, expect } from "vitest";
import { Readable, Writable } from "node:stream";
import { NewlineFraming, ContentLengthFraming, type Framing } from "../src/framing.js";

function collectingStream(): { stream: Writable; bytes: () => Buffer } {
  const chunks: Buffer[] = [];
  const stream = new Writable({
    write(chunk, _enc, cb) {
      chunks.push(Buffer.from(chunk));
      cb();
    },
  });
  return { stream, bytes: () => Buffer.concat(chunks) };
}

async function readableOf(buf: Buffer): Promise<Readable> {
  const s = new Readable({ read() {} });
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

  it("handles CRLF line endings", async () => {
    const f: Framing = new NewlineFraming();
    const reader = await readableOf(Buffer.from('{"a":1}\r\n{"b":2}\r\n'));
    const a = await f.readMessage(reader);
    const b = await f.readMessage(reader);
    expect(a?.toString()).toBe('{"a":1}');
    expect(b?.toString()).toBe('{"b":2}');
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

  it("parses Content-Length case-insensitively", async () => {
    const f: Framing = new ContentLengthFraming();
    const buf = Buffer.from(`content-LENGTH: 7\r\n\r\n{"a":1}`);
    const reader = await readableOf(buf);
    expect((await f.readMessage(reader))?.toString()).toBe('{"a":1}');
  });
});
