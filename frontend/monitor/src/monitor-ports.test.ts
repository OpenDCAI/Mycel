import { describe, expect, it } from "vitest";

import { resolveMonitorPorts } from "./monitor-ports";

describe("resolveMonitorPorts", () => {
  it("uses a dedicated monitor backend port when provided", () => {
    const ports = resolveMonitorPorts({
      env: {
        LEON_BACKEND_PORT: "8010",
        LEON_MONITOR_BACKEND_PORT: "55417",
        LEON_MONITOR_PORT: "5174",
        LEON_MONITOR_PREVIEW_PORT: "4174",
      },
      getWorktreePort: (_key, defaultPort) => defaultPort,
    });

    expect(ports.backendPort).toBe("8010");
    expect(ports.monitorBackendPort).toBe("55417");
  });

  it("falls back to the main backend port when no dedicated monitor backend port is provided", () => {
    const ports = resolveMonitorPorts({
      env: {
        LEON_BACKEND_PORT: "8010",
      },
      getWorktreePort: (_key, defaultPort) => defaultPort,
    });

    expect(ports.backendPort).toBe("8010");
    expect(ports.monitorBackendPort).toBe("8010");
  });

  it("uses the worktree monitor-backend port when no dedicated env port is provided", () => {
    const ports = resolveMonitorPorts({
      env: {
        LEON_BACKEND_PORT: "8010",
      },
      getWorktreePort: (key, defaultPort) => {
        if (key === "worktree.ports.monitor-backend") {
          return "55419";
        }
        return defaultPort;
      },
    });

    expect(ports.monitorBackendPort).toBe("55419");
  });
});
