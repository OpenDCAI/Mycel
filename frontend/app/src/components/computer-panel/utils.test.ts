import { describe, expect, it } from "vitest";

import { parseAgentArgs } from "./utils";

describe("computer-panel arg parsers", () => {
  it("ignores non-string agent args before using alternate keys", () => {
    expect(parseAgentArgs({
      Description: 123,
      description: "Inspect trace rendering",
      Prompt: ["bad"],
      prompt: "Find the current runtime state",
      SubagentType: false,
      subagent_type: "explorer",
    })).toEqual({
      description: "Inspect trace rendering",
      prompt: "Find the current runtime state",
      subagent_type: "explorer",
    });
  });
});
