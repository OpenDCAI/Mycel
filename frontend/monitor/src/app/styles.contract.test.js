import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("monitor style contract", () => {
  it("keeps the body background on a warm surface without the blue radial wash", () => {
    const styles = readFileSync(resolve(import.meta.dirname, "../styles.css"), "utf8");

    expect(styles).not.toContain("radial-gradient(circle at top left, rgba(200, 226, 255, 0.45), transparent 28%)");
    expect(styles).toContain("background: linear-gradient(180deg, #f4f1e8 0%, #ece6d7 100%)");
  });
});
