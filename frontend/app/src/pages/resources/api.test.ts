import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchResourceProviders, refreshResourceProviders } from "./api";

const fetchMock = vi.fn();

describe("resources api", () => {
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("reads the product overview from /api/resources/overview", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        summary: { snapshot_at: "2026-04-06T00:00:00Z", total_providers: 1, active_providers: 1, unavailable_providers: 0, running_sessions: 1 },
        providers: [{ id: "local", cardCpu: { used: 1, limit: 2, unit: "%" } }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchResourceProviders();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resources/overview",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
  });

  it("refreshes the product overview from /api/resources/overview/refresh", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        summary: {
          snapshot_at: "2026-04-06T00:00:00Z",
          last_refreshed_at: "2026-04-06T00:00:00Z",
          refresh_status: "ok",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 1,
        },
        providers: [{ id: "local", cardCpu: { used: 1, limit: 2, unit: "%" } }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await refreshResourceProviders();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resources/overview/refresh",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
});
