// @vitest-environment jsdom

import { render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useThreadData } from "./use-thread-data";

const { getThread } = vi.hoisted(() => ({
  getThread: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getThread,
  };
});

afterEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});

function Harness({ threadId }: { threadId?: string }) {
  const state = useThreadData(threadId);
  useEffect(() => {
    void state.loading;
  }, [state.loading]);
  return null;
}

describe("useThreadData", () => {
  it("does not log a failed fetch once navigation already left the thread route", async () => {
    window.history.replaceState({}, "", "/chat/hire/thread/thread-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    getThread.mockImplementation(async () => {
      window.history.replaceState({}, "", "/resources");
      throw new TypeError("Failed to fetch");
    });

    render(<Harness threadId="thread-1" />);

    await waitFor(() => {
      expect(getThread).toHaveBeenCalledWith("thread-1");
    });
    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
