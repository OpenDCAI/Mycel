// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ConversationList from "./ConversationList";

vi.mock("@/store/conversation-store", () => ({
  useConversationStore: () => ({
    conversations: [],
    loading: false,
    fetchConversations: vi.fn(),
  }),
}));

vi.mock("@/components/NewChatDialog", () => ({
  default: () => null,
}));

describe("ConversationList accessibility", () => {
  it("labels the new conversation button", () => {
    render(
      <MemoryRouter>
        <ConversationList threads={[]} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "新建对话" })).toBeTruthy();
  });
});
