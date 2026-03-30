// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ScheduledTaskEditor from "./scheduled-task-editor";

describe("scheduled task editor", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.innerHTML = "";
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    document.body.innerHTML = "";
  });

  it("applies a preset cron expression when clicked", async () => {
    const onUpdate = vi.fn();

    await act(async () => {
      root.render(
        <ScheduledTaskEditor
          open
          mode="create"
          isMobile={false}
          draft={{
            id: "",
            thread_id: "thread-1",
            name: "Morning Review",
            instruction: "Summarize the thread.",
            cron_expression: "0 9 * * *",
            enabled: 1,
          }}
          runs={[]}
          onUpdate={onUpdate}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );
    });

    const preset = Array.from(document.querySelectorAll("button")).find((button) => button.textContent?.includes("工作日 9:00"));
    if (!preset) throw new Error("preset button not found");

    await act(async () => {
      preset.click();
    });

    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ cron_expression: "0 9 * * 1-5" }));
  });

  it("shows invalid cron feedback and blocks saving", async () => {
    await act(async () => {
      root.render(
        <ScheduledTaskEditor
          open
          mode="create"
          isMobile={false}
          draft={{
            id: "",
            thread_id: "thread-1",
            name: "Morning Review",
            instruction: "Summarize the thread.",
            cron_expression: "0 25 * * *",
            enabled: 1,
          }}
          runs={[]}
          onUpdate={vi.fn()}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );
    });

    expect(document.body.textContent).toContain("无效 Cron");
    const saveButton = Array.from(document.querySelectorAll("button")).find((button) => button.textContent?.includes("创建"));
    if (!saveButton) throw new Error("save button not found");
    expect(saveButton.hasAttribute("disabled")).toBe(true);
  });
});
