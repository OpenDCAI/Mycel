import { describe, expect, it } from "vitest";

import { buildDashboardAttentionLinks, buildDashboardSurfaces, type DashboardPayload } from "./DashboardPage";

const payload: DashboardPayload = {
  snapshot_at: "2026-04-15T00:00:00Z",
  infra: {
    providers_active: 2,
    providers_unavailable: 1,
    sandboxes_total: 3,
    sandboxes_diverged: 1,
    sandboxes_orphan: 0,
  },
  workload: {
    running_sessions: 4,
    evaluations_running: 1,
  },
  latest_evaluation: {
    headline: "Most recent evaluation batch is still running.",
  },
};

describe("dashboard summary shell", () => {
  it("uses sandbox-shaped labels and canonical sandbox links", () => {
    expect(buildDashboardSurfaces(payload)).toContainEqual({
      label: "Running Sandboxes",
      value: 4,
      to: "/resources",
    });
    expect(buildDashboardSurfaces(payload).map((surface) => surface.label)).not.toContain("Running Sessions");
    expect(buildDashboardSurfaces(payload)).toContainEqual({
      label: "Tracked Sandboxes",
      value: 3,
      to: "/sandboxes",
    });
    expect(buildDashboardAttentionLinks(payload)).toContainEqual({
      label: "Sandbox Drift",
      body: "1 diverged sandboxes, 0 orphan sandboxes.",
      to: "/sandboxes",
    });
  });
});
