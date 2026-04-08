import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./SandboxDetailSheet.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("SandboxDetailSheet source", () => {
  it("declares a sheet description for dialog accessibility", () => {
    const source = sourceModules["./SandboxDetailSheet.tsx"];

    expect(source).toContain("SheetDescription");
  });

  it("renders resource session names from agentName", () => {
    const source = sourceModules["./SandboxDetailSheet.tsx"];

    expect(source).toContain("session.agentName");
    expect(source).not.toContain("session.memberName");
  });

  it("renders runtime session ids when available", () => {
    const source = sourceModules["./SandboxDetailSheet.tsx"];

    expect(source).toContain("session.runtimeSessionId");
  });
});
