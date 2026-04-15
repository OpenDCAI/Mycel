import { describe, expect, it } from "vitest";

import { monitorNav, resolveMonitorNav } from "./monitor-nav";

describe("monitor navigation", () => {
  it("exposes sandbox configs as the operator-owned config surface", () => {
    expect(monitorNav.some((item) => item.to === "/sandbox-configs" && item.label === "Sandbox Configs")).toBe(true);
    expect(resolveMonitorNav("/sandbox-configs").to).toBe("/sandbox-configs");
  });

  it("treats sandboxes as the canonical runtime shell", () => {
    expect(monitorNav.some((item) => item.to === "/sandboxes" && item.label === "Sandboxes")).toBe(true);
    expect(resolveMonitorNav("/sandboxes").to).toBe("/sandboxes");
    expect(resolveMonitorNav("/leases").to).toBe("/sandboxes");
  });
});
