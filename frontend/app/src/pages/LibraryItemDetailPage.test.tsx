// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LibraryItemDetailPage from "./LibraryItemDetailPage";
import { useAppStore } from "@/store/app-store";

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

afterEach(() => {
  cleanup();
});

describe("LibraryItemDetailPage", () => {
  let fetchLibrary: ReturnType<typeof vi.fn<() => Promise<void>>>;
  let fetchResourceContent: ReturnType<typeof vi.fn<(type: string, id: string) => Promise<string>>>;
  let updateResource: ReturnType<typeof vi.fn<(type: string, id: string, fields: Record<string, unknown>) => Promise<void>>>;

  beforeEach(() => {
    vi.restoreAllMocks();
    navigateMock.mockReset();
    fetchLibrary = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    fetchResourceContent = vi.fn<(type: string, id: string) => Promise<string>>().mockResolvedValue("# Agent doc");
    updateResource = vi.fn<(type: string, id: string, fields: Record<string, unknown>) => Promise<void>>().mockResolvedValue(undefined);
    useAppStore.setState({
      libraryAgents: [{
        id: "agent-lib-1",
        name: "Explorer",
        desc: "inspect repos",
        type: "agent",
        created_at: 1,
        updated_at: 1,
      }],
      librarySkills: [{
        id: "skill-lib-1",
        name: "Skill One",
        desc: "skill desc",
        type: "skill",
        created_at: 1,
        updated_at: 1,
      }],
      librarySandboxTemplates: [{
        id: "daytona:default",
        name: "Daytona Default",
        desc: "Default recipe for daytona",
        type: "sandbox-template",
        provider_name: "daytona_selfhost",
        provider_type: "daytona",
        features: { lark_cli: false },
        configurable_features: { lark_cli: true },
        feature_options: [{
          key: "lark_cli",
          name: "Lark CLI",
          description: "Install lark-cli during sandbox bootstrap",
        }],
        builtin: true,
        created_at: 0,
        updated_at: 0,
      }],
      fetchLibrary,
      fetchResourceContent,
      updateResource,
    });
  });

  it("uses the canonical installed route for the back button on sandbox detail pages", async () => {
    render(
      <MemoryRouter initialEntries={["/library/sandbox-template/daytona:default"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Daytona Default" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(navigateMock).toHaveBeenCalledWith("/marketplace?tab=installed&sub=sandbox-template");
  });

  it("uses the canonical installed route for the back button on agent detail pages", async () => {
    render(
      <MemoryRouter initialEntries={["/library/agent/agent-lib-1"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Explorer" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(navigateMock).toHaveBeenCalledWith("/marketplace?tab=installed&sub=agent");
  });

  it("uses the canonical installed route for the back button on skill detail pages", async () => {
    fetchResourceContent.mockResolvedValue("# Skill doc");

    render(
      <MemoryRouter initialEntries={["/library/skill/skill-lib-1"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Skill One" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(navigateMock).toHaveBeenCalledWith("/marketplace?tab=installed&sub=skill");
  });

  it("uses bootstrapped library state instead of refetching the whole list", async () => {
    render(
      <MemoryRouter initialEntries={["/library/agent/agent-lib-1"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Explorer" })).toBeTruthy();
    await waitFor(() => {
      expect(fetchResourceContent).toHaveBeenCalledWith("agent", "agent-lib-1");
    });
    expect(fetchLibrary).not.toHaveBeenCalled();
  });

  it("renders sandbox recipe details as an editor instead of a blank raw-content page", async () => {
    render(
      <MemoryRouter initialEntries={["/library/sandbox-template/daytona:default"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Daytona Default" })).toBeTruthy();
    expect(screen.getByText("Sandbox · daytona_selfhost · 默认模板")).toBeTruthy();
    expect(screen.getByDisplayValue("Default recipe for daytona")).toBeTruthy();
    expect(screen.getByText("Lark CLI")).toBeTruthy();
    expect(fetchResourceContent).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Updated sandbox template" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(updateResource).toHaveBeenCalledWith("sandbox-template", "daytona:default", {
        name: "Daytona Default",
        desc: "Updated sandbox template",
        features: { lark_cli: false },
      });
    });
  });

  it("returns sandbox detail deletions to the sandbox installed subtab", async () => {
    const deleteResource = vi.fn<(type: string, id: string) => Promise<void>>().mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    useAppStore.setState({
      deleteResource,
      librarySandboxTemplates: [{
        id: "daytona:custom",
        name: "Daytona Custom",
        desc: "Custom recipe",
        type: "sandbox-template",
        provider_name: "daytona_selfhost",
        provider_type: "daytona",
        features: { lark_cli: false },
        feature_options: [],
        builtin: false,
        created_at: 0,
        updated_at: 0,
      }],
    });

    render(
      <MemoryRouter initialEntries={["/library/sandbox-template/daytona:custom"]}>
        <Routes>
          <Route path="/library/:type/:id" element={<LibraryItemDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Daytona Custom" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() => {
      expect(deleteResource).toHaveBeenCalledWith("sandbox-template", "daytona:custom");
      expect(navigateMock).toHaveBeenCalledWith("/marketplace?tab=installed&sub=sandbox-template");
    });
  });
});
