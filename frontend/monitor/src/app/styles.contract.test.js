import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("monitor style contract", () => {
  it("keeps the body background on a stable warm surface without gradient wash", () => {
    const styles = readFileSync(resolve(import.meta.dirname, "../styles.css"), "utf8");

    expect(styles).not.toContain("radial-gradient(circle at top left, rgba(200, 226, 255, 0.45), transparent 28%)");
    expect(styles).toContain("background: #f4efe6");
  });

  it("does not render provider-level running metric helper copy", () => {
    const resourcesPage = readFileSync(resolve(import.meta.dirname, "../ResourcesPage.tsx"), "utf8");
    const styles = readFileSync(resolve(import.meta.dirname, "../styles.css"), "utf8");

    expect(resourcesPage).not.toContain("provider-card__running-note");
    expect(resourcesPage).not.toContain("具体指标见下方沙盒");
    expect(styles).not.toContain("provider-card__running-note");
  });
});
