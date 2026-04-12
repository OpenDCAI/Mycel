// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewChatDialog from "./NewChatDialog";
import { useAppStore } from "@/store/app-store";

const { authFetch, navigate, authState } = vi.hoisted(() => ({
  authFetch: vi.fn(),
  navigate: vi.fn(),
  authState: { userId: "human-1", token: "token-1" },
}));

vi.mock("../store/auth-store", () => ({
  authFetch,
  useAuthStore: Object.assign(
    (selector: (state: typeof authState) => unknown) => selector(authState),
    { getState: () => authState },
  ),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("./ActorAvatar", () => ({
  default: ({ name }: { name: string }) => <span>{name.slice(0, 2)}</span>,
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

function renderDialog() {
  const onOpenChange = vi.fn();
  render(
    <MemoryRouter>
      <NewChatDialog open onOpenChange={onOpenChange} />
    </MemoryRouter>,
  );
  return { onOpenChange };
}

describe("NewChatDialog", () => {
  beforeEach(() => {
    authFetch.mockReset();
    navigate.mockReset();
    useAppStore.setState({
      agentList: [
        {
          id: "agent-1",
          name: "Morel",
          description: "thoughtful analyst",
          status: "active",
          version: "1.0.0",
          config: { prompt: "", rules: [], tools: [], mcps: [], skills: [], subAgents: [] },
          created_at: 0,
          updated_at: 0,
          avatar_url: "/api/users/agent-1/avatar",
        },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens an agent default thread from the thread mode", () => {
    const { onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: /Morel/ }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith("/chat/hire/agent-1");
    expect(authFetch).not.toHaveBeenCalled();
  });

  it("creates a group chat from selected social users", async () => {
    authFetch
      .mockResolvedValueOnce(okJson([
        {
          user_id: "human-2",
          name: "Ada",
          type: "human",
          avatar_url: null,
          owner_name: null,
          agent_name: "Ada",
          is_owned: false,
          relationship_state: "visit",
          can_chat: true,
        },
        {
          user_id: "agent-2",
          name: "Toad",
          type: "agent",
          avatar_url: "/api/users/agent-2/avatar",
          owner_name: "Owner",
          agent_name: "Toad",
          default_thread_id: "thread-toad",
          is_owned: false,
          relationship_state: "hire",
          can_chat: true,
        },
        {
          user_id: "human-3",
          name: "Pending User",
          type: "human",
          avatar_url: null,
          owner_name: null,
          agent_name: "Pending User",
          is_owned: false,
          relationship_state: "pending",
          can_chat: false,
        },
      ]))
      .mockResolvedValueOnce(okJson({ id: "chat-1", title: "Ada, Toad", status: "active", created_at: 1 }));
    const { onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "创建群聊" }));
    expect(authFetch).toHaveBeenCalledWith("/api/users/chat-candidates");

    expect(await screen.findByRole("button", { name: /Ada/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Pending User/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Ada/ }));
    fireEvent.click(screen.getByRole("button", { name: /Toad/ }));
    fireEvent.change(screen.getByPlaceholderText("群聊名称（可选）"), { target: { value: "Trial group" } });
    fireEvent.click(screen.getByRole("button", { name: "创建群聊（2）" }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenLastCalledWith(
        "/api/chats",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ user_ids: ["human-1", "human-2", "agent-2"], title: "Trial group" }),
        }),
      );
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith("/chat/visit/chat-1");
  });

  it("uses user candidates as the group-chat participant source of truth", async () => {
    useAppStore.setState({
      agentList: [
        {
          id: "agent-config-1",
          name: "Morel",
          description: "configuration identity",
          status: "active",
          version: "1.0.0",
          config: { prompt: "", rules: [], tools: [], mcps: [], skills: [], subAgents: [] },
          created_at: 0,
          updated_at: 0,
        },
      ],
    });
    authFetch
      .mockResolvedValueOnce(okJson([
        {
          user_id: "actor-agent-1",
          name: "Morel",
          type: "agent",
          avatar_url: null,
          owner_name: "我的 Agent",
          agent_name: "Morel",
          default_thread_id: "thread-morel",
          is_owned: true,
          relationship_state: "none",
          can_chat: true,
        },
        {
          user_id: "human-2",
          name: "Ada",
          type: "human",
          avatar_url: null,
          owner_name: null,
          agent_name: "Ada",
          is_owned: false,
          relationship_state: "visit",
          can_chat: true,
        },
      ]))
      .mockResolvedValueOnce(okJson({ id: "chat-user-candidates-source", status: "active", created_at: 1 }));

    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "创建群聊" }));

    expect(await screen.findByRole("button", { name: /Morel/ })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Morel/ })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /Morel/ }));
    fireEvent.click(screen.getByRole("button", { name: /Ada/ }));
    fireEvent.click(screen.getByRole("button", { name: "创建群聊（2）" }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenLastCalledWith(
        "/api/chats",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ user_ids: ["human-1", "actor-agent-1", "human-2"] }),
        }),
      );
    });
  });
});
