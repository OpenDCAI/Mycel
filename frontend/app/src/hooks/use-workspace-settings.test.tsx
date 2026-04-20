// @vitest-environment jsdom

import { act, renderHook, waitFor } from "@testing-library/react";
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

  it("ignores non-string workspace error details", async () => {
    window.history.replaceState({}, "", "/chat/hire/agent-1");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          default_workspace: null,
          recent_workspaces: [],
          default_model: "leon:large",
          enabled_models: ["leon:large"],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: { message: "not a string" } }),
      } as Response);

    const view = renderHook(() => useWorkspaceSettings());

    await waitFor(() => {
      expect(view.result.current.loading).toBe(false);
    });

    await expect(act(async () => {
      await view.result.current.setDefaultWorkspace("/workspace");
    })).rejects.toThrow("Failed to set workspace");
  });
});
