// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes, useParams } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewChatPage from "./NewChatPage";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";

const handleGetDefaultThread = vi.fn();
const clientMocks = vi.hoisted(() => ({
  getDefaultThreadConfig: vi.fn(() => new Promise(() => {})),
}));

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
  getDefaultThreadConfig: clientMocks.getDefaultThreadConfig,
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
          handleGetDefaultThread,
          handleDeleteThread: vi.fn(),
        },
        sidebarCollapsed: false,
        setSidebarCollapsed: vi.fn(),
        setSessionsOpen: vi.fn(),
      }}
    />
  );
}

function ThreadRouteProbe() {
  const { threadId } = useParams<{ threadId: string }>();
  return <div>{`thread-route:${threadId}`}</div>;
}

describe("NewChatPage", () => {
  beforeEach(() => {
    handleGetDefaultThread.mockReset();
    handleGetDefaultThread.mockResolvedValue(null);
    clientMocks.getDefaultThreadConfig.mockReset();
    clientMocks.getDefaultThreadConfig.mockImplementation(() => new Promise(() => {}));

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
      agentList: [{
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
      fetchAgents: vi.fn(),
      addAgent: vi.fn(),
      updateAgent: vi.fn(),
      updateAgentConfig: vi.fn(),
      publishAgent: vi.fn(),
      deleteAgent: vi.fn(),
      getAgentById: vi.fn(),
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
      getAgentNames: vi.fn(),
      getResourceUsedBy: vi.fn(),
    });
  });

  it("does not block the create-chat UI on a pending default-config fetch once the default thread resolves null", async () => {
    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
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
    handleGetDefaultThread.mockReset();
    handleGetDefaultThread.mockImplementation(() => new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("正在检查 Morel 的默认线程")).toBeTruthy();
    expect(screen.getByText("如果没有默认线程，这里会进入创建界面。")).toBeTruthy();
  });

  it("navigates resolved default threads through the thread-only hire route", async () => {
    handleGetDefaultThread.mockResolvedValue({ thread_id: "thread-42" });

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
            <Route path="/chat/hire/thread/:threadId" element={<ThreadRouteProbe />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("thread-route:thread-42")).toBeTruthy();
    });
  });

  it("does not log a failed default-config fetch once navigation already left the hire route", async () => {
    clientMocks.getDefaultThreadConfig.mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
            <Route path="/chat" element={<div>chat-page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(clientMocks.getDefaultThreadConfig).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });

  it("does not log a failed default-thread resolve once navigation already left the hire route", async () => {
    handleGetDefaultThread.mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
            <Route path="/chat" element={<div>chat-page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(handleGetDefaultThread).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
