import { describe, expect, it } from "vitest";

import { isTasksNavActive, resolveTasksTab, tasksHref } from "./tasks-navigation";

describe("tasks navigation", () => {
  it("uses scheduled tab when query asks for it", () => {
    expect(resolveTasksTab("?tab=scheduled")).toBe("cron");
    expect(resolveTasksTab("?tab=other")).toBe("tasks");
    expect(resolveTasksTab("")).toBe("tasks");
  });

  it("builds stable hrefs for each tasks tab", () => {
    expect(tasksHref("tasks")).toBe("/tasks");
    expect(tasksHref("cron")).toBe("/tasks?tab=scheduled");
  });

  it("marks only the matching tasks entry as active", () => {
    expect(isTasksNavActive("/tasks", "", "tasks")).toBe(true);
    expect(isTasksNavActive("/tasks", "", "cron")).toBe(false);
    expect(isTasksNavActive("/tasks", "?tab=scheduled", "tasks")).toBe(false);
    expect(isTasksNavActive("/tasks", "?tab=scheduled", "cron")).toBe(true);
  });
});
