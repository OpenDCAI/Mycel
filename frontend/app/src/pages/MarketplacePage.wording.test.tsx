// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MarketplacePage from "./MarketplacePage";

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname + location.search}</output>;
}

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
const appStoreAddResource = vi.fn();
let appStoreState: Record<string, unknown>;

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector(appStoreState),
}));

afterEach(() => {
  cleanup();
});

describe("MarketplacePage wording contract", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    appStoreFetchLibrary.mockReset();
    appStoreDeleteResource.mockReset();
    appStoreAddResource.mockReset();
    appStoreAddResource.mockResolvedValue({
      id: "daytona_selfhost:custom:probe",
      name: "Selfhost Custom",
      desc: "custom self-host sandbox",
      type: "recipe",
      provider_name: "daytona_selfhost",
      provider_type: "daytona",
      features: { lark_cli: false },
      created_at: 1,
      updated_at: 1,
    });
    appStoreState = {
      agentList: [],
      agentsLoaded: true,
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
          features: { lark_cli: false },
          feature_options: [{
            key: "lark_cli",
            name: "Lark CLI",
            description: "Install lark-cli during sandbox bootstrap",
          }],
        },
      ],
      librariesLoaded: { skill: true, mcp: true, agent: true, recipe: true },
      fetchLibrary: appStoreFetchLibrary,
      deleteResource: appStoreDeleteResource,
      addResource: appStoreAddResource,
    };
  });

  it("uses Agent wording for the installed local agent tab", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=agent-user"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("button", { name: /Agent/ }).length).toBeGreaterThan(0);
    expect(screen.getByText("暂无已安装的 Agent")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Member" })).toBeNull();
  });

  it("uses agent-user as the installed Agent tab URL key", () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed"]}>
        <Routes>
          <Route path="/marketplace" element={<><MarketplacePage /><LocationProbe /></>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getAllByRole("button", { name: /Agent/ })[0]);

    expect(screen.getByLabelText("location").textContent).toContain("sub=agent-user");
    expect(screen.getByLabelText("location").textContent).not.toContain("sub=member");
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

    expect(screen.getAllByRole("button", { name: /Sandbox/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Recipe/ })).toBeNull();
    expect(screen.getByText("Self-host Daytona")).toBeTruthy();
    expect(screen.getByText("Sandbox · daytona_selfhost")).toBeTruthy();
  });

  it("does not show installed sandbox empty state before recipe library is loaded", () => {
    appStoreState = {
      ...appStoreState,
      libraryRecipes: [],
      librariesLoaded: { skill: true, mcp: true, agent: true, recipe: false },
    };

    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=recipe"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("暂无已安装的 Sandbox")).toBeNull();
    expect(screen.getByText("正在加载已安装内容...")).toBeTruthy();
  });

  it("creates sandbox recipes with concrete provider_name from backend-loaded recipes", async () => {
    render(
      <MemoryRouter initialEntries={["/marketplace?tab=installed&sub=recipe"]}>
        <Routes>
          <Route path="/marketplace" element={<MarketplacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "新建 Sandbox" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Selfhost Custom" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "custom self-host sandbox" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() => {
      expect(appStoreAddResource).toHaveBeenCalledWith("recipe", "Selfhost Custom", "custom self-host sandbox", {
        provider_name: "daytona_selfhost",
        features: { lark_cli: false },
      });
    });
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
