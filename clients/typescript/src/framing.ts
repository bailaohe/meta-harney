import type { Readable, Writable } from "node:stream";

/**
 * Framing strategy for length-delimited messages over a Node stream.
 *
 * Mirrors the Phase 10 Python framing layer:
 *   - NewlineFraming: payload terminated by '\n' (LF; CRLF tolerated)
 *   - ContentLengthFraming: HTTP-style `Content-Length` header + blank line + body
 *
 * Each framing instance maintains a per-reader buffer so that successive
 * `readMessage` calls share state across the underlying stream. Do not share
 * a single framing instance across multiple reader streams.
 */
export interface Framing {
  /** Read one framed message. Resolves to the payload or null on EOF. */
  readMessage(reader: Readable): Promise<Buffer | null>;
  /** Write one framed message, awaiting backpressure drain if needed. */
  writeMessage(writer: Writable, payload: Buffer): Promise<void>;
}

const LF = 0x0a;
const CR = 0x0d;
const COLON = 0x3a;

/**
 * Per-reader buffered chunk source. Holds onto trailing bytes between
 * `readMessage` calls so we never depend on `Readable.unshift` re-triggering
 * data events (which is unreliable once listeners have been detached).
 */
class BufferedReader {
  private buf: Buffer = Buffer.alloc(0);
  private ended = false;
  private err: Error | null = null;
  private waiters: Array<() => void> = [];
  private attached: Readable | null = null;
  private onData = (chunk: Buffer): void => {
    this.buf = Buffer.concat([this.buf, Buffer.from(chunk)]);
    this.wake();
  };
  private onEnd = (): void => {
    this.ended = true;
    this.wake();
  };
  private onErr = (e: Error): void => {
    this.err = e;
    this.wake();
  };

  attach(reader: Readable): void {
    if (this.attached === reader) return;
    if (this.attached !== null) {
      throw new Error("BufferedReader already attached to a different stream");
    }
    this.attached = reader;
    reader.on("data", this.onData);
    reader.on("end", this.onEnd);
    reader.on("error", this.onErr);
  }

  private wake(): void {
    const ws = this.waiters;
    this.waiters = [];
    for (const w of ws) w();
  }

  private wait(): Promise<void> {
    return new Promise<void>((resolve) => {
      this.waiters.push(resolve);
    });
  }

  /** Read exactly n bytes. Throws on premature EOF. */
  async readExact(n: number): Promise<Buffer> {
    if (n === 0) return Buffer.alloc(0);
    while (this.buf.length < n) {
      if (this.err !== null) throw this.err;
      if (this.ended) {
        throw new Error(`unexpected EOF: needed ${n}, got ${this.buf.length}`);
      }
      await this.wait();
    }
    const out = this.buf.subarray(0, n);
    this.buf = this.buf.subarray(n);
    return Buffer.from(out);
  }

  /**
   * Read until (and consuming) the next LF byte. Returns the line without
   * its trailing LF, or null if EOF was reached with no data buffered.
   * If EOF arrives with a partial line, that partial line is returned.
   */
  async readLine(): Promise<Buffer | null> {
    for (;;) {
      const nl = this.buf.indexOf(LF);
      if (nl !== -1) {
        const line = this.buf.subarray(0, nl);
        this.buf = this.buf.subarray(nl + 1);
        return Buffer.from(line);
      }
      if (this.err !== null) throw this.err;
      if (this.ended) {
        if (this.buf.length === 0) return null;
        const rest = this.buf;
        this.buf = Buffer.alloc(0);
        return Buffer.from(rest);
      }
      await this.wait();
    }
  }

  /**
   * True if no bytes are buffered AND the stream has ended (no more to come).
   */
  isCleanEof(): boolean {
    return this.ended && this.buf.length === 0 && this.err === null;
  }
}

const readers = new WeakMap<Readable, BufferedReader>();

function bufferedReaderFor(reader: Readable): BufferedReader {
  let br = readers.get(reader);
  if (br === undefined) {
    br = new BufferedReader();
    br.attach(reader);
    readers.set(reader, br);
  }
  return br;
}

export class NewlineFraming implements Framing {
  async readMessage(reader: Readable): Promise<Buffer | null> {
    const br = bufferedReaderFor(reader);
    const line = await br.readLine();
    if (line === null) return null;
    return stripTrailingCR(line);
  }

  async writeMessage(writer: Writable, payload: Buffer): Promise<void> {
    await writeAndDrain(writer, Buffer.concat([payload, Buffer.from("\n")]));
  }
}

export class ContentLengthFraming implements Framing {
  async readMessage(reader: Readable): Promise<Buffer | null> {
    const br = bufferedReaderFor(reader);
    const headers = await readHeaders(br);
    if (headers === null) return null;
    const lenStr = headers.get("content-length");
    if (lenStr === undefined) throw new Error("missing Content-Length header");
    const n = parseInt(lenStr, 10);
    if (!Number.isFinite(n) || n < 0) {
      throw new Error(`invalid Content-Length: ${lenStr}`);
    }
    return await br.readExact(n);
  }

  async writeMessage(writer: Writable, payload: Buffer): Promise<void> {
    const header = Buffer.from(
      `Content-Length: ${payload.length}\r\n\r\n`,
      "ascii",
    );
    await writeAndDrain(writer, Buffer.concat([header, payload]));
  }
}

function stripTrailingCR(b: Buffer): Buffer {
  if (b.length > 0 && b[b.length - 1] === CR) return b.subarray(0, b.length - 1);
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

async function readHeaders(
  br: BufferedReader,
): Promise<Map<string, string> | null> {
  const headers = new Map<string, string>();
  let sawAny = false;
  for (;;) {
    const line = await br.readLine();
    if (line === null) {
      if (!sawAny) return null;
      throw new Error("unexpected EOF while reading headers");
    }
    sawAny = true;
    const clean = stripTrailingCR(line);
    if (clean.length === 0) {
      // Blank line terminates headers.
      return headers;
    }
    const sep = clean.indexOf(COLON);
    if (sep === -1) continue;
    const k = clean.subarray(0, sep).toString("ascii").trim().toLowerCase();
    const v = clean.subarray(sep + 1).toString("ascii").trim();
    headers.set(k, v);
  }
}
