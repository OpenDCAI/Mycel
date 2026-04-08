import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./SandboxCard.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("SandboxCard source", () => {
  it("renders resource session names from agentName", () => {
    const source = sourceModules["./SandboxCard.tsx"];

    expect(source).toContain("s.agentName");
    expect(source).not.toContain("s.memberName");
  });

  it("renders resource agent avatars from avatarUrl", () => {
    const source = sourceModules["./SandboxCard.tsx"];

    expect(source).toContain("s.avatarUrl");
  });
});
