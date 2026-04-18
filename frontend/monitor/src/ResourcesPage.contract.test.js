import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("ResourcesPage resource identity contract", () => {
  it("does not keep leaseId as a frontend resource grouping fallback", () => {
    const resourcesPage = readFileSync(resolve(import.meta.dirname, "ResourcesPage.tsx"), "utf8");
    const resourceTypes = readFileSync(resolve(import.meta.dirname, "resources/types.ts"), "utf8");
    const removedLeaseFieldToken = "lease" + "Id";

    expect(resourcesPage).not.toContain(removedLeaseFieldToken);
    expect(resourceTypes).not.toContain(removedLeaseFieldToken);
  });

  it("does not describe internal resource rows as sessions", () => {
    const resourcesPage = readFileSync(resolve(import.meta.dirname, "ResourcesPage.tsx"), "utf8");
    const styles = readFileSync(resolve(import.meta.dirname, "styles.css"), "utf8");
    const removedInternalTokens = [
      "format" + "SessionMetricRange",
      "running" + "SessionCount",
      "paused" + "SessionCount",
      "stopped" + "SessionCount",
      "provider-card__" + "session-dot",
      "sandbox-" + "session-row",
      "sandbox-" + "session-list",
      "unavailable-with-" + "sessions",
      "关联 " + "session",
    ];

    for (const token of removedInternalTokens) {
      expect(resourcesPage).not.toContain(token);
      expect(styles).not.toContain(token);
    }
  });
});
