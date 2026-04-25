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

vi.mock("@/components/marketplace/MarketplaceActionDialog", () => ({
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
    marketplaceState.detail = {
      ...marketplaceState.detail,
      type: "skill",
      name: "Skill One",
    };
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

  it("uses add wording for Hub agent-user detail actions", async () => {
    marketplaceState.detail = {
      ...marketplaceState.detail,
      type: "member",
      name: "Agent Pack",
    };

    render(
      <MemoryRouter initialEntries={["/marketplace/item-1"]}>
        <Routes>
          <Route path="/marketplace/:id" element={<MarketplaceDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Agent Pack" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "添加 Agent" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "下载" })).toBeNull();
    expect(document.body.textContent).toContain("0 次添加");
    expect(document.body.textContent).not.toContain("downloads");
  });

  it("uses save wording for Skill detail actions", async () => {
    render(
      <MemoryRouter initialEntries={["/marketplace/item-1"]}>
        <Routes>
          <Route path="/marketplace/:id" element={<MarketplaceDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Skill One" })).toBeTruthy();
    const saveButton = screen.getByRole("button", { name: "保存到 Library" });
    expect(saveButton).toBeTruthy();
    expect(saveButton.querySelector(".lucide-package-plus")).toBeTruthy();
    expect(saveButton.querySelector(".lucide-download")).toBeNull();
    expect(screen.queryByRole("button", { name: "下载" })).toBeNull();
  });

  it("does not offer apply for unsupported Marketplace item types", async () => {
    marketplaceState.detail = {
      ...marketplaceState.detail,
      type: "env",
      name: "Env One",
    };

    render(
      <MemoryRouter initialEntries={["/marketplace/item-1"]}>
        <Routes>
          <Route path="/marketplace/:id" element={<MarketplaceDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Env One" })).toBeTruthy();
    const button = screen.getByRole("button", { name: "暂不支持保存" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "保存到 Library" })).toBeNull();
  });
});
