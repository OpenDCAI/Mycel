// @vitest-environment jsdom

import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceSettings } from "./use-workspace-settings";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("useWorkspaceSettings", () => {
  it("does not log a failed settings load once navigation already left /chat/hire", async () => {
    window.history.replaceState({}, "", "/chat/hire/agent-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    renderHook(() => useWorkspaceSettings());

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
