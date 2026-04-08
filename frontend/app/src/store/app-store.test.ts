import { beforeEach, describe, expect, it, vi } from "vitest";

describe("app store agent panel contract", () => {
  let useAuthStore: typeof import("./auth-store").useAuthStore;
  let useAppStore: typeof import("./app-store").useAppStore;

  beforeEach(async () => {
    vi.restoreAllMocks();
    vi.resetModules();
    const storage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("window", { __MYCEL_CONFIG__: {}, localStorage: storage });

    ({ useAuthStore } = await import("./auth-store"));
    ({ useAppStore } = await import("./app-store"));

    useAuthStore.setState({
      token: "token-1",
      user: null,
      agent: null,
      userId: null,
      setupInfo: null,
      login: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn(),
      completeRegister: vi.fn(),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("fetchAgents hits /agents instead of /members", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await useAppStore.getState().fetchAgents();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/panel/agents",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-1",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("agent mutations all hit /agents routes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: "agent-1", config: {} }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({ id: "agent-1", config: {} }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await useAppStore.getState().addAgent("Toad", "helper");
    await useAppStore.getState().updateAgent("agent-1", { name: "Dryad" });
    await useAppStore.getState().updateAgentConfig("agent-1", { prompt: "hello" });
    await useAppStore.getState().publishAgent("agent-1", "minor");
    await useAppStore.getState().deleteAgent("agent-1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/panel/agents",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Toad", description: "helper" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/panel/agents/agent-1",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ name: "Dryad" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/panel/agents/agent-1/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ prompt: "hello" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/panel/agents/agent-1/publish",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ bump_type: "minor" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/panel/agents/agent-1",
      expect.objectContaining({
        method: "DELETE",
      }),
    );
  });

  it("resets loaded member state when auth identity changes", () => {
    useAppStore.setState({
      agentList: [{ id: "m-old", name: "Old", status: "active" } as never],
      loaded: true,
      error: "stale",
    });

    useAppStore.getState().resetSessionData();

    const state = useAppStore.getState();
    expect(state.agentList).toEqual([]);
    expect(state.loaded).toBe(false);
    expect(state.error).toBeNull();
  });
});
