import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("SandboxDetailPage source contract", () => {
  it("does not describe sandbox runtime detail as a runtime session link", () => {
    const source = readFileSync(resolve(import.meta.dirname, "SandboxDetailPage.tsx"), "utf8");
    const oldRuntimeCopy = ["Live runtime", "session", "linked"].join(" ");

    expect(source).not.toContain(oldRuntimeCopy);
  });
});
