import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../api";
import { resolveAgentVisualStatus } from "./agent-visual-status";

function makeStep(): ToolStep {
  return {
    id: "tool-1",
    name: "Agent",
    args: {},
    status: "calling",
    timestamp: Date.now(),
    subagent_stream: {
      task_id: "task-1",
      thread_id: "subagent-1",
      description: "inspect",
      text: "done text",
      tool_calls: [],
      status: "running",
    },
  };
}

describe("resolveAgentVisualStatus", () => {
  it("trusts the child thread idle state over a stale parent running badge", () => {
    expect(
      resolveAgentVisualStatus(makeStep(), {
        childDisplayRunning: false,
        childRuntimeState: "idle",
      }),
    ).toBe("completed");
  });

  it("keeps the agent running while the child display is still open", () => {
    expect(
      resolveAgentVisualStatus(makeStep(), {
        childDisplayRunning: true,
        childRuntimeState: "active",
      }),
    ).toBe("running");
  });
});
