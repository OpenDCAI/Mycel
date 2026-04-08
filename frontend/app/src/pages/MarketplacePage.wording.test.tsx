// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MarketplacePage from "./MarketplacePage";

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("@/components/marketplace/MarketplaceCard", () => ({
  default: () => null,
}));

vi.mock("@/components/marketplace/UpdateDialog", () => ({
  default: () => null,
}));

vi.mock("@/store/marketplace-store", () => ({
  useMarketplaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      items: [],
      total: 0,
      loading: false,
      error: null,
      updates: [],
      filters: { type: null, sort: "downloads" },
      setFilter: vi.fn(),
      fetchItems: vi.fn(),
      checkUpdates: vi.fn(),
    }),
}));

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      agentList: [],
      librarySkills: [],
      libraryAgents: [],
      fetchLibrary: vi.fn(),
      deleteResource: vi.fn(),
    }),
}));

afterEach(() => {
  cleanup();
});

describe("MarketplacePage wording contract", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("uses Agent wording for the installed local agent tab", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=member"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("button", { name: /Agent/ }).length).toBeGreaterThan(0);
    expect(screen.getByText("暂无已安装的 Agent")).toBeTruthy();
  });
});
