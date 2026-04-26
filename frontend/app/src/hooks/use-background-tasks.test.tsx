// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useBackgroundTasks } from "./use-background-tasks";
import type { UseThreadStreamResult } from "./use-thread-stream";
import { authFetch } from "../store/auth-store";

vi.mock("../store/auth-store", () => ({
  authFetch: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

function Harness() {
  const subscribe: UseThreadStreamResult["subscribe"] = () => () => {};
  const { tasks } = useBackgroundTasks({ threadId: "thread-1", subscribe });
  return <pre data-testid="tasks">{JSON.stringify(tasks)}</pre>;
}

describe("useBackgroundTasks", () => {
  it("does not log a failed task fetch once navigation already left the thread route", async () => {
    window.history.replaceState({}, "", "/chat/hire/thread/thread-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const authFetchMock = vi.mocked(authFetch).mockImplementation(async () => {
      window.history.replaceState({}, "", "/resources");
      throw new TypeError("Failed to fetch");
    });

    render(<Harness />);

    await waitFor(() => {
      expect(authFetchMock).toHaveBeenCalledWith("/api/threads/thread-1/tasks");
    });
    await Promise.resolve();

    expect(consoleError).not.toHaveBeenCalled();
  });

  it("reports malformed task list payloads instead of storing invalid task state", async () => {
    window.history.replaceState({}, "", "/chat/hire/thread/thread-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ items: "not-a-task-list" }),
    } as Response);

    render(<Harness />);

    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledWith(
        "[BackgroundTasks] Error fetching tasks:",
        expect.objectContaining({
          message: "Malformed background task payload: expected task array",
        }),
      );
    });
    expect(screen.getByTestId("tasks").textContent).toBe("[]");
  });

  it("accepts the backend cancelled task status", async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          task_id: "task-1",
          task_type: "agent",
          status: "cancelled",
          description: "cancelled probe",
        },
      ],
    } as Response);

    render(<Harness />);

    await waitFor(() => {
      expect(JSON.parse(screen.getByTestId("tasks").textContent || "[]")).toEqual([
        {
          task_id: "task-1",
          task_type: "agent",
          status: "cancelled",
          description: "cancelled probe",
        },
      ]);
    });
  });
});
