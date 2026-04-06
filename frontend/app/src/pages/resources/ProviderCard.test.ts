import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./ProviderCard.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("ProviderCard selectors", () => {
  it("keeps stable browser verification hooks in the source", () => {
    const source = sourceModules["./ProviderCard.tsx"];

    expect(source).toContain('data-testid="provider-card"');
    expect(source).toContain("data-provider-id={provider.id}");
  });
});
