// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NewChatPage from "./NewChatPage";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";
import type { AccountResourceLimit, SandboxType } from "../api/types";

const handleGetDefaultThread = vi.fn();
const handleCreateThread = vi.fn();
const clientMocks = vi.hoisted(() => ({
  getDefaultThreadConfig: vi.fn(() => new Promise(() => {})),
  fetchAccountResourceLimits: vi.fn<() => Promise<AccountResourceLimit[]>>(async () => []),
}));

vi.mock("zustand/middleware", async () => {
  const actual = await vi.importActual<typeof import("zustand/middleware")>("zustand/middleware");
  return {
    ...actual,
    persist: ((initializer: unknown) => initializer) as typeof actual.persist,
  };
});

vi.mock("../components/CenteredInputBox", () => ({
  default: ({ environmentControl, onSend }: {
    environmentControl: {
      summary: React.ReactNode;
      applyLabel?: string;
      applyDisabled?: boolean;
      onApply?: (draftModel: string) => boolean | Promise<boolean>;
      renderPanel: (args: {
        draftModel: string;
        setDraftModel: (value: string) => void;
      }) => React.ReactNode;
    };
    onSend?: (message: string, model: string) => Promise<void>;
  }) => (
    <div>
      <div>centered-input-box</div>
      <div data-testid="environment-summary">{environmentControl.summary}</div>
      <button
        disabled={environmentControl.applyDisabled}
        onClick={() => {
          void environmentControl.onApply?.("leon:large");
        }}
      >
        {environmentControl.applyLabel ?? "确认"}
      </button>
      <button
        onClick={() => {
          void onSend?.("hello from test", "leon:large");
        }}
      >
        发送测试消息
      </button>
      {environmentControl.renderPanel({ draftModel: "leon:large", setDraftModel: () => undefined })}
    </div>
  ),
}));

vi.mock("../components/FilesystemBrowser", () => ({
  default: () => <div>filesystem-browser</div>,
}));

vi.mock("../components/ActorAvatar", () => ({
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
  postRun: vi.fn(async () => undefined),
}));

vi.mock("../api/client", () => ({
  getDefaultThreadConfig: clientMocks.getDefaultThreadConfig,
  listMyLeases: vi.fn(async () => []),
  saveDefaultThreadConfig: vi.fn(async () => undefined),
}));

vi.mock("../api/settings", () => ({
  fetchAccountResourceLimits: clientMocks.fetchAccountResourceLimits,
}));

let sandboxTypesForTest: SandboxType[] = [{ name: "local", available: true }];

