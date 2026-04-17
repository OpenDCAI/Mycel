import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("ResourcesPage resource identity contract", () => {
  it("does not keep leaseId as a frontend resource grouping fallback", () => {
    const resourcesPage = readFileSync(resolve(import.meta.dirname, "ResourcesPage.tsx"), "utf8");
    const resourceTypes = readFileSync(resolve(import.meta.dirname, "resources/types.ts"), "utf8");
    const legacyLeaseToken = "lease" + "Id";

    expect(resourcesPage).not.toContain(legacyLeaseToken);
    expect(resourceTypes).not.toContain(legacyLeaseToken);
  });
});
