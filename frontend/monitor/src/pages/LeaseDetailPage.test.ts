import { describe, expect, it } from "vitest";

import { buildLeaseDetailShell } from "./LeaseDetailPage";

describe("lease detail page shell", () => {
  it("becomes a compatibility redirect shell after sandbox detail parity lands", () => {
    const shell = buildLeaseDetailShell({
      lease: { lease_id: "lease-1", sandbox_id: "sandbox-1" },
      triage: { description: "Lease state and cleanup readiness." },
      cleanup: { reason: "Canonical sandbox detail is ready." },
    });

    expect(shell.title).toBe("Lease compatibility redirect");
    expect(shell.description).toBe("Legacy lease-shaped detail route now redirects to canonical sandbox detail.");
    expect(shell.canonicalHref).toBe("/sandboxes/sandbox-1");
    expect(shell.compatibilityOnly).toBe(true);
  });
});
