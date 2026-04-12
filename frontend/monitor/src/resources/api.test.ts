import { afterEach, describe, expect, it, vi } from "vitest";

import { cleanupMonitorProviderSession, fetchMonitorProviderSessions } from "./api";

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
});
