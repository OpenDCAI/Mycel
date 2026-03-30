// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth-store";
import ScheduledTaskEditor from "./scheduled-task-editor";
import { ThreadPicker } from "./thread-picker";

function flush() {
  return Promise.resolve().then(() => Promise.resolve());
}

function findButton(label: string): HTMLButtonElement {
  const buttons = Array.from(document.querySelectorAll("button"));
  const match = buttons.find((button) => button.textContent?.includes(label));
  if (!match) {
    throw new Error(`Button not found: ${label}`);
  }
  return match as HTMLButtonElement;
}

describe("thread picker", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    useAuthStore.setState({ token: "token-1" });
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

  it("loads owned threads and lets the user select one", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        threads: [
          {
            thread_id: "thread-1",
            member_id: "member-a",
            member_name: "Agent A",
            entity_name: "Agent A",
            sidebar_label: "主线对话",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSelect = vi.fn();

    await act(async () => {
      root.render(<ThreadPicker scope="owned" value="" onSelect={onSelect} />);
    });

    await act(async () => {
      findButton("选择 Thread").click();
      await flush();
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/threads?scope=owned", expect.any(Object));
    expect(document.body.textContent).toContain("Agent A");

    await act(async () => {
      findButton("Agent A").click();
      await flush();
    });

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ thread_id: "thread-1" }));
  });

  it("shows empty state when no threads exist", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ threads: [] }),
    }));

    await act(async () => {
      root.render(<ThreadPicker scope="owned" value="" onSelect={vi.fn()} />);
    });

    await act(async () => {
      findButton("选择 Thread").click();
      await flush();
    });

    expect(document.body.textContent).toContain("没有可选 thread");
  });

  it("shows backend error when loading fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      text: async () => "boom",
      status: 500,
      statusText: "Server Error",
    }));

    await act(async () => {
      root.render(<ThreadPicker scope="owned" value="" onSelect={vi.fn()} />);
    });

    await act(async () => {
      findButton("选择 Thread").click();
      await flush();
    });

    expect(document.body.textContent).toContain("加载 thread 失败");
  });

  it("renders selected thread label immediately when options are provided", async () => {
    await act(async () => {
      root.render(
        <ThreadPicker
          scope="owned"
          value="thread-1"
          threads={[{
            thread_id: "thread-1",
            member_id: "member-a",
            member_name: "Agent A",
            entity_name: "Agent A",
            sidebar_label: "主线对话",
          }]}
          onSelect={vi.fn()}
        />,
      );
    });

    expect(document.body.textContent).toContain("Agent A");
    expect(document.body.textContent).not.toContain("已选: thread-1");
  });

  it("uses thread picker inside scheduled task editor", async () => {
    await act(async () => {
      root.render(
        <ScheduledTaskEditor
          open
          mode="create"
          isMobile={false}
          draft={{
            id: "",
            thread_id: "",
            name: "Daily brief",
            instruction: "Summarize the thread.",
            cron_expression: "0 9 * * *",
            enabled: 1,
          }}
          runs={[]}
          onUpdate={vi.fn()}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );
    });

    expect(document.body.textContent).toContain("选择 Thread");
    expect(document.body.textContent).not.toContain("thread-main");
  });
});
