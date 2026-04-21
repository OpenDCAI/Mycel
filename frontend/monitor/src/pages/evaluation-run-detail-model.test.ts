import { describe, expect, it } from "vitest";

import { buildArtifactDownloadPayload, summarizeTrajectory } from "./evaluation-run-detail-model";

describe("evaluation run detail helpers", () => {
  it("downloads artifact content as text when inline content exists", () => {
    expect(
      buildArtifactDownloadPayload("run-1", {
        name: "patch.diff",
        mime_type: "text/x-diff",
        content: "diff --git a b",
      }),
    ).toEqual({
      filename: "run-1-patch.diff.txt",
      mimeType: "text/x-diff",
      text: "diff --git a b",
    });
  });

  it("falls back to artifact json when no inline content exists", () => {
    const payload = buildArtifactDownloadPayload("run-1", {
      name: "judge",
      kind: "judge_result",
      metadata: { verdict: "passed" },
    });

    expect(payload.filename).toBe("run-1-judge.json");
    expect(payload.mimeType).toBe("application/json");
    expect(payload.text).toContain("\"judge_result\"");
    expect(payload.text).toContain("\"passed\"");
  });

  it("summarizes trajectory availability without assuming either channel exists", () => {
    expect(summarizeTrajectory({ conversation: [{ role: "user" }], events: [] })).toEqual({
      messageCount: 1,
      eventCount: 0,
      hasTrace: true,
    });

    expect(summarizeTrajectory({ conversation: [], events: [] })).toEqual({
      messageCount: 0,
      eventCount: 0,
      hasTrace: false,
    });
  });
});
