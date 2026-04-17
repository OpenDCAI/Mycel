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

function errorJson(status: number, payload: unknown): Response {
  return {
    ok: false,
    status,
    statusText: "Error",
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

  it("createThread sends sandbox_template_id instead of the template snapshot", async () => {
    authFetch.mockResolvedValue(okJson({ thread_id: "thread-1" }));

    await api.createThread({
      sandbox: "local",
      agentUserId: "agent-1",
      sandboxTemplateId: "local:default",
    });

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ sandbox: "local", agent_user_id: "agent-1", sandbox_template_id: "local:default" }),
      }),
    );
  });

  it("createThread sends existing_sandbox_id for existing sandbox selection", async () => {
    authFetch.mockResolvedValue(okJson({ thread_id: "thread-1" }));

    await api.createThread({
      sandbox: "local",
      agentUserId: "agent-1",
      existingSandboxId: "sandbox-1",
    });

    expect(authFetch).toHaveBeenCalledWith(
      "/api/threads",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ sandbox: "local", agent_user_id: "agent-1", existing_sandbox_id: "sandbox-1" }),
      }),
    );
  });

  it("createThread surfaces backend error messages", async () => {
    authFetch.mockResolvedValue(errorJson(409, {
      error: "sandbox_quota_exceeded",
      message: "Self-host Daytona sandbox quota exceeded",
    }));

    let thrown: Error | null = null;
    try {
      await api.createThread({ sandbox: "daytona_selfhost", agentUserId: "agent-1" });
    } catch (err) {
      thrown = err as Error;
    }

    expect(thrown?.message).toBe("Self-host Daytona sandbox quota exceeded");
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

  it("getDefaultThread rejects malformed default-thread envelopes", async () => {
    authFetch.mockResolvedValue(okJson({ thread: false }));

    await expect(api.getDefaultThread("agent-1")).rejects.toThrow("Malformed default thread");
  });

  it("getDefaultThreadConfig queries by agent_user_id", async () => {
    authFetch.mockResolvedValue(okJson({
      source: "derived",
      config: { create_mode: "new", provider_config: "local", sandbox_template: null, existing_sandbox_id: null, model: null, workspace: null },
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

  it("getThreadSandbox rejects malformed sandbox status identities", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: { value: "thread-1" },
      provider_name: "local",
      instance: null,
      created_at: "2026-04-12T00:00:00Z",
      updated_at: "2026-04-12T00:00:00Z",
    }));

    await expect(api.getThreadSandbox("thread-1")).rejects.toThrow("Malformed sandbox status");
    expect(authFetch).toHaveBeenCalledWith("/api/threads/thread-1/sandbox");
  });

  it("no longer exposes terminal status client", async () => {
    expect("getThreadTerminal" in api).toBe(false);
  });

  it("getThreadFileChannel reads workspace path from files channel binding", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      files_path: "/workspace/.mycel/files",
      workspace_id: "workspace-1",
      workspace_path: "/workspace",
    }));

    await expect(api.getThreadFileChannel("thread-1")).resolves.toEqual({
      thread_id: "thread-1",
      files_path: "/workspace/.mycel/files",
      workspace_id: "workspace-1",
      workspace_path: "/workspace",
    });
    expect(authFetch).toHaveBeenCalledWith("/api/threads/thread-1/files/channels", undefined);
  });

  it("getThreadFileChannel rejects malformed workspace binding", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      files_path: "/workspace/.mycel/files",
      workspace_id: "workspace-1",
      workspace_path: null,
    }));

    await expect(api.getThreadFileChannel("thread-1")).rejects.toThrow("Malformed thread file channel");
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

  it("listSandboxTypes rejects malformed sandbox type identities", async () => {
    authFetch.mockResolvedValue(okJson({
      types: [{ name: { value: "local" }, available: true }],
    }));

    await expect(api.listSandboxTypes()).rejects.toThrow("Malformed sandbox types");
  });

  it("listMySandboxes reads canonical sandbox summaries without lease identities", async () => {
    authFetch.mockResolvedValue(okJson({
      sandboxes: [{
        sandbox_id: "sandbox-1",
        provider_name: "local",
        recipe_id: "recipe-1",
        recipe_name: "Local",
        thread_ids: ["thread-1"],
        agents: [{ thread_id: "thread-1", agent_name: "Toad" }],
      }],
    }));

    const result = await api.listMySandboxes();

    expect(result).toMatchObject([{ sandbox_id: "sandbox-1" }]);
    expect(result[0]).not.toHaveProperty("lease_id");
    expect(authFetch).toHaveBeenCalledWith("/api/sandbox/sandboxes/mine", { signal: undefined });
  });

  it("listMySandboxes rejects sandbox summaries without sandbox identities", async () => {
    authFetch.mockResolvedValue(okJson({
      sandboxes: [{
        provider_name: "local",
        recipe_id: "recipe-1",
        recipe_name: "Local",
        thread_ids: ["thread-1"],
        agents: [{ thread_id: "thread-1", agent_name: "Toad" }],
      }],
    }));

    await expect(api.listMySandboxes()).rejects.toThrow("Malformed user sandboxes");
  });

  it("listMySandboxes rejects malformed sandbox participant identities", async () => {
    authFetch.mockResolvedValue(okJson({
      sandboxes: [{
        sandbox_id: "sandbox-1",
        provider_name: "local",
        recipe_id: "recipe-1",
        recipe_name: "Local",
        thread_ids: ["thread-1"],
        agents: [{ thread_id: { value: "thread-1" }, agent_name: "Toad" }],
      }],
    }));

    await expect(api.listMySandboxes()).rejects.toThrow("Malformed user sandboxes");
  });

  it("listSandboxFiles rejects malformed file entries", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      path: "/workspace",
      entries: [{ name: "src", is_dir: "true", size: 0 }],
    }));

    await expect(api.listSandboxFiles("thread-1")).rejects.toThrow("Malformed sandbox file list");
  });

  it("readSandboxFile rejects malformed file content payloads", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      path: "/workspace/app.py",
      content: { text: "print(1)" },
      size: "8",
    }));

    await expect(api.readSandboxFile("thread-1", "/workspace/app.py")).rejects.toThrow("Malformed sandbox file read");
  });

  it("uploadSandboxFile rejects malformed upload results", async () => {
    authFetch.mockResolvedValue(okJson({
      thread_id: "thread-1",
      relative_path: "avatar.png",
      absolute_path: "/workspace/files/avatar.png",
      size_bytes: "3",
      sha256: "abc",
    }));

    await expect(api.uploadSandboxFile("thread-1", { file: new File(["png"], "avatar.png") })).rejects.toThrow(
      "Malformed sandbox upload result",
    );
  });

  it("fetchInviteCodes rejects malformed invite code rows", async () => {
    authFetch.mockResolvedValue(okJson({
      codes: [{
        code: { value: "INVITE" },
        used: false,
        created_at: "2026-04-12T00:00:00Z",
      }],
    }));

    await expect(api.fetchInviteCodes()).rejects.toThrow("Malformed invite codes");
  });

  it("generateInviteCode rejects malformed invite code payloads", async () => {
    authFetch.mockResolvedValue(okJson({
      code: "INVITE",
      used: "false",
      created_at: "2026-04-12T00:00:00Z",
    }));

    await expect(api.generateInviteCode()).rejects.toThrow("Malformed invite code");
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
