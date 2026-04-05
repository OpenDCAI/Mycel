// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatEntry, StreamEvent } from "../api";
import { useDisplayDeltas } from "./use-display-deltas";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    cancelRun: vi.fn(async () => undefined),
    postRun: vi.fn(async () => ({ run_id: "run-1", thread_id: "thread-1" })),
  };
});

let latestHandler: ((event: StreamEvent) => void) | null = null;

afterEach(() => {
  latestHandler = null;
  cleanup();
});

function Harness({
  initialEntries,
  threadId = "thread-1",
  streamIsRunning = true,
}: {
  initialEntries: ChatEntry[];
  threadId?: string;
  streamIsRunning?: boolean;
}) {
  const [entries, setEntries] = useState<ChatEntry[]>(initialEntries);
  const { isRunning, handleSendMessage } = useDisplayDeltas({
    threadId,
    onUpdate: setEntries,
    displaySeq: 0,
    stream: {
      runtimeStatus: null,
      isRunning: streamIsRunning,
      subscribe: (handler) => {
        latestHandler = handler;
        return () => {
          if (latestHandler === handler) latestHandler = null;
        };
      },
    },
  });
  return (
    <>
      <pre data-testid="entries">{JSON.stringify(entries)}</pre>
      <div data-testid="running">{String(isRunning)}</div>
      <button data-testid="send" onClick={() => void handleSendMessage("hello")} />
    </>
  );
}

describe("useDisplayDeltas", () => {
  it("marks the parent Agent tool done when subagent completion arrives", () => {
    const initialEntries: ChatEntry[] = [
      {
        id: "turn-1",
        role: "assistant",
        timestamp: Date.now(),
        segments: [
          {
            type: "tool",
            step: {
              id: "tool-1",
              name: "Agent",
              args: {},
              status: "calling",
              timestamp: Date.now(),
              subagent_stream: {
                task_id: "task-1",
                thread_id: "subagent-task-1",
                description: "inspect workspace",
                text: "",
                tool_calls: [],
                status: "running",
              },
            },
          },
        ],
      },
    ];

    render(<Harness initialEntries={initialEntries} />);

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "update_segment",
          index: 0,
          patch: {
            subagent_stream_status: "completed",
          },
        },
      });
    });

    const entries = JSON.parse(screen.getByTestId("entries").textContent || "[]");
    expect(entries[0].segments[0].step.subagent_stream.status).toBe("completed");
    expect(entries[0].segments[0].step.status).toBe("done");
  });

  it("stops reporting running after the assistant turn finalizes", () => {
    render(<Harness initialEntries={[]} />);

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "append_entry",
          entry: {
            id: "turn-1",
            role: "assistant",
            timestamp: Date.now(),
            streaming: true,
            segments: [],
          },
        },
      });
    });

    expect(screen.getByTestId("running").textContent).toBe("true");

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "finalize_turn",
          timestamp: Date.now(),
        },
      });
    });

    expect(screen.getByTestId("running").textContent).toBe("false");
  });

  it("resets display-owned running state when the child thread changes", () => {
    const view = render(<Harness initialEntries={[]} threadId="thread-1" />);

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "append_entry",
          entry: {
            id: "turn-1",
            role: "assistant",
            timestamp: Date.now(),
            streaming: true,
            segments: [],
          },
        },
      });
    });

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "finalize_turn",
          timestamp: Date.now(),
        },
      });
    });

    expect(screen.getByTestId("running").textContent).toBe("false");

    view.rerender(<Harness initialEntries={[]} threadId="thread-2" />);

    expect(screen.getByTestId("running").textContent).toBe("true");
  });

  it("clears queued-send pending once the assistant turn starts streaming", () => {
    render(<Harness initialEntries={[]} streamIsRunning={false} />);

    fireEvent.click(screen.getByTestId("send"));
    expect(screen.getByTestId("running").textContent).toBe("true");

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "append_entry",
          entry: {
            id: "turn-1",
            role: "assistant",
            timestamp: Date.now(),
            streaming: true,
            segments: [],
          },
        },
      });
    });

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "finalize_turn",
          timestamp: Date.now(),
        },
      });
    });

    expect(screen.getByTestId("running").textContent).toBe("false");
  });
});
