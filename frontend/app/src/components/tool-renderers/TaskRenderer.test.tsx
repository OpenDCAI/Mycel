// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../api";
import TaskRenderer from "./TaskRenderer";

function renderTaskRenderer(step: ToolStep) {
  return render(
    <MemoryRouter>
      <TaskRenderer step={step} expanded={false} />
    </MemoryRouter>,
  );
}

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
});
