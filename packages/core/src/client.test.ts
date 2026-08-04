import { describe, expect, it } from "vitest";
import { PageCapClient } from "./client";

const BASE = "http://127.0.0.1:8765";
const TOKEN = "tok-123/abc+def";

describe("URL builders without a token", () => {
  const client = new PageCapClient(BASE);

  it("builds a download URL", () => {
    expect(client.downloadUrl("j1", "photo.jpg")).toBe(`${BASE}/jobs/j1/download/photo.jpg`);
  });

  it("percent-encodes the filename", () => {
    expect(client.downloadUrl("j1", "my file&x.jpg")).toBe(
      `${BASE}/jobs/j1/download/my%20file%26x.jpg`,
    );
  });

  it("builds a preview URL", () => {
    expect(client.previewUrl("j1", "a.png")).toBe(`${BASE}/jobs/j1/preview/a.png`);
  });

  it("builds a zip URL", () => {
    expect(client.downloadAllUrl("j1")).toBe(`${BASE}/jobs/j1/download-all`);
  });
});

describe("URL builders with a token", () => {
  const client = new PageCapClient(BASE, TOKEN);

  it("appends the token to browser-fetched URLs, which cannot send headers", () => {
    expect(client.downloadUrl("j1", "a.png")).toBe(
      `${BASE}/jobs/j1/download/a.png?token=tok-123%2Fabc%2Bdef`,
    );
    expect(client.previewUrl("j1", "a.png")).toBe(
      `${BASE}/jobs/j1/preview/a.png?token=tok-123%2Fabc%2Bdef`,
    );
    expect(client.downloadAllUrl("j1")).toBe(
      `${BASE}/jobs/j1/download-all?token=tok-123%2Fabc%2Bdef`,
    );
  });

  it("url-encodes the token so slashes and plus signs survive", () => {
    const url = client.downloadUrl("j1", "a.png");
    expect(url).not.toContain("tok-123/abc+def");
    expect(new URL(url).searchParams.get("token")).toBe(TOKEN);
  });
});

describe("watchJob", () => {
  it("derives a ws:// URL from the http base and carries the token", () => {
    const captured: string[] = [];
    class FakeWebSocket {
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      constructor(url: string) {
        captured.push(url);
      }
      close() {}
    }
    const original = globalThis.WebSocket;
    // @ts-expect-error test double
    globalThis.WebSocket = FakeWebSocket;
    try {
      new PageCapClient(BASE, TOKEN).watchJob("j1", () => {});
      expect(captured[0]).toBe(`ws://127.0.0.1:8765/ws/j1?token=tok-123%2Fabc%2Bdef`);
    } finally {
      globalThis.WebSocket = original;
    }
  });

  it("closes the socket once the job reaches a terminal state", () => {
    let closed = false;
    let handler: ((e: MessageEvent) => void) | null = null;
    class FakeWebSocket {
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      constructor(_url: string) {}
      close() {
        closed = true;
      }
    }
    const original = globalThis.WebSocket;
    // @ts-expect-error test double
    globalThis.WebSocket = FakeWebSocket;
    try {
      const ws = new PageCapClient(BASE).watchJob("j1", () => {});
      handler = (ws as unknown as FakeWebSocket).onmessage;
      handler?.({ data: JSON.stringify({ status: "running" }) } as MessageEvent);
      expect(closed).toBe(false);
      handler?.({ data: JSON.stringify({ status: "done" }) } as MessageEvent);
      expect(closed).toBe(true);
    } finally {
      globalThis.WebSocket = original;
    }
  });

  it("ignores malformed frames instead of throwing", () => {
    class FakeWebSocket {
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      constructor(_url: string) {}
      close() {}
    }
    const original = globalThis.WebSocket;
    // @ts-expect-error test double
    globalThis.WebSocket = FakeWebSocket;
    try {
      const updates: unknown[] = [];
      const ws = new PageCapClient(BASE).watchJob("j1", (s) => updates.push(s));
      expect(() =>
        (ws as unknown as FakeWebSocket).onmessage?.({ data: "not json" } as MessageEvent),
      ).not.toThrow();
      expect(updates).toEqual([]);
    } finally {
      globalThis.WebSocket = original;
    }
  });
});
