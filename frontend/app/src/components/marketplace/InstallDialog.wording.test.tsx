// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InstallDialog from "./InstallDialog";

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
      download: vi.fn(),
      downloading: false,
    }),
}));

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      agentList: [{ id: "agent-1", name: "Toad", builtin: false }],
      ensureAgents: vi.fn(),
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
});

describe("InstallDialog wording contract", () => {
  it("uses Agent wording for Hub agent-user installs", () => {
    render(
      <InstallDialog
        open
        onOpenChange={vi.fn()}
        item={{
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
        }}
      />,
    );

    expect(screen.getByText("这将把该 Agent 保存到本地库，之后可以在 Agent 配置页中添加使用。")).toBeTruthy();
    expect(screen.queryByText(/member/)).toBeNull();
  });

  it("requires a target Agent for Skill installs", () => {
    render(
      <InstallDialog
        open
        onOpenChange={vi.fn()}
        item={{
          id: "skill-1",
          slug: "fastapi",
          description: "desc",
          avatar_url: null,
          publisher_user_id: "user-1",
          name: "FastAPI",
          type: "skill",
          publisher_username: "tester",
          parent_id: null,
          download_count: 0,
          visibility: "public",
          tags: [],
          created_at: "2026-04-08T00:00:00Z",
          updated_at: "2026-04-08T00:00:00Z",
          versions: [{ id: "ver-1", version: "1.0.0", release_notes: null, created_at: "2026-04-08T00:00:00Z" }],
          parent: null,
        }}
      />,
    );

    expect(screen.getByText("这将把该 Skill 直接安装到选中的 Agent，随后对话运行时可通过 load_skill 按需加载。")).toBeTruthy();
    expect(screen.getAllByText("安装到 Agent").length).toBeGreaterThan(0);
    expect(screen.getByText("Toad")).toBeTruthy();
  });
});
