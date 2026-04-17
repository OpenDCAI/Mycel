import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("threads page source contract", () => {
  it("uses thread-shaped workbench class names", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ThreadsPage.tsx"), "utf8");

    expect(source).not.toContain("leases" + "-workbench-header");
  });
});
