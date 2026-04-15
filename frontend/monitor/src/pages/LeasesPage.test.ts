import { describe, expect, it } from "vitest";

import { buildLeaseWorkbenchShell } from "./LeasesPage";

describe("leases page shell", () => {
  it("uses lease rows as compatibility links into canonical sandbox detail", () => {
    const shell = buildLeaseWorkbenchShell({
      title: "All Leases",
      count: 1,
      triage: {
        summary: {
          active_drift: 0,
          detached_residue: 0,
          orphan_cleanup: 1,
          healthy_capacity: 0,
        },
      },
      items: [
        {
          sandbox_id: "sandbox-1",
          lease_id: "lease-1",
          provider: "docker",
          instance_id: "runtime-1",
          triage: { category: "orphan_cleanup", title: "Orphan Cleanup" },
          thread: { thread_id: "thread-1" },
          state_badge: { text: "paused" },
          updated_ago: "1m ago",
          error: null,
        },
      ],
    });

    expect(shell.triageTitle).toBe("Lease Triage");
    expect(shell.workbenchTitle).toBe("Lease Workbench");
    expect(shell.rows[0].href).toBe("/sandboxes/sandbox-1");
    expect(shell.rows[0].compatibilityLeaseId).toBe("lease-1");
  });
});
