// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MarketplaceItemDetail } from "@/store/marketplace-store";

import MarketplaceActionDialog from "./MarketplaceActionDialog";

const mocks = vi.hoisted(() => ({
  applyItem: vi.fn(),
  applying: false,
  fetchAgents: vi.fn(),
  fetchLibrary: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogHeader: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogTitle: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogDescription: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogFooter: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/store/marketplace-store", () => ({
  useMarketplaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      applyItem: mocks.applyItem,
      applying: mocks.applying,
    }),
}));

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      agentList: [{ id: "agent-1", name: "Agent One", builtin: false }],
      ensureAgents: vi.fn(),
      fetchAgents: mocks.fetchAgents,
      fetchLibrary: mocks.fetchLibrary,
    }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: mocks.toastSuccess,
    error: mocks.toastError,
  },
}));

function marketItem(overrides: Partial<MarketplaceItemDetail> = {}): MarketplaceItemDetail {
  return {
    id: "pkg-1",
    slug: "pack-one",
    description: "desc",
    avatar_url: null,
    publisher_user_id: "user-1",
    name: "Pack One",
    type: "member",
    publisher_username: "tester",
    parent_id: null,
    download_count: 0,
    visibility: "public",
    tags: [],
    created_at: "2026-04-08T00:00:00Z",
    updated_at: "2026-04-08T00:00:00Z",
    versions: [{ id: "ver-1", version: "1.0.0", release_notes: null, created_at: "2026-04-08T00:00:00Z" }],
    parent: null,
    ...overrides,
  };
}

function skillItem(): MarketplaceItemDetail {
  return marketItem({
    id: "skill-1",
    slug: "fastapi",
    name: "FastAPI",
    type: "skill",
  });
}

function renderDialog(item: MarketplaceItemDetail = marketItem()) {
  return render(<MarketplaceActionDialog open onOpenChange={vi.fn()} item={item} />);
}

afterEach(() => {
  mocks.applyItem.mockReset();
  mocks.applying = false;
  mocks.fetchAgents.mockReset();
  mocks.fetchLibrary.mockReset();
  mocks.fetchAgents.mockResolvedValue(undefined);
  mocks.fetchLibrary.mockResolvedValue(undefined);
  mocks.toastSuccess.mockReset();
  mocks.toastError.mockReset();
  cleanup();
});

describe("MarketplaceActionDialog wording contract", () => {
  it("uses Agent wording for Hub agent-user actions", () => {
    renderDialog();

    expect(document.body.textContent).toContain("添加 Pack One");
    expect(screen.getByText("这将把该 Agent 添加到你的 Agent 列表。")).toBeTruthy();
    expect(screen.getByText("添加 Agent")).toBeTruthy();
    expect(screen.queryByText(/member/)).toBeNull();
  });

  it("refreshes Agents after Hub agent-user action", async () => {
    mocks.applyItem.mockResolvedValue({
      user_id: "agent-user-1",
      type: "user",
      version: "1.0.0",
    });

    renderDialog();

    fireEvent.click(screen.getByText("添加 Agent"));

    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith("Pack One 已添加到 Agent 列表");
    });
    expect(mocks.applyItem).toHaveBeenCalledWith("pkg-1", undefined);
    expect(mocks.fetchAgents).toHaveBeenCalled();
    expect(mocks.fetchLibrary).not.toHaveBeenCalled();
  });

  it("uses add wording while a Hub agent-user action is in progress", () => {
    mocks.applying = true;

    renderDialog();

    expect(screen.getByText("添加中...")).toBeTruthy();
  });

  it("uses add failure wording for Hub agent-user errors", async () => {
    mocks.applyItem.mockRejectedValue(new Error("boom"));

    renderDialog();
    fireEvent.click(screen.getByText("添加 Agent"));

    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith("添加失败：boom");
    });
  });

  it("defaults Skill saves to Library and keeps Agent assignment optional", () => {
    renderDialog(skillItem());

    expect(screen.getByText("这将把该 Skill 保存到 Library，之后可以在 Agent 配置页中添加使用。")).toBeTruthy();
    expect(document.body.textContent).toContain("保存 FastAPI");
    expect(screen.getByText("保存到 Library 后赋给 Agent")).toBeTruthy();
    expect(screen.getByText("保存到 Library")).toBeTruthy();
    expect(document.querySelector(".lucide-package-plus")).toBeTruthy();
    expect(document.querySelector(".lucide-download")).toBeNull();

    fireEvent.click(screen.getByLabelText("保存到 Library 后赋给 Agent"));

    expect(screen.getByText("Agent One")).toBeTruthy();
    expect(screen.getByText("保存到 Library 并赋给 Agent")).toBeTruthy();
  });

  it("does not pass an Agent id when saving a Skill to Library only", async () => {
    mocks.applyItem.mockResolvedValue({
      resource_id: "fastapi",
      type: "skill",
      version: "1.0.0",
    });

    renderDialog(skillItem());
    fireEvent.click(screen.getByText("保存到 Library"));

    await waitFor(() => {
      expect(mocks.applyItem).toHaveBeenCalledWith("skill-1", undefined);
    });
    expect(mocks.fetchLibrary).toHaveBeenCalledWith("skill");
    expect(mocks.fetchAgents).not.toHaveBeenCalled();
  });

  it("shows Library-first success wording without internal ids", async () => {
    mocks.applyItem.mockResolvedValue({
      resource_id: "fastapi",
      type: "skill",
      version: "1.0.0",
      agent_user_id: "agent-1",
    });

    renderDialog(skillItem());
    fireEvent.click(screen.getByLabelText("保存到 Library 后赋给 Agent"));
    fireEvent.click(screen.getByText("保存到 Library 并赋给 Agent"));

    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith("FastAPI 已保存到 Library，并已赋给 Agent");
    });
    expect(mocks.applyItem).toHaveBeenCalledWith("skill-1", "agent-1");
    expect(mocks.fetchLibrary).toHaveBeenCalledWith("skill");
    expect(mocks.fetchAgents).toHaveBeenCalled();
    expect(mocks.toastSuccess).not.toHaveBeenCalledWith(expect.stringContaining("fastapi"));
  });
});
