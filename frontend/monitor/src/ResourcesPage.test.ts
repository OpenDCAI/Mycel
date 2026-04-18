import { describe, expect, it } from "vitest";

import { groupResourceRows } from "./ResourcesPage";
import type { ResourceRow } from "./resources/types";

describe("resource row grouping", () => {
  it("groups sandbox-backed resource rows by sandbox identity before lower runtime-handle residue", () => {
    const resourceRows: ResourceRow[] = [
      {
        id: "sandbox-1:thread-1",
        sandboxId: "sandbox-1",
        threadId: "thread-1",
        agentName: "Toad",
        status: "running",
        startedAt: "2026-04-18T00:00:00",
      },
      {
        id: "sandbox-1:thread-1",
        sandboxId: "sandbox-1",
        threadId: "thread-1",
        agentName: "Toad",
        status: "running",
        startedAt: "2026-04-18T00:00:01",
      },
    ];

    const groups = groupResourceRows(resourceRows);

    expect(groups).toHaveLength(1);
    expect(groups[0].sandboxId).toBe("sandbox-1");
    expect(groups[0].displayId).toBe("sandbox-1");
  });
});
