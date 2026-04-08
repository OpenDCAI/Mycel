import { describe, expect, it } from "vitest";

import { resolveMonitorPorts } from "../monitor-ports";

describe("resolveMonitorPorts", () => {
  it("prefers env vars over worktree config", () => {
    const ports = resolveMonitorPorts({
      env: {
        LEON_BACKEND_PORT: "9012",
        LEON_MONITOR_PORT: "5274",
        LEON_MONITOR_PREVIEW_PORT: "4274",
      },
      getWorktreePort: (key, fallback) =>
        (
          {
            "worktree.ports.backend": "8012",
            "worktree.ports.monitor-frontend": "5178",
            "worktree.ports.monitor-preview": "4178",
          } as Record<string, string>
        )[key] ?? fallback,
    });

    expect(ports).toEqual({
      backendPort: "9012",
      devPort: 5274,
      previewPort: 4274,
    });
  });

  it("uses worktree config when env vars are absent", () => {
    const ports = resolveMonitorPorts({
      env: {},
      getWorktreePort: (key, fallback) =>
        (
          {
            "worktree.ports.backend": "8012",
            "worktree.ports.monitor-frontend": "5178",
            "worktree.ports.monitor-preview": "4178",
          } as Record<string, string>
        )[key] ?? fallback,
    });

    expect(ports).toEqual({
      backendPort: "8012",
      devPort: 5178,
      previewPort: 4178,
    });
  });

  it("falls back to current monitor defaults", () => {
    const ports = resolveMonitorPorts({
      env: {},
      getWorktreePort: (_key, fallback) => fallback,
    });

    expect(ports).toEqual({
      backendPort: "8001",
      devPort: 5174,
      previewPort: 4174,
    });
  });
});
