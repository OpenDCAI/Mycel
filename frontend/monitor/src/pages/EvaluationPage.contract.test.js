import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("evaluation page scenario selector", () => {
  it("exposes pressed state for selectable scenario chips", () => {
    const source = readFileSync(resolve(import.meta.dirname, "EvaluationPage.tsx"), "utf8");

    expect(source).toContain("aria-pressed={selected}");
  });
});
