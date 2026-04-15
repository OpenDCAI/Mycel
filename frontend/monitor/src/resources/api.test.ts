import { afterEach, describe, expect, it, vi } from "vitest";

import {
  browseMonitorSandbox,
  cleanupMonitorProviderSession,
  fetchMonitorProviderSessions,
  readMonitorSandboxFile,
} from "./api";

describe("monitor resource API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches provider orphan sessions through the monitor API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        count: 1,
        sessions: [{ session_id: "sandbox-1", provider: "daytona_selfhost", status: "paused", source: "provider_orphan" }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchMonitorProviderSessions();

    expect(fetchMock).toHaveBeenCalledWith("/api/monitor/provider-sessions", {
      headers: { "Content-Type": "application/json" },
    });
    expect(payload.sessions[0].session_id).toBe("sandbox-1");
  });

  it("rejects malformed provider orphan payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ sessions: null }),
      }),
    );

    await expect(fetchMonitorProviderSessions()).rejects.toThrow(
      "Unexpected /api/monitor/provider-sessions response shape",
    );
  });

  it("cleans provider orphan sessions through the monitor API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        accepted: true,
        message: "Provider session cleanup completed.",
        operation: { operation_id: "op-1", status: "succeeded" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await cleanupMonitorProviderSession("daytona_selfhost", "sandbox/1");

    expect(fetchMock).toHaveBeenCalledWith("/api/monitor/provider-sessions/daytona_selfhost/sandbox%2F1/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(payload.operation?.status).toBe("succeeded");
  });

  it("browses monitor sandbox files through sandbox-shaped route naming", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ current_path: "/workspace", parent_path: "/", items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await browseMonitorSandbox("sandbox-1", "/workspace");

    expect(fetchMock).toHaveBeenCalledWith("/api/monitor/sandboxes/sandbox-1/browse?path=%2Fworkspace", undefined);
    expect(payload.current_path).toBe("/workspace");
  });

  it("reads monitor sandbox files through sandbox-shaped route naming", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ path: "/README.md", content: "hello", truncated: false }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await readMonitorSandboxFile("sandbox-1", "/README.md");

    expect(fetchMock).toHaveBeenCalledWith("/api/monitor/sandboxes/sandbox-1/read?path=%2FREADME.md", undefined);
    expect(payload.content).toBe("hello");
  });
});
