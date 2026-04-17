import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("sandboxes page source contract", () => {
  it("does not use lease-shaped CSS class names for the sandbox workbench", () => {
    const source = [
      readFileSync(resolve(import.meta.dirname, "SandboxesPage.tsx"), "utf8"),
      readFileSync(resolve(import.meta.dirname, "..", "styles.css"), "utf8"),
    ].join("\n");

    const forbiddenTokens = ["lease" + "-triage", "leases" + "-workbench", "lease" + "-topology"];
    for (const token of forbiddenTokens) {
      expect(source).not.toContain(token);
    }
  });
});
