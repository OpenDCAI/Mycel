import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./SandboxFileBrowser.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("SandboxFileBrowser source", () => {
  it("keeps a retry action for browse failures", () => {
    const source = sourceModules["./SandboxFileBrowser.tsx"];

    expect(source).toContain('data-testid="sandbox-browser-retry"');
    expect(source).toContain("void loadPath(currentPath);");
    expect(source).toContain("重试");
  });
});
