// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MarketplaceDetailPage from "./MarketplaceDetailPage";

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("@/components/marketplace/LineageTree", () => ({
  default: () => null,
}));

vi.mock("@/components/marketplace/InstallDialog", () => ({
  default: () => null,
}));

const marketplaceState = {
  detail: {
    id: "item-1",
    slug: "item-one",
    type: "skill",
    name: "Skill One",
    description: "skill description",
    avatar_url: null,
    publisher_user_id: "publisher-1",
    publisher_username: "owner",
    parent_id: null,
    download_count: 0,
    visibility: "public",
    featured: false,
    tags: [],
    created_at: "2026-04-01T00:00:00Z",
    updated_at: "2026-04-01T00:00:00Z",
    versions: [],
    parent: null,
  },
  detailLoading: false,
  fetchDetail: vi.fn(),
  lineage: { ancestors: [], children: [] },
  fetchLineage: vi.fn(),
  clearDetail: vi.fn(),
  error: null,
  versionSnapshot: null,
  snapshotLoading: false,
  fetchVersionSnapshot: vi.fn(),
  clearSnapshot: vi.fn(),
};

vi.mock("@/store/marketplace-store", () => ({
  useMarketplaceStore: (selector: (state: typeof marketplaceState) => unknown) => selector(marketplaceState),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MarketplaceDetailPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("uses the marketplace explore route as the back target for direct-open detail", async () => {
    render(
      <MemoryRouter initialEntries={["/marketplace/item-1"]}>
        <Routes>
          <Route path="/marketplace/:id" element={<MarketplaceDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Skill One" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(navigateMock).toHaveBeenCalledWith("/marketplace?tab=explore");
  });
});
