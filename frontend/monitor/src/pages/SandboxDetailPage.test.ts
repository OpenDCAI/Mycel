import { describe, expect, it } from "vitest";

import { buildSandboxDetailShell } from "./SandboxDetailPage";

describe("sandbox detail page shell", () => {
  it("uses sandbox-shaped shell with cleanup parity lane", () => {
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
      cleanup: {
        allowed: true,
        recommended_action: "lease_cleanup",
        reason: "Lease is orphan cleanup residue and can enter managed cleanup.",
        operation: {
          operation_id: "op-1",
          kind: "lease_cleanup",
          status: "succeeded",
          summary: "Lease cleanup completed.",
        },
        recent_operations: [],
      },
    });

    expect(shell.title).toBe("Sandbox sandbox-1");
    expect(shell.surfaceHref).toBe("/sandboxes");
    expect(shell.cleanupIncluded).toBe(true);
    expect(shell.cleanupTitle).toBe("Cleanup");
    expect(shell.cleanupHint).toBe("Canonical sandbox cleanup lane for current operation and recent cleanup history.");
    expect(shell.cleanupButtonLabel).toBe("Start sandbox cleanup");
    expect(shell.cleanupLedgerTitle).toBe("Recent Operations");
  });
});
