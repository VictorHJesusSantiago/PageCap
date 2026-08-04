import { describe, expect, it, vi, beforeEach } from "vitest";
import { JobState } from "@pagecap/core";
import { act, renderHook, waitFor } from "../test/render";

vi.mock("../apiClient", () => ({
  client: {
    startExtraction: vi.fn(),
    getJob: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(undefined),
    pauseJob: vi.fn().mockResolvedValue(undefined),
    resumeJob: vi.fn().mockResolvedValue(undefined),
    watchJob: vi.fn(),
    downloadUrl: (j: string, f: string) => `/dl/${j}/${f}`,
    downloadAllUrl: (j: string) => `/zip/${j}`,
    previewUrl: (j: string, f: string) => `/pv/${j}/${f}`,
  },
}));

import { client } from "../apiClient";
import { useExtraction } from "./useExtraction";

function job(overrides: Partial<JobState> = {}): JobState {
  return {
    job_id: "j1",
    status: "running",
    url: "https://example.com",
    progress: 0,
    total: 0,
    message: "",
    files: [],
    created_at: 1,
    updated_at: 1,
    ...overrides,
  } as JobState;
}

function stubWatch() {
  const socket = { close: vi.fn() };
  let onUpdate: ((s: JobState) => void) | undefined;
  let onError: (() => void) | undefined;
  vi.mocked(client.watchJob).mockImplementation((_id, update, error) => {
    onUpdate = update;
    onError = error as () => void;
    return socket as unknown as WebSocket;
  });
  return {
    socket,
    push: (s: JobState) => act(() => onUpdate?.(s)),
    fail: () => act(() => onError?.()),
  };
}

beforeEach(() => {
  vi.mocked(client.startExtraction).mockResolvedValue({ job_id: "j1", status: "queued" });
});

describe("starting a job", () => {
  it("begins idle", () => {
    const { result } = renderHook(() => useExtraction());
    expect(result.current.phase).toBe("idle");
    expect(result.current.job).toBeNull();
  });

  it("moves to running and opens the WebSocket", async () => {
    stubWatch();
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    expect(result.current.phase).toBe("running");
    expect(client.watchJob).toHaveBeenCalledWith("j1", expect.any(Function), expect.any(Function));
  });

  it("ignores a second start while one is in flight", async () => {
    stubWatch();
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.start({ url: "https://a.example" } as never);
    });
    await act(async () => {
      await result.current.start({ url: "https://b.example" } as never);
    });

    expect(client.startExtraction).toHaveBeenCalledOnce();
  });

  it("surfaces a connection failure as an error phase with a message", async () => {
    vi.mocked(client.startExtraction).mockRejectedValue(new Error("ECONNREFUSED"));
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    expect(result.current.phase).toBe("error");
    expect(result.current.job?.error).toBe("ECONNREFUSED");
    expect(result.current.job?.status).toBe("error");
  });
});

describe("live updates", () => {
  it("maps each job status onto the right phase", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    watch.push(job({ status: "queued" }));
    expect(result.current.phase).toBe("running");

    watch.push(job({ status: "waiting_captcha" }));
    expect(result.current.phase).toBe("running");

    watch.push(job({ status: "done", progress: 100 }));
    expect(result.current.phase).toBe("done");
  });

  it("treats a cancelled job as done, not as an error", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    watch.push(job({ status: "cancelled" }));
    expect(result.current.phase).toBe("done");
  });

  it("maps an errored job to the error phase", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    watch.push(job({ status: "error", error: "boom" }));
    expect(result.current.phase).toBe("error");
    expect(result.current.job?.error).toBe("boom");
  });

  it("reports a socket error", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    watch.fail();
    expect(result.current.phase).toBe("error");
  });
});

describe("controls", () => {
  it("cancels the current job and returns to idle", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    act(() => result.current.cancel());
    expect(client.cancelJob).toHaveBeenCalledWith("j1");
    expect(watch.socket.close).toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
  });

  it("pauses and resumes the current job", async () => {
    stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    act(() => result.current.pause());
    expect(client.pauseJob).toHaveBeenCalledWith("j1");

    act(() => result.current.resume());
    expect(client.resumeJob).toHaveBeenCalledWith("j1");
  });

  it("does nothing when pausing with no active job", () => {
    const { result } = renderHook(() => useExtraction());
    act(() => result.current.pause());
    expect(client.pauseJob).not.toHaveBeenCalled();
  });

  it("swallows a rejected cancel so the UI still resets", async () => {
    stubWatch();
    vi.mocked(client.cancelJob).mockRejectedValue(new Error("gone"));
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    act(() => result.current.cancel());
    await waitFor(() => expect(result.current.phase).toBe("idle"));
  });

  it("reset clears the job and closes the socket", async () => {
    const watch = stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    act(() => result.current.reset());
    expect(watch.socket.close).toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
    expect(result.current.job).toBeNull();
  });
});

describe("URL builders", () => {
  it("return '#' before a job exists, so no link points at the API root", () => {
    const { result } = renderHook(() => useExtraction());
    expect(result.current.downloadUrl("a.png")).toBe("#");
    expect(result.current.previewUrl("a.png")).toBe("#");
    expect(result.current.downloadAllUrl()).toBe("#");
  });

  it("delegate to the client once a job is active", async () => {
    stubWatch();
    const { result } = renderHook(() => useExtraction());
    await act(async () => {
      await result.current.start({ url: "https://example.com" } as never);
    });

    expect(result.current.downloadUrl("a.png")).toBe("/dl/j1/a.png");
    expect(result.current.previewUrl("a.png")).toBe("/pv/j1/a.png");
    expect(result.current.downloadAllUrl()).toBe("/zip/j1");
  });
});

describe("loading a job from history", () => {
  it("renders a finished job without reconnecting the socket", async () => {
    stubWatch();
    vi.mocked(client.getJob).mockResolvedValue(job({ job_id: "old", status: "done", progress: 100 }));
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.loadJob("old");
    });

    expect(result.current.phase).toBe("done");
    expect(result.current.job?.job_id).toBe("old");
    expect(client.watchJob).not.toHaveBeenCalled();
  });

  it("reconnects the socket for a job that is still in flight", async () => {
    stubWatch();
    vi.mocked(client.getJob).mockResolvedValue(job({ job_id: "live", status: "running" }));
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.loadJob("live");
    });

    expect(result.current.phase).toBe("running");
    expect(client.watchJob).toHaveBeenCalledWith("live", expect.any(Function), expect.any(Function));
  });

  it("wires the URL builders to the loaded job", async () => {
    stubWatch();
    vi.mocked(client.getJob).mockResolvedValue(job({ job_id: "old", status: "done" }));
    const { result } = renderHook(() => useExtraction());

    await act(async () => {
      await result.current.loadJob("old");
    });

    expect(result.current.downloadUrl("x.pdf")).toBe("/dl/old/x.pdf");
  });
});
