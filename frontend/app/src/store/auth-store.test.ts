import { beforeEach, describe, expect, it, vi } from "vitest";

describe("authFetch header contract", () => {
  let authFetch: typeof import("./auth-store").authFetch;
  let useAuthStore: typeof import("./auth-store").useAuthStore;

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

    ({ authFetch, useAuthStore } = await import("./auth-store"));
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

  it("preserves HeadersInit while adding auth and JSON defaults", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await authFetch("/api/settings", {
      headers: new Headers([["X-Trace-Id", "trace-1"]]),
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("X-Trace-Id")).toBe("trace-1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Authorization")).toBe("Bearer token-1");
  });

  it("does not force JSON content type for FormData uploads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await authFetch("/api/upload", {
      method: "POST",
      body: new FormData(),
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Content-Type")).toBeNull();
    expect(headers.get("Authorization")).toBe("Bearer token-1");
  });

  it("marks auth state hydrated after persisted session restore", async () => {
    const persisted = JSON.stringify({
      state: {
        token: "persisted-token",
        user: { id: "u-1", name: "tester", type: "human", avatar: null },
        agent: null,
        userId: "u-1",
        setupInfo: null,
      },
      version: 0,
    });
    const storage = {
      getItem: vi.fn((key: string) => (key === "leon-auth" ? persisted : null)),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("window", { __MYCEL_CONFIG__: {}, localStorage: storage });
    vi.resetModules();

    const mod = await import("./auth-store");
    await Promise.resolve();

    expect(mod.useAuthStore.getState().token).toBe("persisted-token");
    expect(mod.useAuthStore.getState().hydrated).toBe(true);
  });
});
