// @vitest-environment jsdom

import { act, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
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

function Harness({ initialEntries }: { initialEntries: ChatEntry[] }) {
  const [entries, setEntries] = useState<ChatEntry[]>(initialEntries);
  useDisplayDeltas({
    threadId: "thread-1",
    onUpdate: setEntries,
    displaySeq: 0,
    stream: {
      runtimeStatus: null,
      isRunning: false,
      subscribe: (handler) => {
        latestHandler = handler;
        return () => {
          if (latestHandler === handler) latestHandler = null;
        };
      },
    },
  });
  return <pre data-testid="entries">{JSON.stringify(entries)}</pre>;
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
});
