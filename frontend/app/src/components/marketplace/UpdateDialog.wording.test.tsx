// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UpdateDialog from "./UpdateDialog";
import { toast } from "sonner";

const { upgrade, fetchAgents } = vi.hoisted(() => ({
  upgrade: vi.fn(),
  fetchAgents: vi.fn(),
}));

vi.mock("@/store/marketplace-store", () => ({
  useMarketplaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      upgrade,
    }),
}));

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      fetchAgents,
    }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UpdateDialog wording contract", () => {
  beforeEach(() => {
    upgrade.mockResolvedValue(undefined);
    fetchAgents.mockResolvedValue(undefined);
  });

  it("uses Chinese product wording for Agent updates", () => {
    render(
      <UpdateDialog
        open
        onOpenChange={() => undefined}
        agentId="agent-user-1"
        agentName="Market Agent"
        update={{
          marketplace_item_id: "hub-item-1",
          source_version: "1.0.0",
          latest_version: "1.1.0",
          release_notes: "new version",
        }}
      />,
    );

    expect(screen.getByText("更新 Market Agent")).toBeTruthy();
    expect(screen.getByText("更新说明")).toBeTruthy();
    expect(screen.getByText("这会覆盖本地 Agent 配置，请确认当前改动已经保留。")).toBeTruthy();
  });

  it("uses Chinese toast wording after Agent update", async () => {
    render(
      <UpdateDialog
        open
        onOpenChange={() => undefined}
        agentId="agent-user-1"
        agentName="Market Agent"
        update={{
          marketplace_item_id: "hub-item-1",
          source_version: "1.0.0",
          latest_version: "1.1.0",
          release_notes: "",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "更新" }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Market Agent 已更新到 v1.1.0");
    });
  });
});
