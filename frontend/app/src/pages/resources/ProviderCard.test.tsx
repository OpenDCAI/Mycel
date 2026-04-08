import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./ProviderCard.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("ProviderCard source", () => {
  it("renders provider unavailableReason instead of hardcoded SDK copy", () => {
    const source = sourceModules["./ProviderCard.tsx"];

    expect(source).toContain("provider.unavailableReason");
    expect(source).not.toContain("需要安装 SDK");
    expect(source).not.toContain("需要 Docker");
  });
});
