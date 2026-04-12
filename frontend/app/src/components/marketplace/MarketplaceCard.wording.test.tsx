// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import MarketplaceCard from "./MarketplaceCard";

afterEach(() => cleanup());

describe("MarketplaceCard wording contract", () => {
  it("renders the Hub agent-user item type as Agent", () => {
    render(
      <MarketplaceCard
        item={{
          id: "item-1",
          slug: "agent-pack",
          type: "member",
          name: "Agent Pack",
          description: "An agent user package",
          avatar_url: null,
          publisher_user_id: "user-1",
          publisher_username: "tester",
          parent_id: null,
          download_count: 0,
          visibility: "public",
          featured: false,
          tags: [],
          created_at: "2026-04-13T00:00:00Z",
          updated_at: "2026-04-13T00:00:00Z",
        }}
      />,
    );

    expect(screen.getByText("Agent")).toBeTruthy();
    expect(screen.queryByText("member")).toBeNull();
  });
});
