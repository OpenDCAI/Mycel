import { beforeEach, describe, expect, it, vi } from "vitest";

const authFetch = vi.fn();

vi.mock("../store/auth-store", () => ({
  authFetch,
}));

function okJson(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("thread api client contract", () => {
  let api: typeof import("./client");

  beforeEach(async () => {
    authFetch.mockReset();
    vi.resetModules();
    vi.stubGlobal("window", { __MYCEL_CONFIG__: {} });
    api = await import("./client");
  });

  it("createThread sends agent_user_id instead of member_id", async () => {
    authFetch.mockResolvedValue(okJson({ thread_id: "thread-1" }));

    await api.createThread({ sandbox: "local", agentUserId: "agent-1" });

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ sandbox: "local", agent_user_id: "agent-1" }),
      }),
    );
  });

  it("getDefaultThread resolves through agent_user_id", async () => {
    authFetch.mockResolvedValue(okJson({ thread: null }));

    await api.getDefaultThread("agent-1");

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads/main",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ agent_user_id: "agent-1" }),
      }),
    );
  });

  it("getDefaultThreadConfig queries by agent_user_id", async () => {
    authFetch.mockResolvedValue(okJson({ source: "derived", config: {} }));

    await api.getDefaultThreadConfig("agent-1");

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads/default-config?agent_user_id=agent-1",
      { signal: undefined },
    );
  });

  it("saveDefaultThreadConfig posts agent_user_id", async () => {
    authFetch.mockResolvedValue(okJson({ ok: true }));

    await api.saveDefaultThreadConfig("agent-1", {
      create_mode: "new",
      provider_config: "local",
      model: "gpt-5.4-mini",
    });

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads/default-config",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          agent_user_id: "agent-1",
          create_mode: "new",
          provider_config: "local",
          model: "gpt-5.4-mini",
        }),
      }),
    );
  });
});
