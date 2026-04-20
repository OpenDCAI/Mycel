// @vitest-environment jsdom

import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useThreadManager } from "./use-thread-manager";

const { listSandboxTypes, listThreads } = vi.hoisted(() => ({
  listSandboxTypes: vi.fn(),
  listThreads: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listSandboxTypes,
    listThreads,
  };
});

describe("useThreadManager", () => {
  beforeEach(() => {
    listSandboxTypes.mockReset();
    listThreads.mockReset();
  });

  it("surfaces bootstrap failures instead of silently showing an empty thread shell", async () => {
    listSandboxTypes.mockRejectedValue(new Error("Sandbox types API 503"));
    listThreads.mockResolvedValue([]);

    const view = renderHook(() => useThreadManager());

    await waitFor(() => {
      expect(view.result.current.loading).toBe(false);
    });
    expect(view.result.current.bootstrapError).toBe("Sandbox types API 503");
  });
});
