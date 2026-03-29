import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "./app-store";
import { useAuthStore } from "./auth-store";

describe("app-store scheduled tasks", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null });
    useAppStore.setState({
      scheduledTasks: [],
      scheduledTaskRuns: {},
      error: null,
    });
  });

  it("fetchScheduledTasks loads scheduled task list into store", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "scheduled-1",
            thread_id: "thread-1",
            name: "Daily sync",
            instruction: "Summarize thread activity.",
            cron_expression: "0 9 * * *",
            enabled: 1,
            last_triggered_at: 0,
            next_trigger_at: 1740000000,
            created_at: 1730000000,
            updated_at: 1730000000,
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await useAppStore.getState().fetchScheduledTasks();

    expect(fetchMock).toHaveBeenCalledWith("/api/panel/scheduled-tasks", expect.any(Object));
    expect(useAppStore.getState().scheduledTasks).toHaveLength(1);
    expect(useAppStore.getState().scheduledTasks[0]?.thread_id).toBe("thread-1");
  });

  it("triggerScheduledTask stores latest runs for the scheduled task", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          item: {
            id: "run-1",
            scheduled_task_id: "scheduled-1",
            thread_id: "thread-1",
            status: "dispatched",
            triggered_at: 1740000001,
            started_at: 1740000002,
            completed_at: 0,
            thread_run_id: "thread-run-1",
            error: "",
            dispatch_result: { status: "started", routing: "direct" },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "run-1",
              scheduled_task_id: "scheduled-1",
              thread_id: "thread-1",
              status: "dispatched",
              triggered_at: 1740000001,
              started_at: 1740000002,
              completed_at: 0,
              thread_run_id: "thread-run-1",
              error: "",
              dispatch_result: { status: "started", routing: "direct" },
            },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const run = await useAppStore.getState().triggerScheduledTask("scheduled-1");

    expect(run.thread_run_id).toBe("thread-run-1");
    expect(useAppStore.getState().scheduledTaskRuns["scheduled-1"]).toHaveLength(1);
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/panel/scheduled-tasks/scheduled-1/run", expect.any(Object));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/panel/scheduled-tasks/scheduled-1/runs", expect.any(Object));
  });
});
