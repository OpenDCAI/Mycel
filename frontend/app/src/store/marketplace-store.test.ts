import { beforeEach, describe, expect, it, vi } from "vitest";

describe("marketplace store backend contract", () => {
  let useAuthStore: typeof import("./auth-store").useAuthStore;
  let useMarketplaceStore: typeof import("./marketplace-store").useMarketplaceStore;

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
    ({ useMarketplaceStore } = await import("./marketplace-store"));

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

  it("upgrade posts user_id instead of member_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await useMarketplaceStore.getState().upgrade("agent-1", "item-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/marketplace/upgrade",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ user_id: "agent-1", item_id: "item-1" }),
        headers: expect.objectContaining({
          Authorization: "Bearer token-1",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("publishToMarketplace posts user_id instead of member_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await useMarketplaceStore
      .getState()
      .publishToMarketplace("agent-1", "member", "patch", "notes", ["tag-a"], "public");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/marketplace/publish",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          user_id: "agent-1",
          type: "member",
          bump_type: "patch",
          release_notes: "notes",
          tags: ["tag-a"],
          visibility: "public",
        }),
      }),
    );
  });
});
