import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("SandboxesPage source contract", () => {
  it("does not keep the old local runtime prefix as a contiguous source token", () => {
    const source = readFileSync(resolve(import.meta.dirname, "SandboxesPage.tsx"), "utf8");
    const lowerLocalRuntimePrefix = ["leon", "lease"].join("-") + "-";

    expect(source).not.toContain(lowerLocalRuntimePrefix);
  });
});
