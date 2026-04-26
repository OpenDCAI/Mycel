// @vitest-environment jsdom

import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRemoteWorkspaceRoot } from "./use-remote-workspace-root";

const { getThreadFileChannel } = vi.hoisted(() => ({
  getThreadFileChannel: vi.fn(),
}));

vi.mock("../../api", () => ({
  getThreadFileChannel,
}));

describe("useRemoteWorkspaceRoot", () => {
  beforeEach(() => {
    getThreadFileChannel.mockReset();
  });

  it("reads remote workspace root from file channel binding instead of terminal state", async () => {
    getThreadFileChannel.mockResolvedValue({
      thread_id: "thread-1",
      files_path: "/workspace/.mycel/files",
      workspace_id: "workspace-1",
      workspace_path: "/workspace",
    });

    const view = renderHook(() => useRemoteWorkspaceRoot({ threadId: "thread-1", isRemote: true }));

    await expect(view.result.current.refreshWorkspaceRoot()).resolves.toBe("/workspace");
    expect(getThreadFileChannel).toHaveBeenCalledWith("thread-1");
  });
});
