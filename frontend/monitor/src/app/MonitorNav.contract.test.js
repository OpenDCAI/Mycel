import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("monitor navigation source contract", () => {
  it("describes the monitor workbench with sandbox wording", () => {
    const source = readFileSync(resolve(import.meta.dirname, "MonitorNav.tsx"), "utf8");

    expect(source).not.toContain("lease " + "workbench");
  });
});
