// @vitest-environment jsdom

import { act, render } from "@testing-library/react";
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
  vi.useRealTimers();
  window.history.replaceState({}, "", "/");
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
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    getThreadPermissions.mockImplementation(
      (_threadId: string, signal?: AbortSignal) =>
        new Promise((_, reject) => {
          signal?.addEventListener("abort", () => {
            reject(
              new DOMException("The user aborted a request.", "AbortError"),
            );
          });
        }),
    );

    const view = render(<Harness threadId="thread-1" />);
    view.unmount();

    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("does not log a failed fetch once navigation already left the thread route", async () => {
    window.history.replaceState({}, "", "/chat/hire/member-1/thread-1");
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    getThreadPermissions.mockImplementation(async () => {
      window.history.replaceState({}, "", "/resources");
      throw new TypeError("Failed to fetch");
    });

    render(<Harness threadId="thread-1" />);

    await Promise.resolve();
    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("stops polling permissions after an active-route terminal error", async () => {
    vi.useFakeTimers();
    window.history.replaceState({}, "", "/chat/hire/member-1/thread-1");
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    getThreadPermissions.mockRejectedValue(
      new Error(
        'API 503: {"detail":"Sandbox agent init failed for daytona_selfhost: No module named \'daytona_sdk\'"}',
      ),
    );

    render(<Harness threadId="thread-1" />);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getThreadPermissions).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(6000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getThreadPermissions).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });
});
