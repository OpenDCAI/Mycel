// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDetailPage from "./AgentDetailPage";

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      getAgentById: () => ({
        id: "agent-1",
        name: "Agent One",
        description: "desc",
        status: "active",
        version: "1.0.0",
        config: {
          prompt: "",
          tools: [],
          rules: [],
          skills: [],
          mcps: [],
          subAgents: [],
        },
      }),
      updateAgent: vi.fn(),
      updateAgentConfig: vi.fn(),
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
});

describe("AgentDetailPage wording contract", () => {
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
});
