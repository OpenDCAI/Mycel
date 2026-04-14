// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LibraryItemDetailPage from "./LibraryItemDetailPage";
import { useAppStore } from "@/store/app-store";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
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
      librarySkills: [],
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
});
