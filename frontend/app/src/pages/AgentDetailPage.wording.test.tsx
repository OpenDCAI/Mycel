// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentDetailPage from "./AgentDetailPage";
import { toast } from "sonner";

const { getAgentById, fetchAgent, updateAgent, updateAgentConfig } = vi.hoisted(() => ({
  getAgentById: vi.fn(),
  fetchAgent: vi.fn(),
  updateAgent: vi.fn(),
  updateAgentConfig: vi.fn(),
}));

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
    mcps: [],
    subAgents: [],
  },
};

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      getAgentById,
      fetchAgent,
      updateAgent,
      updateAgentConfig,
      loadAll: vi.fn(),
      librarySkills: [],
      libraryMcps: [],
      libraryAgents: [],
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
    getAgentById.mockReturnValue(agentFixture);
    fetchAgent.mockResolvedValue(agentFixture);
  });

  it("uses Agent wording for the subagent module label", () => {
    render(
      <MemoryRouter initialEntries={["/contacts/agents/agent-1"]}>
        <Routes>
          <Route path="/contacts/agents/:id" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /子 Agent/ })).toBeTruthy();
  });

  it("does not expose the old fake local test panel", () => {
    render(
      <MemoryRouter initialEntries={["/contacts/agents/agent-1"]}>
        <Routes>
          <Route path="/contacts/agents/:id" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByRole("button", { name: /^测试$/ })).toBeNull();
  });

  it("loads full agent detail when the list item is only a summary", async () => {
    getAgentById.mockReturnValue({
      id: "agent-1",
      name: "Agent One",
      status: "active",
      config_loaded: false,
      config: { prompt: "", rules: [], tools: [], mcps: [], skills: [], subAgents: [] },
    });

    render(
      <MemoryRouter initialEntries={["/contacts/agents/agent-1"]}>
        <Routes>
          <Route path="/contacts/agents/:id" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(fetchAgent).toHaveBeenCalledWith("agent-1");
    });
  });

  it("shows the concrete rename failure", async () => {
    updateAgent.mockRejectedValue(new Error("name already exists"));

    render(
      <MemoryRouter initialEntries={["/contacts/agents/agent-1"]}>
        <Routes>
          <Route path="/contacts/agents/:id" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.doubleClick(screen.getByText("Agent One"));
    fireEvent.change(screen.getByDisplayValue("Agent One"), { target: { value: "Morel" } });
    fireEvent.keyDown(screen.getByDisplayValue("Morel"), { key: "Enter" });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("重命名失败：name already exists");
    });
  });
});
