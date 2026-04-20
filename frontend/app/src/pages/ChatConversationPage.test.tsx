// @vitest-environment jsdom

import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatConversationPage from "./ChatConversationPage";
import { useAuthStore } from "../store/auth-store";

const authFetchMocks = vi.hoisted(() => ({
  authFetch: vi.fn(),
  streamChatEvents: vi.fn(),
  useOutletContext: vi.fn(),
}));

vi.mock("zustand/middleware", async () => {
  const actual = await vi.importActual<typeof import("zustand/middleware")>("zustand/middleware");
  return {
    ...actual,
    persist: ((initializer: unknown) => initializer) as typeof actual.persist,
  };
});

vi.mock("../store/auth-store", async () => {
  const actual = await vi.importActual<typeof import("../store/auth-store")>("../store/auth-store");
  return {
    ...actual,
    authFetch: authFetchMocks.authFetch,
  };
});

vi.mock("../api/chat-events", () => ({
  streamChatEvents: authFetchMocks.streamChatEvents,
  parseChatMessageEventData: vi.fn(),
  parseChatTypingUserId: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useOutletContext: authFetchMocks.useOutletContext,
  };
});

vi.mock("../components/chat-area/UserBubble", () => ({
  UserBubble: () => null,
}));

vi.mock("../components/chat-area/ChatBubble", () => ({
  ChatBubble: () => null,
}));

describe("ChatConversationPage SSE teardown", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    authFetchMocks.authFetch.mockReset();
    authFetchMocks.streamChatEvents.mockReset();
    authFetchMocks.useOutletContext.mockReset();
    authFetchMocks.useOutletContext.mockReturnValue({
      setSidebarCollapsed: vi.fn(),
      refreshChatList: vi.fn(),
    });

    useAuthStore.setState({
      hydrated: true,
      token: "token-1",
      user: { id: "user-1", name: "tester", type: "human", avatar: null },
      agent: null,
      userId: "user-1",
      setupInfo: null,
      markHydrated: vi.fn(),
      login: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn(),
      completeRegister: vi.fn(),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });

    authFetchMocks.authFetch.mockImplementation(async (url: string) => {
      if (url === "/api/chats/chat-1") {
        return {
          ok: true,
          json: async () => ({
            id: "chat-1",
            title: "chat title",
            members: [{ id: "user-1", name: "tester", type: "human" }],
          }),
        };
      }
      if (url === "/api/chats/chat-1/messages?limit=100") {
        return {
          ok: true,
          json: async () => [],
        };
      }
      if (url === "/api/chats/chat-1/read") {
        return {
          ok: true,
          json: async () => ({}),
        };
      }
      throw new Error(`Unexpected authFetch url: ${url}`);
    });
  });

  it("suppresses unload-time SSE network errors after pagehide aborts the stream", async () => {
    let rejectStream: ((reason?: unknown) => void) | null = null;
    let seenSignal: AbortSignal | undefined;
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    authFetchMocks.streamChatEvents.mockImplementation(
      async (_chatId: string, _onEvent: unknown, signal?: AbortSignal) =>
        new Promise<void>((_, reject) => {
          seenSignal = signal;
          rejectStream = reject;
        }),
    );

    render(
      <MemoryRouter initialEntries={["/chat/visit/chat-1"]}>
        <Routes>
          <Route path="/chat/visit/:chatId" element={<ChatConversationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(authFetchMocks.streamChatEvents).toHaveBeenCalled();
    });

    window.dispatchEvent(new Event("pagehide"));
    expect(seenSignal?.aborted).toBe(true);

    if (!rejectStream) {
      throw new Error("expected stream reject handler to be captured");
    }
    const reject = rejectStream as (reason?: unknown) => void;
    reject(new TypeError("network error"));
    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
