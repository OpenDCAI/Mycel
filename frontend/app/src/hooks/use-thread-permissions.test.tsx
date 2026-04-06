// @vitest-environment jsdom

import { render } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useThreadPermissions } from "./use-thread-permissions";

const { getThreadPermissions } = vi.hoisted(() => ({
  getThreadPermissions: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getThreadPermissions,
    addThreadPermissionRule: vi.fn(),
    removeThreadPermissionRule: vi.fn(),
    resolveThreadPermission: vi.fn(),
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

function Harness({ threadId }: { threadId?: string }) {
  const state = useThreadPermissions(threadId);
  useEffect(() => {
    void state.loading;
  }, [state.loading]);
  return null;
}

describe("useThreadPermissions", () => {
  it("does not log an error when an in-flight permissions request is aborted on unmount", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    getThreadPermissions.mockImplementation((_threadId: string, signal?: AbortSignal) => new Promise((_, reject) => {
      signal?.addEventListener("abort", () => {
        reject(new DOMException("The user aborted a request.", "AbortError"));
      });
    }));

    const view = render(<Harness threadId="thread-1" />);
    view.unmount();

    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
