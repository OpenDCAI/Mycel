// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewChatPage from "./NewChatPage";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";

const handleGetMainThread = vi.fn();

vi.mock("zustand/middleware", async () => {
  const actual = await vi.importActual<typeof import("zustand/middleware")>("zustand/middleware");
  return {
    ...actual,
    persist: ((initializer: unknown) => initializer) as typeof actual.persist,
  };
});

vi.mock("../components/CenteredInputBox", () => ({
  default: () => <div>centered-input-box</div>,
}));

vi.mock("../components/WorkspaceSetupModal", () => ({
  default: () => null,
}));

vi.mock("../components/FilesystemBrowser", () => ({
  default: () => null,
}));

vi.mock("../components/MemberAvatar", () => ({
  default: ({ name }: { name: string }) => <div>{name}</div>,
}));

vi.mock("../hooks/use-workspace-settings", () => ({
  useWorkspaceSettings: () => ({
    settings: { default_workspace: null, recent_workspaces: [], default_model: "leon:large", enabled_models: ["leon:large"] },
    loading: false,
    hasWorkspace: false,
    refreshSettings: vi.fn(),
    setDefaultWorkspace: vi.fn(),
  }),
}));

vi.mock("../api", () => ({
  postRun: vi.fn(),
}));

vi.mock("../api/client", () => ({
  getDefaultThreadConfig: vi.fn(() => new Promise(() => {})),
  listMyLeases: vi.fn(async () => []),
  saveDefaultThreadConfig: vi.fn(async () => undefined),
}));

function ContextOutlet() {
  return (
    <Outlet
      context={{
        tm: {
          threads: [],
          sandboxTypes: [{ name: "local", available: true }],
          selectedSandbox: "local",
          loading: false,
          setSelectedSandbox: vi.fn(),
          setThreads: vi.fn(),
          refreshThreads: vi.fn(),
          handleCreateThread: vi.fn(),
          handleGetMainThread,
          handleDeleteThread: vi.fn(),
        },
        sidebarCollapsed: false,
        setSidebarCollapsed: vi.fn(),
        setSessionsOpen: vi.fn(),
      }}
    />
  );
}

describe("NewChatPage", () => {
  beforeEach(() => {
    handleGetMainThread.mockReset();
    handleGetMainThread.mockResolvedValue(null);

    useAuthStore.setState({
      token: "token",
      user: { id: "u-1", name: "tester", type: "human", avatar: null },
      agent: null,

      setupInfo: null,
      login: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn(),
      completeRegister: vi.fn(),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });

    useAppStore.setState({
      memberList: [{
        id: "m_xVuNpKJNxblZ",
        name: "Morel",
        description: "",
        status: "active",
        version: "1.0.0",
        avatar_url: "/avatars/morel.png",
        config: {
          prompt: "",
          rules: [],
          tools: [],
          mcps: [],
          skills: [],
          subAgents: [],
        },
        created_at: 0,
        updated_at: 0,
      }],
      taskList: [],
      cronJobs: [],
      librarySkills: [],
      libraryMcps: [],
      libraryAgents: [],
      libraryRecipes: [],
      userProfile: { name: "User", initials: "U", email: "" },
      loaded: true,
      error: null,
      loadAll: vi.fn(),
      retry: vi.fn(),
      resetSessionData: vi.fn(),
      fetchMembers: vi.fn(),
      addMember: vi.fn(),
      updateMember: vi.fn(),
      updateMemberConfig: vi.fn(),
      publishMember: vi.fn(),
      deleteMember: vi.fn(),
      getMemberById: vi.fn(),
      fetchTasks: vi.fn(),
      addTask: vi.fn(),
      updateTask: vi.fn(),
      deleteTask: vi.fn(),
      bulkUpdateTaskStatus: vi.fn(),
      bulkDeleteTasks: vi.fn(),
      fetchCronJobs: vi.fn(),
      addCronJob: vi.fn(),
      updateCronJob: vi.fn(),
      deleteCronJob: vi.fn(),
      triggerCronJob: vi.fn(),
      fetchLibrary: vi.fn(),
      fetchLibraryNames: vi.fn(),
      addResource: vi.fn(),
      updateResource: vi.fn(),
      deleteResource: vi.fn(),
      fetchResourceContent: vi.fn(),
      updateResourceContent: vi.fn(),
      fetchProfile: vi.fn(),
      updateProfile: vi.fn(),
      getMemberNames: vi.fn(),
      getResourceUsedBy: vi.fn(),
    });
  });

  it("does not block the create-chat UI on a pending default-config fetch once the default thread resolves null", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:memberId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("开始与 Morel 对话")).toBeTruthy();
    });
    expect(screen.queryByText("正在检查 Morel 的默认线程")).toBeNull();
    expect(screen.getByText("centered-input-box")).toBeTruthy();
  });

  it("uses default-thread wording while resolving the template entry", async () => {
    handleGetMainThread.mockReset();
    handleGetMainThread.mockImplementation(() => new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:memberId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("正在检查 Morel 的默认线程")).toBeTruthy();
    expect(screen.getByText("如果没有默认线程，这里会进入创建界面。")).toBeTruthy();
  });
});
