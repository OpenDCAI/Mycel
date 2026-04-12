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

function noContent(): Response {
  return {
    ok: true,
    status: 204,
    statusText: "No Content",
    json: async () => {
      throw new Error("204 response should not parse JSON");
    },
    text: async () => "",
  } as unknown as Response;
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

  it("listThreads rejects malformed thread identities", async () => {
    authFetch.mockResolvedValue(okJson({
      threads: [{ thread_id: { value: "thread-1" }, agent_user_id: "agent-1" }],
    }));

    await expect(api.listThreads()).rejects.toThrow("Malformed thread summaries");
  });

  it("getThread rejects malformed thread detail display data", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      entries: {},
      display_seq: "3",
      sandbox: null,
    }));

    await expect(api.getThread("thread-1")).rejects.toThrow("Malformed thread detail");
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
    authFetch.mockResolvedValue(okJson({
      source: "derived",
      config: { create_mode: "new", provider_config: "local", recipe: null, lease_id: null, model: null, workspace: null },
    }));

    await api.getDefaultThreadConfig("agent-1");

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads/default-config?agent_user_id=agent-1",
      { signal: undefined },
    );
  });

  it("getDefaultThreadConfig rejects malformed launch config payloads", async () => {
    authFetch.mockResolvedValue(okJson({ source: "derived", config: { provider_config: "local" } }));

    await expect(api.getDefaultThreadConfig("agent-1")).rejects.toThrow("Malformed default thread config");
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

  it("deleteThread accepts no-content responses without parsing JSON", async () => {
    authFetch.mockResolvedValue(noContent());

    await api.deleteThread("thread-1");

    expect(authFetch).toHaveBeenCalledWith("/api/threads/thread-1", { method: "DELETE" });
  });

  it("sendMessage rejects malformed routing payload identities", async () => {
    authFetch.mockResolvedValue(okJson({
      status: "started",
      routing: "direct",
      thread_id: { value: "thread-1" },
    }));

    await expect(api.sendMessage("thread-1", "hello")).rejects.toThrow("Malformed send message result");
  });

  it("getThreadRuntime rejects malformed runtime counters", async () => {
    authFetch.mockResolvedValue(okJson({
      state: { state: "idle", flags: {} },
      tokens: { total_tokens: "0", input_tokens: 0, output_tokens: 0, cost: 0 },
      context: { message_count: 0, estimated_tokens: 0, usage_percent: 0, near_limit: false },
      last_seq: 1,
    }));

    await expect(api.getThreadRuntime("thread-1")).rejects.toThrow("Malformed runtime status");
  });

  it("getThreadLease rejects malformed lease identities", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      lease_id: { value: "lease-1" },
      provider_name: "local",
      instance: null,
      created_at: "2026-04-12T00:00:00Z",
      updated_at: "2026-04-12T00:00:00Z",
    }));

    await expect(api.getThreadLease("thread-1")).rejects.toThrow("Malformed lease status");
  });

  it("getThreadSession rejects malformed session identities", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      session_id: "session-1",
      terminal_id: { value: "terminal-1" },
      status: "active",
      started_at: "2026-04-12T00:00:00",
      last_active_at: "2026-04-12T00:01:00",
      expires_at: "2026-04-12T01:00:00",
    }));

    await expect(api.getThreadSession("thread-1")).rejects.toThrow("Malformed session status");
  });

  it("getThreadTerminal rejects malformed terminal state", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      terminal_id: "terminal-1",
      lease_id: "lease-1",
      cwd: "/workspace",
      env_delta: { PATH: 123 },
      version: "1",
      created_at: "2026-04-12T00:00:00",
      updated_at: "2026-04-12T00:01:00",
    }));

    await expect(api.getThreadTerminal("thread-1")).rejects.toThrow("Malformed terminal status");
  });

  it("getThreadPermissions rejects malformed permission payload identities", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: { value: "thread-1" },
      requests: [],
      session_rules: { allow: [], deny: [], ask: [] },
      managed_only: true,
    }));

    await expect(api.getThreadPermissions("thread-1")).rejects.toThrow("Malformed thread permissions");
  });

  it("resolveThreadPermission rejects malformed permission mutation identities", async () => {
    authFetch.mockResolvedValue(okJson({
      ok: true,
      thread_id: "thread-1",
      request_id: { value: "request-1" },
    }));

    await expect(api.resolveThreadPermission("thread-1", "request-1", "allow")).rejects.toThrow(
      "Malformed permission mutation",
    );
  });

  it("addThreadPermissionRule rejects malformed rule mutation payloads", async () => {
    authFetch.mockResolvedValue(okJson({
      ok: true,
      thread_id: "thread-1",
      scope: "session",
      rules: { allow: "bash", deny: [], ask: [] },
      managed_only: true,
    }));

    await expect(api.addThreadPermissionRule("thread-1", "allow", "bash")).rejects.toThrow(
      "Malformed permission rules mutation",
    );
  });

  it("listSandboxSessions rejects malformed session identities", async () => {
    authFetch.mockResolvedValue(okJson({
      sessions: [{
        session_id: "session-1",
        thread_id: "thread-1",
        provider: { name: "local" },
        status: "running",
      }],
    }));

    await expect(api.listSandboxSessions()).rejects.toThrow("Malformed sandbox sessions");
  });

  it("listSandboxTypes rejects malformed sandbox type identities", async () => {
    authFetch.mockResolvedValue(okJson({
      types: [{ name: { value: "local" }, available: true }],
    }));

    await expect(api.listSandboxTypes()).rejects.toThrow("Malformed sandbox types");
  });

  it("listMyLeases rejects malformed lease participant identities", async () => {
    authFetch.mockResolvedValue(okJson({
      leases: [{
        lease_id: "lease-1",
        provider_name: "local",
        recipe_id: "recipe-1",
        recipe_name: "Local",
        thread_ids: ["thread-1"],
        agents: [{ thread_id: { value: "thread-1" }, agent_name: "Toad" }],
      }],
    }));

    await expect(api.listMyLeases()).rejects.toThrow("Malformed user leases");
  });

  it("uploadUserAvatar sends user avatar path instead of members path", async () => {
    authFetch.mockResolvedValue(okJson({ ok: true }));

    await api.uploadUserAvatar("agent-1", new File(["png"], "avatar.png", { type: "image/png" }));

    expect(authFetch).toHaveBeenCalledWith(
      "/api/users/agent-1/avatar",
      expect.objectContaining({
        method: "PUT",
        body: expect.any(FormData),
      }),
    );
  });
});
