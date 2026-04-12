// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContactList from "./ContactList";
import { useAppStore } from "@/store/app-store";

const { authFetch, authState } = vi.hoisted(() => ({
  authFetch: vi.fn(),
  authState: { userId: "human-1", token: "token-1" },
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
  useAuthStore: Object.assign(
    (selector: (state: typeof authState) => unknown) => selector(authState),
    { getState: () => authState },
  ),
}));

vi.mock("@/components/ActorAvatar", () => ({
  default: ({ name }: { name: string }) => <span>{name.slice(0, 2)}</span>,
}));

vi.mock("@/components/CreateAgentDialog", () => ({
  default: () => null,
}));

function okJson(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("ContactList", () => {
  let ensureAgents: ReturnType<typeof vi.fn<() => Promise<void>>>;

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    authFetch.mockReset();
    ensureAgents = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    useAppStore.setState({
      agentList: [
        {
          id: "agent-1",
          name: "Morel",
          description: "owned agent",
          status: "active",
          version: "1.0.0",
          config: { prompt: "", rules: [], tools: [], mcps: [], skills: [], subAgents: [] },
          created_at: 0,
          updated_at: 0,
          avatar_url: "/api/users/agent-1/avatar",
        },
      ],
      ensureAgents,
    });
  });

  it("does not bootstrap owned agents because RootLayout owns panel loading", () => {
    render(
      <MemoryRouter>
        <ContactList />
      </MemoryRouter>,
    );

    expect(ensureAgents).not.toHaveBeenCalled();
    expect(screen.getByText("Morel")).toBeTruthy();
  });

  it("shows backend-approved external contacts from the entity surface", async () => {
    authFetch.mockResolvedValueOnce(okJson([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
      },
      {
        user_id: "human-4",
        name: "Grace",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "none",
        can_chat: true,
      },
      {
        user_id: "agent-1",
        name: "Morel",
        type: "agent",
        avatar_url: "/api/users/agent-1/avatar",
        owner_name: "Me",
        is_owned: true,
        relationship_state: "none",
        can_chat: true,
      },
      {
        user_id: "human-3",
        name: "Pending",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "pending",
        can_chat: false,
      },
    ]));

    render(
      <MemoryRouter initialEntries={["/contacts"]}>
        <Routes>
          <Route path="/contacts" element={<ContactList />} />
          <Route path="/contacts/entities" element={<ContactList />} />
          <Route path="/contacts/entities/:userId" element={<div>contact detail route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "创建 Agent" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /联系人/ }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/entities");
    });
    expect(await screen.findByText("Ada")).toBeTruthy();
    expect(screen.getByText("Grace")).toBeTruthy();
    expect(screen.queryByText("none")).toBeNull();
    expect(screen.queryByText("联系人功能即将上线")).toBeNull();
    expect(screen.queryByText("Morel")).toBeNull();
    expect(screen.queryByText("Pending")).toBeNull();

    fireEvent.click(screen.getByRole("link", { name: /Ada/ }));

    expect(await screen.findByText("contact detail route")).toBeTruthy();
  });
});
