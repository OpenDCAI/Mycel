// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SandboxSessionsModal from "./SandboxSessionsModal";
import type { SandboxSession } from "../api";

const { listSandboxSessions } = vi.hoisted(() => ({
  listSandboxSessions: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listSandboxSessions,
    destroySandboxSession: vi.fn(),
  };
});

describe("SandboxSessionsModal", () => {
  beforeEach(() => {
    listSandboxSessions.mockReset();
  });

  it("does not render pause or resume controls for running or paused sessions", async () => {
    const sessions: SandboxSession[] = [
      {
        session_id: "session-running",
        thread_id: "thread-running",
        provider: "local",
        status: "running",
      },
      {
        session_id: "session-paused",
        thread_id: "thread-paused",
        provider: "daytona_selfhost",
        status: "paused",
      },
    ];
    listSandboxSessions.mockResolvedValue(sessions);

    render(<SandboxSessionsModal isOpen onClose={vi.fn()} onSessionMutated={vi.fn()} />);

    await waitFor(() => {
      expect(listSandboxSessions).toHaveBeenCalled();
    });

    expect(screen.queryByTitle("暂停")).toBeNull();
    expect(screen.queryByTitle("恢复")).toBeNull();
    expect(screen.getAllByTitle("销毁")).toHaveLength(2);
  });
});
