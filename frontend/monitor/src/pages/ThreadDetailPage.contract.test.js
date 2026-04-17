import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("ThreadDetailPage summary contract", () => {
  it("does not expose lease_id on the thread summary read surface", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ThreadDetailPage.tsx"), "utf8");
    const legacyLeaseToken = "lease_" + "id";

    expect(source).not.toContain(legacyLeaseToken);
  });
});
