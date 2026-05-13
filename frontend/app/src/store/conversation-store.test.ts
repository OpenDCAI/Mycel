// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("./auth-store", () => ({
  authFetch,
}));

afterEach(async () => {
  vi.resetModules();
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
  const { useConversationStore } = await import("./conversation-store");
  useConversationStore.setState({ conversations: [], loading: false });
});

describe("useConversationStore", () => {
  it("does not log a failed fetch once navigation already left the chat route", async () => {
    window.history.replaceState({}, "", "/chat");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    authFetch.mockImplementation(async () => {
      window.history.replaceState({}, "", "/settings");
      throw new TypeError("Failed to fetch");
    });

    const { useConversationStore } = await import("./conversation-store");

    await useConversationStore.getState().fetchConversations();

    expect(authFetch).toHaveBeenCalledWith("/api/conversations");
    expect(consoleError).not.toHaveBeenCalled();
  });
});
