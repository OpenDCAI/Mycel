// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContactDetailPage from "./ContactDetailPage";

const { authFetch, navigate } = vi.hoisted(() => ({
  authFetch: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
  useAuthStore: (selector: (state: { userId: string }) => unknown) => selector({ userId: "human-1" }),
}));

vi.mock("@/components/ActorAvatar", () => ({
  default: ({ name }: { name: string }) => <span>{name.slice(0, 2)}</span>,
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

function okJson(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("ContactDetailPage", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    authFetch.mockReset();
    navigate.mockReset();
  });

  it("uses the contacts tab as the back target for direct-open contact detail", async () => {
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
    ]));

    render(
      <MemoryRouter initialEntries={["/contacts/users/human-2"]}>
        <Routes>
          <Route path="/contacts/users/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Ada" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button")[0]);

    expect(navigate).toHaveBeenCalledWith("/contacts/users");
  });

  it("renders a contact profile from the user candidate surface without leaking agent config panels", async () => {
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
    ]));

    render(
      <MemoryRouter initialEntries={["/contacts/users/human-2"]}>
        <Routes>
          <Route path="/contacts/users/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(authFetch).toHaveBeenCalledWith("/api/users/chat-candidates"));
    expect(await screen.findByRole("heading", { name: "Ada" })).toBeTruthy();
    expect(screen.getByText("human")).toBeTruthy();
    expect(screen.getByText("visit")).toBeTruthy();
    expect(screen.getByRole("button", { name: "发起对话" })).toBeTruthy();
    expect(screen.queryByText("系统提示词")).toBeNull();
    expect(screen.queryByRole("button", { name: /子 Agent/ })).toBeNull();
  });

  it("opens an agent contact through the chat surface instead of the private default thread", async () => {
    authFetch
      .mockResolvedValueOnce(okJson([
        {
          user_id: "agent-2",
          name: "Toad",
          type: "agent",
          avatar_url: null,
          owner_name: "Other",
          is_owned: false,
          relationship_state: "hire",
          can_chat: true,
        },
      ]))
      .mockResolvedValueOnce(okJson({ id: "chat-agent-2" }));

    render(
      <MemoryRouter initialEntries={["/contacts/users/agent-2"]}>
        <Routes>
          <Route path="/contacts/users/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "发起对话" }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/chats", {
        method: "POST",
        body: JSON.stringify({ user_ids: ["human-1", "agent-2"] }),
      });
    });
    expect(navigate).toHaveBeenCalledWith("/chat/visit/chat-agent-2");
    expect(screen.queryByText("默认线程")).toBeNull();
    expect(screen.queryByText("分支")).toBeNull();
  });

  it("shows chat-capable contacts as contacts instead of exposing raw none state", async () => {
    authFetch.mockResolvedValueOnce(okJson([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "none",
        can_chat: true,
      },
    ]));

    render(
      <MemoryRouter initialEntries={["/contacts/users/human-2"]}>
        <Routes>
          <Route path="/contacts/users/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("联系人")).toBeTruthy();
    expect(screen.queryByText("none")).toBeNull();
  });
});
