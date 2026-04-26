// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentDetailPage from "./AgentDetailPage";
import { toast } from "sonner";

const { getAgentById, fetchAgent, updateAgent, updateAgentConfig, ensureLibrary, librarySkills } = vi.hoisted(() => ({
  getAgentById: vi.fn(),
  fetchAgent: vi.fn(),
  updateAgent: vi.fn(),
  updateAgentConfig: vi.fn(),
  ensureLibrary: vi.fn(),
  librarySkills: [] as Array<{ id: string; name: string; desc: string; type: string; created_at: number; updated_at: number }>,
}));

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

const agentFixture = {
  id: "agent-1",
  name: "Agent One",
  description: "desc",
  status: "active",
  version: "1.0.0",
  config_loaded: true,
  config: {
    prompt: "",
    tools: [],
    rules: [],
    skills: [],
    mcpServers: [],
    subAgents: [],
  },
};

function renderAgentDetail() {
  return render(
    <MemoryRouter initialEntries={["/contacts/agents/agent-1"]}>
      <Routes>
        <Route path="/contacts/agents/:id" element={<AgentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      getAgentById,
      fetchAgent,
      updateAgent,
      updateAgentConfig,
      ensureLibrary,
      loadAll: vi.fn(),
      librarySkills,
    }),
}));

vi.mock("@/components/PublishDialog", () => ({
  default: () => null,
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

describe("AgentDetailPage wording contract", () => {
  beforeEach(() => {
    librarySkills.splice(0);
    getAgentById.mockReturnValue(agentFixture);
    fetchAgent.mockResolvedValue(agentFixture);
    ensureLibrary.mockResolvedValue(undefined);
    navigateMock.mockReset();
  });

  it("uses the contacts page as the back target for direct-open agent detail", async () => {
    renderAgentDetail();

    expect(await screen.findByText("Agent One")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button")[0]);

    expect(navigateMock).toHaveBeenCalledWith("/contacts");
  });

  it("uses Agent wording for the subagent module label", () => {
    renderAgentDetail();

    expect(screen.getByRole("button", { name: /子 Agent/ })).toBeTruthy();
  });

  it("does not expose the old fake local test panel", () => {
    renderAgentDetail();

    expect(screen.queryByRole("button", { name: /^测试$/ })).toBeNull();
  });

  it("keeps MCP out of the primary agent config modules", () => {
    renderAgentDetail();

    expect(screen.getByRole("button", { name: /^技能/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^子 Agent/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^MCP\s*\d*$/ })).toBeNull();
    expect(screen.getByText("高级集成")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^MCP 高级/ })).toBeTruthy();
  });

  it("loads full agent detail when the list item is only a summary", async () => {
    getAgentById.mockReturnValue({
      id: "agent-1",
      name: "Agent One",
      status: "active",
      config_loaded: false,
      config: { prompt: "", rules: [], tools: [], mcpServers: [], skills: [], subAgents: [] },
    });

    renderAgentDetail();

    await waitFor(() => {
      expect(fetchAgent).toHaveBeenCalledWith("agent-1");
    });
  });

  it("shows the concrete rename failure", async () => {
    updateAgent.mockRejectedValue(new Error("name already exists"));

    renderAgentDetail();

    fireEvent.doubleClick(screen.getByText("Agent One"));
    fireEvent.change(screen.getByDisplayValue("Agent One"), { target: { value: "Morel" } });
    fireEvent.keyDown(screen.getByDisplayValue("Morel"), { key: "Enter" });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("重命名失败：name already exists");
    });
  });

  it("shows and saves the compaction trigger token setting", async () => {
    getAgentById.mockReturnValue({
      ...agentFixture,
      config: {
        ...agentFixture.config,
        compact: { trigger_tokens: 80000 },
      },
    });

    renderAgentDetail();

    const input = screen.getByLabelText("压缩触发 Token");
    expect((input as HTMLInputElement).value).toBe("80000");

    fireEvent.change(input, { target: { value: "100000" } });
    fireEvent.click(screen.getByRole("button", { name: /保存压缩设置/ }));

    await waitFor(() => {
      expect(updateAgentConfig).toHaveBeenCalledWith("agent-1", {
        compact: { trigger_tokens: 100000 },
      });
    });
  });

  it("keeps MCP advanced config outside the Library picker path", async () => {
    renderAgentDetail();

    expect(ensureLibrary).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^MCP 高级/ }));

    expect(screen.getByText("暂无MCP 服务器")).toBeTruthy();
    expect(ensureLibrary).not.toHaveBeenCalled();
  });

  it("adds a Skill from Library with the Library Skill id", async () => {
    librarySkills.push({
      id: "loadable-skill",
      name: "Loadable Skill",
      desc: "loadable",
      type: "skill",
      created_at: 0,
      updated_at: 0,
    });

    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^技能/ }));
    fireEvent.click(screen.getByText("点击 + 从 Library 添加 技能"));
    fireEvent.click(await screen.findByText("Loadable Skill"));
    fireEvent.click(screen.getByRole("button", { name: /添加 \(1\)/ }));

    await waitFor(() => {
      expect(updateAgentConfig).toHaveBeenCalledWith("agent-1", {
        skills: [
          {
            id: "loadable-skill",
            enabled: true,
          },
        ],
      });
    });
  });

  it("toggles MCP servers with enabled config", async () => {
    getAgentById.mockReturnValue({
      ...agentFixture,
      config: {
        ...agentFixture.config,
        mcpServers: [
          {
            name: "demo-mcp",
            command: "uv",
            args: [],
            env: {},
            enabled: true,
          },
        ],
      },
    });

    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^MCP 高级/ }));
    fireEvent.click(screen.getByRole("switch"));

    await waitFor(() => {
      expect(updateAgentConfig).toHaveBeenCalledWith("agent-1", {
        mcpServers: [
          {
            name: "demo-mcp",
            command: "uv",
            args: [],
            env: {},
            enabled: false,
          },
        ],
      });
    });
  });

  it("does not expose a Library picker for subagents", async () => {
    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^子 Agent/ }));

    expect(screen.queryByTitle("添加子 Agent")).toBeNull();
    expect(screen.queryByRole("heading", { name: /从 Library 添加/ })).toBeNull();
    expect(ensureLibrary).not.toHaveBeenCalled();
  });

  it("keeps subagents editable without a Library add control", () => {
    getAgentById.mockReturnValue({
      ...agentFixture,
      config: {
        ...agentFixture.config,
        subAgents: [{ name: "Helper", desc: "", tools: [], system_prompt: "" }],
      },
    });

    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^子 Agent/ }));

    expect(screen.queryByTitle("添加子 Agent")).toBeNull();
    expect(screen.getAllByText("Helper").length).toBeGreaterThan(0);
  });

  it("uses subagent wording for the empty subagent detail prompt", () => {
    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^子 Agent/ }));

    expect(screen.getByText("选择一个子 Agent 查看详情")).toBeTruthy();
  });

  it("uses subagent wording for editable subagent fields", () => {
    getAgentById.mockReturnValue({
      ...agentFixture,
      config: {
        ...agentFixture.config,
        subAgents: [{ name: "Helper", desc: "", tools: [], system_prompt: "" }],
      },
    });

    renderAgentDetail();

    fireEvent.click(screen.getByRole("button", { name: /^子 Agent/ }));

    expect(screen.getByPlaceholderText("子 Agent 描述...")).toBeTruthy();
  });
});
