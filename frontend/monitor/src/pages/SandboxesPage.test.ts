import { describe, expect, it } from "vitest";

import { buildSandboxWorkbenchShell } from "./SandboxesPage";

describe("sandboxes page shell", () => {
  it("uses sandbox-shaped headings and canonical sandbox links", () => {
    const shell = buildSandboxWorkbenchShell({
      title: "All Sandboxes",
      count: 2,
      triage: {
        summary: {
          active_drift: 1,
          detached_residue: 0,
          orphan_cleanup: 0,
          healthy_capacity: 1,
        },
      },
      items: [
        {
          sandbox_id: "sandbox-1",
          provider: "docker",
          instance_id: "runtime-1",
          triage: { category: "active_drift", title: "Active Drift" },
          thread: { thread_id: "thread-1" },
          state_badge: { text: "running" },
          updated_ago: "1m ago",
          error: null,
        },
      ],
    });

    expect(shell.triageTitle).toBe("Sandbox Triage");
    expect(shell.workbenchTitle).toBe("Sandbox Workbench");
    expect(shell.rows[0].href).toBe("/sandboxes/sandbox-1");
  });
});
