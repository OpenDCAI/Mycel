import { describe, expect, it } from "vitest";

import { groupResourceSessions } from "./ResourcesPage";
import type { ResourceSession } from "./resources/types";

describe("resource session grouping", () => {
  it("groups sandbox-backed resource sessions by sandbox identity before legacy lease residue", () => {
    const sessions: ResourceSession[] = [
      {
        id: "sandbox-1:thread-1",
        sandboxId: "sandbox-1",
        leaseId: "lease-old",
        threadId: "thread-1",
        agentName: "Toad",
        status: "running",
        startedAt: "2026-04-18T00:00:00",
      },
      {
        id: "sandbox-1:thread-1",
        sandboxId: "sandbox-1",
        leaseId: "lease-new",
        threadId: "thread-1",
        agentName: "Toad",
        status: "running",
        startedAt: "2026-04-18T00:00:01",
      },
    ];

    const groups = groupResourceSessions(sessions);

    expect(groups).toHaveLength(1);
    expect(groups[0].sandboxId).toBe("sandbox-1");
    expect(groups[0].displayId).toBe("sandbox-1");
  });
});
