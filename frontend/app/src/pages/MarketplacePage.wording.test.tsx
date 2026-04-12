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

const appStoreFetchLibrary = vi.fn();
const appStoreDeleteResource = vi.fn();

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      agentList: [],
      librarySkills: [],
      libraryAgents: [],
      libraryRecipes: [
        {
          id: "daytona:selfhost:default",
          name: "Self-host Daytona",
          desc: "Use the self-host Daytona provider",
          type: "recipe",
          provider_type: "daytona",
          provider_name: "daytona_selfhost",
        },
      ],
      fetchLibrary: appStoreFetchLibrary,
      deleteResource: appStoreDeleteResource,
    }),
}));

afterEach(() => {
  cleanup();
});

describe("MarketplacePage wording contract", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    appStoreFetchLibrary.mockReset();
    appStoreDeleteResource.mockReset();
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
    expect(screen.queryByRole("button", { name: "Member" })).toBeNull();
  });

  it("uses Subagent wording for marketplace agent resources", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=agent"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /Subagent/ })).toBeTruthy();
    expect(screen.getByText("暂无已安装的 Subagent")).toBeTruthy();
  });

  it("does not bootstrap installed libraries because RootLayout owns panel loading", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=agent"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(appStoreFetchLibrary).not.toHaveBeenCalled();
  });

  it("shows installed sandbox recipes as the sandbox library tab", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=recipe"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /Sandbox/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Recipe/ })).toBeNull();
    expect(screen.getByText("Self-host Daytona")).toBeTruthy();
    expect(screen.getByText("Sandbox recipe · daytona")).toBeTruthy();
  });

  it("uses Agent wording for marketplace member resources", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "Agent" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Member" })).toBeNull();
  });

  it("falls back to explore for invalid tab params", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=unknown&sub=ghost"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Explore" })).toBeTruthy();
  });
});
