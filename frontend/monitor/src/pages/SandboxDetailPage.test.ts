import { describe, expect, it } from "vitest";

import { buildSandboxDetailShell } from "./SandboxDetailPage";

describe("sandbox detail page shell", () => {
  it("uses sandbox-shaped read-only shell without cleanup lane", () => {
    const shell = buildSandboxDetailShell({
      sandbox: {
        sandbox_id: "sandbox-1",
        provider_name: "docker",
        desired_state: "running",
        observed_state: "running",
        current_instance_id: "runtime-1",
        updated_at: "2026-04-15T00:00:00Z",
        last_error: null,
        badge: { text: "running" },
      },
      triage: {
        category: "healthy_capacity",
        title: "Healthy Capacity",
        description: "Sandbox is converged and attached.",
      },
      provider: {
        id: "docker",
        name: "docker",
      },
      runtime: {
        runtime_session_id: "runtime-1",
      },
      threads: [{ thread_id: "thread-1" }],
      sessions: [{ chat_session_id: "chat-1", thread_id: "thread-1", status: "active" }],
    });

    expect(shell.title).toBe("Sandbox sandbox-1");
    expect(shell.surfaceHref).toBe("/sandboxes");
    expect(shell.cleanupIncluded).toBe(false);
  });
});
