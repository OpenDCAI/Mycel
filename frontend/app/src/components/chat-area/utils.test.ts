import { describe, expect, it } from "vitest";

import type { ToolStep } from "../../api";
import { getStepResultSummary, getStepSummary } from "./utils";

function toolStep(overrides: Partial<ToolStep>): ToolStep {
  return {
    id: "tool-1",
    name: "Bash",
    args: {},
    status: "done",
    timestamp: 1,
    ...overrides,
  };
}

describe("chat-area tool summaries", () => {
  it("ignores non-string agent descriptions before reading the prompt", () => {
    const summary = getStepSummary(toolStep({
      name: "Agent",
      args: { Description: 123, Prompt: "Inspect the failing monitor view" },
    }));

    expect(summary).toBe("Inspect the failing monitor view");
  });

  it("ignores non-string file paths", () => {
    const summary = getStepSummary(toolStep({
      name: "Read",
      args: { FilePath: 123 },
    }));

    expect(summary).toBe("Read");
  });

  it("does not split non-string write content", () => {
    const summary = getStepResultSummary(toolStep({
      name: "Write",
      args: { Content: 123 },
      result: "ok",
    }));

    expect(summary).toBe("Wrote file");
  });

  it("does not split non-string edit strings", () => {
    const summary = getStepResultSummary(toolStep({
      name: "Edit",
      args: { OldString: 123, NewString: "new" },
      result: "ok",
    }));

    expect(summary).toBe("Edited file");
  });
});
