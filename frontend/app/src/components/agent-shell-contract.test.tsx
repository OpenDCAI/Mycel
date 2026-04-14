// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CreateAgentDialog from "./CreateAgentDialog";
import NewChatDialog from "./NewChatDialog";
import AgentsPage from "../pages/AgentsPage";
import { useAppStore } from "../store/app-store";
import { toast } from "sonner";

vi.mock("zustand/middleware", async () => {
  const actual = await vi.importActual<typeof import("zustand/middleware")>("zustand/middleware");
  return {
    ...actual,
    persist: ((initializer: unknown) => initializer) as typeof actual.persist,
  };
});

vi.mock("./ActorAvatar", () => ({
  default: ({ name }: { name: string }) => <div>{name}</div>,
}));

vi.mock("@/api/client", () => ({
  uploadUserAvatar: vi.fn(),
}));

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children, className }: { children: ReactNode; className?: string }) => <h1 className={className}>{children}</h1>,
  DialogDescription: ({ children, className }: { children: ReactNode; className?: string }) => <p className={className}>{children}</p>,
  DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe("frontend agent wording contract", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    useAppStore.setState({
      agentList: [],
      librarySkills: [],
      libraryMcps: [],
      libraryAgents: [],
      librarySandboxTemplates: [],
      userProfile: { name: "User", initials: "U", email: "" },
      loaded: true,
      error: null,
      loadAll: vi.fn(),
      retry: vi.fn(),
      resetSessionData: vi.fn(),
      fetchAgents: vi.fn(),
      addAgent: vi.fn(),
      updateAgent: vi.fn(),
      updateAgentConfig: vi.fn(),
      publishAgent: vi.fn(),
      deleteAgent: vi.fn(),
      getAgentById: vi.fn(),
      fetchLibrary: vi.fn(),
      fetchLibraryNames: vi.fn(),
      addResource: vi.fn(),
      updateResource: vi.fn(),
      deleteResource: vi.fn(),
      fetchResourceContent: vi.fn(),
      updateResourceContent: vi.fn(),
      fetchProfile: vi.fn(),
      updateProfile: vi.fn(),
      getAgentNames: vi.fn(),
      getResourceUsedBy: vi.fn(),
    });
  });

  it("CreateAgentDialog presents agent wording", () => {
    render(
      <MemoryRouter>
        <CreateAgentDialog open onOpenChange={() => undefined} />
      </MemoryRouter>,
    );

    expect(screen.getByText("创建新 Agent")).toBeTruthy();
    expect(screen.getByText("定义一个新的 AI Agent")).toBeTruthy();
    expect(screen.getByRole("button", { name: "创建并配置 Agent" })).toBeTruthy();
  });

  it("CreateAgentDialog shows the concrete create failure", async () => {
    useAppStore.setState({ addAgent: vi.fn().mockRejectedValue(new Error("quota reached")) });

    render(
      <MemoryRouter>
        <CreateAgentDialog open onOpenChange={() => undefined} />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/名称/), { target: { value: "Morel" } });
    fireEvent.click(screen.getByRole("button", { name: "创建并配置 Agent" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("创建失败：quota reached");
    });
  });

  it("NewChatDialog presents agent wording", () => {
    render(
      <MemoryRouter>
        <NewChatDialog open onOpenChange={() => undefined} />
      </MemoryRouter>,
    );

    expect(screen.getByText("创建 Agent 新线程")).toBeTruthy();
    expect(screen.getByPlaceholderText("搜索 Agent...")).toBeTruthy();
    expect(screen.getByText("暂无 Agent")).toBeTruthy();
  });

  it("AgentsPage presents agent wording", () => {
    render(
      <MemoryRouter>
        <AgentsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Agent")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /创建 Agent/ }).length).toBeGreaterThan(0);
    expect(screen.getByPlaceholderText("搜索 Agent...")).toBeTruthy();
    expect(screen.getByText("还没有 AI Agent")).toBeTruthy();
  });
});
