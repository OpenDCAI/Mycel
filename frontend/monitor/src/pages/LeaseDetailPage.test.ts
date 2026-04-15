import { describe, expect, it } from "vitest";

import { buildLeaseDetailShell } from "./LeaseDetailPage";

describe("lease detail page shell", () => {
  it("keeps cleanup as compatibility shell after sandbox cleanup rollout", () => {
    const shell = buildLeaseDetailShell({
      lease: { lease_id: "lease-1" },
      triage: { description: "Lease state and cleanup readiness." },
      cleanup: { allowed: true },
    });

    expect(shell.title).toBe("Lease lease-1");
    expect(shell.cleanupTitle).toBe("Compatibility Cleanup");
    expect(shell.cleanupHint).toBe("Legacy lease-shaped cleanup entry kept during sandbox cleanup rollout.");
    expect(shell.cleanupButtonLabel).toBe("Start compatibility cleanup");
    expect(shell.compatibilityOnly).toBe(true);
  });
});
