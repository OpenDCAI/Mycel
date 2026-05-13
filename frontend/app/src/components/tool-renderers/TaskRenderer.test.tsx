// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ToolStep } from "../../api";
import TaskRenderer from "./TaskRenderer";

function renderTaskRenderer(step: ToolStep) {
  return render(
    <MemoryRouter>
      <TaskRenderer step={step} expanded={false} />
    </MemoryRouter>,
  );
}

function renderExpandedTaskRenderer(step: ToolStep) {
  return render(
    <MemoryRouter initialEntries={["/threads/thread-1"]}>
      <Routes>
        <Route path="/threads/:threadId" element={<TaskRenderer step={step} expanded />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TaskRenderer", () => {
  it("ignores non-string task arg fields instead of treating them as labels", () => {
    renderTaskRenderer({
      id: "tool-1",
      name: "Task",
      args: { description: 123 },
      status: "done",
      timestamp: 1,
    });

    expect(screen.getByText("子任务")).toBeTruthy();
  });

  it("stringifies non-string task output payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      json: async () => ({ result: { answer: "42" } }),
    } as Response);

    renderExpandedTaskRenderer({
      id: "tool-1",
      name: "Task",
      args: { description: "solve" },
      status: "done",
      timestamp: 1,
      subagent_stream: {
        task_id: "task-1",
        thread_id: "thread-1",
        description: "solve",
        status: "completed",
        text: "",
        tool_calls: [],
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    await waitFor(() => {
      expect(screen.getByText(/"answer": "42"/)).toBeTruthy();
    });
  });
});
