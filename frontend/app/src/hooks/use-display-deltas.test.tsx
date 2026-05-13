// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatEntry, StreamEvent } from "../api";
import { useDisplayDeltas } from "./use-display-deltas";

const apiMocks = vi.hoisted(() => ({
  cancelRun: vi.fn(async () => undefined),
  postRun: vi.fn(async () => ({ run_id: "run-1", thread_id: "thread-1" })),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    cancelRun: apiMocks.cancelRun,
    postRun: apiMocks.postRun,
  };
});

let latestHandler: ((event: StreamEvent) => void) | null = null;

afterEach(() => {
  latestHandler = null;
  apiMocks.cancelRun.mockReset();
  apiMocks.cancelRun.mockResolvedValue(undefined);
  apiMocks.postRun.mockReset();
  apiMocks.postRun.mockResolvedValue({ run_id: "run-1", thread_id: "thread-1" });
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
  const { isRunning, handleSendMessage, handleStopStreaming } = useDisplayDeltas({
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
      <button data-testid="stop" onClick={() => void handleStopStreaming()} />
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

  it("ignores display deltas with unknown protocol types", () => {
    const initialEntries: ChatEntry[] = [
      {
        id: "user-1",
        role: "user",
        content: "hello",
        timestamp: Date.now(),
      },
    ];

    render(<Harness initialEntries={initialEntries} />);

    act(() => {
      latestHandler?.({
        type: "display_delta",
        data: {
          type: "unknown_delta_type",
          entry: {
            id: "turn-1",
            role: "assistant",
            timestamp: Date.now(),
            segments: [],
          },
        },
      });
    });

    expect(JSON.parse(screen.getByTestId("entries").textContent || "[]")).toEqual(initialEntries);
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

  it("clears pending state without appending an error when startup is cancelled", async () => {
    apiMocks.postRun.mockRejectedValueOnce(new Error("Run cancelled"));

    render(<Harness initialEntries={[]} streamIsRunning={false} />);

    fireEvent.click(screen.getByTestId("send"));

    await waitFor(() => {
      expect(screen.getByTestId("running").textContent).toBe("false");
    });
    expect(JSON.parse(screen.getByTestId("entries").textContent || "[]")).toEqual([]);
  });

  it("closes display-owned running state after stop succeeds", async () => {
    render(<Harness initialEntries={[]} streamIsRunning={false} />);

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

    fireEvent.click(screen.getByTestId("stop"));

    await waitFor(() => {
      expect(screen.getByTestId("running").textContent).toBe("false");
    });
  });
});
