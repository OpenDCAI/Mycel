// @vitest-environment jsdom

import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useBackgroundTasks } from "./use-background-tasks";
import type { UseThreadStreamResult } from "./use-thread-stream";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

function Harness() {
  const subscribe: UseThreadStreamResult["subscribe"] = () => () => {};
  useBackgroundTasks({ threadId: "thread-1", subscribe });
  return null;
}

describe("useBackgroundTasks", () => {
  it("does not log a failed task fetch once navigation already left the thread route", async () => {
    window.history.replaceState({}, "", "/chat/hire/thread/thread-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/resources");
      throw new TypeError("Failed to fetch");
    });

    render(<Harness />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/threads/thread-1/tasks");
    });
    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
  });
});
