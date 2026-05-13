// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDirectoryBrowser } from "./use-directory-browser";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useDirectoryBrowser", () => {
  it("reports malformed item payloads instead of storing invalid entries", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        current_path: "/workspace",
        parent_path: "/",
        items: "not-a-list",
      }),
    } as Response);

    const view = renderHook(() => useDirectoryBrowser((path) => `/browse?path=${path}`, "/workspace"));

    await act(async () => {
      await view.result.current.loadPath("/workspace");
    });

    expect(view.result.current.items).toEqual([]);
    expect(view.result.current.error).toBe("Malformed directory browser payload: items must be an array");
  });

  it("ignores non-string error details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      json: async () => ({ detail: { message: "not a string" } }),
    } as Response);

    const view = renderHook(() => useDirectoryBrowser((path) => `/browse?path=${path}`, "/workspace"));

    await act(async () => {
      await view.result.current.loadPath("/workspace");
    });

    expect(view.result.current.error).toBe("加载失败");
  });
});
