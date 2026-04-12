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

  it("renders a contact profile from the entity surface without leaking agent config panels", async () => {
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
      <MemoryRouter initialEntries={["/contacts/entities/human-2"]}>
        <Routes>
          <Route path="/contacts/entities/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(authFetch).toHaveBeenCalledWith("/api/entities"));
    expect(await screen.findByRole("heading", { name: "Ada" })).toBeTruthy();
    expect(screen.getByText("human")).toBeTruthy();
    expect(screen.getByText("visit")).toBeTruthy();
    expect(screen.getByRole("button", { name: "发起对话" })).toBeTruthy();
    expect(screen.queryByText("系统提示词")).toBeNull();
    expect(screen.queryByRole("button", { name: /子 Agent/ })).toBeNull();
  });

  it("opens an agent contact default thread when the backend exposes one", async () => {
    authFetch.mockResolvedValueOnce(okJson([
      {
        user_id: "agent-2",
        name: "Toad",
        type: "agent",
        avatar_url: null,
        owner_name: "Other",
        is_owned: false,
        relationship_state: "hire",
        can_chat: true,
        default_thread_id: "thread-toad",
        is_default_thread: true,
        branch_index: 0,
      },
    ]));

    render(
      <MemoryRouter initialEntries={["/contacts/entities/agent-2"]}>
        <Routes>
          <Route path="/contacts/entities/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "打开默认线程" }));

    expect(navigate).toHaveBeenCalledWith("/chat/hire/thread/thread-toad");
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
      <MemoryRouter initialEntries={["/contacts/entities/human-2"]}>
        <Routes>
          <Route path="/contacts/entities/:userId" element={<ContactDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("联系人")).toBeTruthy();
    expect(screen.queryByText("none")).toBeNull();
  });
});