function ContextOutlet() {
  return (
    <Outlet
      context={{
        tm: {
          threads: [],
          sandboxTypes: sandboxTypesForTest,
          selectedSandbox: "local",
          loading: false,
          refreshThreads: vi.fn(),
          handleCreateThread,
          handleGetDefaultThread,
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
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    handleGetDefaultThread.mockReset();
    handleGetDefaultThread.mockResolvedValue(null);
    handleCreateThread.mockReset();
    handleCreateThread.mockResolvedValue("thread-from-test");
    clientMocks.getDefaultThreadConfig.mockReset();
    clientMocks.getDefaultThreadConfig.mockImplementation(() => new Promise(() => {}));
    clientMocks.fetchAccountResourceLimits.mockReset();
    clientMocks.fetchAccountResourceLimits.mockResolvedValue([]);
    sandboxTypesForTest = [{ name: "local", available: true }];

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

  it("uses the embedded filesystem browser as the local workspace picker", async () => {
    clientMocks.getDefaultThreadConfig.mockResolvedValue({
      source: "derived",
      config: {
        create_mode: "new",
        provider_config: "local",
        recipe: {
          id: "local-recipe",
          name: "Local",
          provider_type: "local",
          features: {},
          configurable_features: {},
          feature_options: [],
        },
        lease_id: null,
        model: "leon:large",
        workspace: null,
      },
    });
    useAppStore.setState({
      libraryRecipes: [{
        id: "local-recipe",
        type: "recipe",
        name: "Local",
        desc: "",
        provider_type: "local",
        available: true,
        created_at: 0,
        updated_at: 0,
      }],
    });

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("centered-input-box");
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "下一步" })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    expect(await screen.findByText("选择工作区")).toBeTruthy();
    expect(screen.getByText("filesystem-browser")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "浏览" })).toBeNull();
    expect((screen.getByRole("button", { name: "确认" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("uses sandbox-template wording instead of bare Recipe wording in the new sandbox flow", async () => {
    clientMocks.getDefaultThreadConfig.mockResolvedValue({
      source: "derived",
      config: {
        create_mode: "new",
        provider_config: "local",
        recipe: {
          id: "local-recipe",
          name: "Local",
          provider_type: "local",
          features: {},
          configurable_features: {},
          feature_options: [],
        },
        lease_id: null,
        model: "leon:large",
        workspace: null,
      },
    });
    useAppStore.setState({
      libraryRecipes: [{
        id: "local-recipe",
        type: "recipe",
        name: "Local",
        desc: "",
        provider_type: "local",
        available: true,
        created_at: 0,
        updated_at: 0,
      }],
    });

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("centered-input-box");
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    expect(await screen.findByText("确认沙盒模板与工具")).toBeTruthy();
    expect(screen.getByText("沙盒模板")).toBeTruthy();
    expect(screen.queryByText("确认 Recipe 与工具")).toBeNull();
    expect(screen.queryByText("Recipe")).toBeNull();
  });

  it("launches a new thread with the selected sandbox template snapshot", async () => {
    clientMocks.getDefaultThreadConfig.mockResolvedValue({
      source: "derived",
      config: {
        create_mode: "new",
        provider_config: "local",
        recipe_id: "local-recipe",
        recipe: {
          id: "stale-display-snapshot",
          name: "Local",
          provider_type: "local",
          features: { lark_cli: false },
          configurable_features: { lark_cli: true },
          feature_options: [{ key: "lark_cli", name: "Lark CLI", description: "Install Lark CLI" }],
        },
        lease_id: null,
        model: "leon:large",
        workspace: null,
      },
    });
    useAppStore.setState({
      libraryRecipes: [{
        id: "other-recipe",
        type: "recipe",
        name: "Other Local",
        desc: "",
        provider_type: "local",
        features: {},
        configurable_features: {},
        feature_options: [],
        available: true,
        created_at: 0,
        updated_at: 0,
      }, {
        id: "local-recipe",
        type: "recipe",
        name: "Local",
        desc: "",
        provider_type: "local",
        features: { lark_cli: true },
        configurable_features: { lark_cli: true },
        feature_options: [{ key: "lark_cli", name: "Lark CLI", description: "Install Lark CLI" }],
        available: true,
        created_at: 0,
        updated_at: 0,
      }],
    });

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

    await screen.findByText("centered-input-box");
    fireEvent.click(screen.getByRole("button", { name: "发送测试消息" }));

    await waitFor(() => {
      expect(handleCreateThread).toHaveBeenCalledWith(
        "local",
        undefined,
        "m_xVuNpKJNxblZ",
        "leon:large",
        undefined,
        "local-recipe",
      );
    });
  });

  it("blocks advancing a new sandbox selection when backend account resources say the provider is exhausted", async () => {
    sandboxTypesForTest = [{ name: "daytona_selfhost", provider: "daytona", available: true }];
    clientMocks.fetchAccountResourceLimits.mockResolvedValue([
      {
        resource: "sandbox",
        provider_name: "daytona_selfhost",
        label: "Self-host Daytona",
        limit: 2,
        used: 2,
        remaining: 0,
        can_create: false,
      },
    ]);
    clientMocks.getDefaultThreadConfig.mockResolvedValue({
      source: "derived",
      config: {
        create_mode: "new",
        provider_config: "daytona_selfhost",
        recipe: {
          id: "daytona-recipe",
          name: "Self-host Daytona",
          provider_type: "daytona",
          features: {},
          configurable_features: {},
          feature_options: [],
        },
        lease_id: null,
        model: "leon:large",
        workspace: null,
      },
    });
    useAppStore.setState({
      libraryRecipes: [{
        id: "daytona-recipe",
        type: "recipe",
        name: "Self-host Daytona",
        desc: "",
        provider_type: "daytona",
        available: true,
        created_at: 0,
        updated_at: 0,
      }],
    });

    render(
      <MemoryRouter initialEntries={["/chat/hire/m_xVuNpKJNxblZ"]}>
        <Routes>
          <Route element={<ContextOutlet />}>
            <Route path="/chat/hire/:agentId" element={<NewChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Self-host Daytona 已达上限")).toBeTruthy();
    expect((screen.getByRole("button", { name: "下一步" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
