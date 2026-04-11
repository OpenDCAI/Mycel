// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./SettingsPage";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("../store/auth-store", () => ({
  authFetch,
}));

vi.mock("../hooks/use-mobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("../components/ModelMappingSection", () => ({ default: () => null }));
vi.mock("../components/ModelPoolSection", () => ({
  default: ({
    onAddCustomModel,
    onRemoveCustomModel,
  }: {
    onAddCustomModel: (modelId: string, provider: string) => Promise<void>;
    onRemoveCustomModel: (modelId: string) => Promise<void>;
  }) => (
    <div>
      <button onClick={() => void onAddCustomModel("custom:model", "openai")}>add-custom-model</button>
      <button onClick={() => void onRemoveCustomModel("custom:model")}>remove-custom-model</button>
    </div>
  ),
}));
vi.mock("../components/ObservationSection", () => ({ default: () => null }));
vi.mock("../components/ProvidersSection", () => ({ default: () => null }));
vi.mock("../components/SandboxSection", () => ({ default: () => null }));
vi.mock("../components/WorkspaceSection", () => ({ default: () => null }));

vi.mock("@/api/client", () => ({
  fetchInviteCodes: vi.fn(),
  generateInviteCode: vi.fn(),
  revokeInviteCode: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function settingsResponse() {
  return {
    model_mapping: {},
    enabled_models: [],
    custom_config: {},
    providers: {},
    default_workspace: null,
    default_model: "leon:medium",
  };
}

function mockSettingsRuntime(
  handleMutation: (url: string) => { ok: boolean; json: () => Promise<unknown> } | undefined,
) {
  const counters = {
    availableModelsFetches: 0,
    settingsFetches: 0,
  };
  authFetch.mockImplementation(async (url: string) => {
    if (url === "/api/settings/available-models") {
      counters.availableModelsFetches += 1;
      return { ok: true, json: async () => ({ models: [], virtual_models: [] }) };
    }
    if (url === "/api/settings") {
      counters.settingsFetches += 1;
      return { ok: true, json: async () => settingsResponse() };
    }
    if (url === "/api/settings/sandboxes") return { ok: true, json: async () => ({ sandboxes: {} }) };
    if (url === "/api/settings/observation") return { ok: true, json: async () => ({}) };
    const mutation = handleMutation(url);
    if (mutation) return mutation;
    throw new Error(`unexpected url: ${url}`);
  });
  return counters;
}

afterEach(() => {
  vi.restoreAllMocks();
  authFetch.mockReset();
  window.history.replaceState({}, "", "/");
});

describe("SettingsPage", () => {
  it("loads settings bootstrap through authenticated fetch", async () => {
    window.history.replaceState({}, "", "/settings");
    authFetch.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/settings/available-models");
      expect(authFetch).toHaveBeenCalledWith("/api/settings");
      expect(authFetch).toHaveBeenCalledWith("/api/settings/sandboxes");
      expect(authFetch).toHaveBeenCalledWith("/api/settings/observation");
    });
  });

  it("does not log a failed settings load once navigation already left /settings", async () => {
    window.history.replaceState({}, "", "/settings");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    authFetch.mockImplementation(async () => {
      window.history.pushState({}, "", "/chat");
      window.dispatchEvent(new PopStateEvent("popstate"));
      throw new TypeError("Failed to fetch");
    });

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/chat" element={<div>chat-page</div>} />
        </Routes>
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });

  it("does not treat non-boolean custom model add success as successful", async () => {
    window.history.replaceState({}, "", "/settings");
    let customModelAdds = 0;
    const counters = mockSettingsRuntime((url) => {
      if (url === "/api/settings/models/custom") {
        customModelAdds += 1;
        return { ok: true, json: async () => ({ success: "yes" }) };
      }
      return undefined;
    });

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "add-custom-model" }));

    await waitFor(() => {
      expect(customModelAdds).toBe(1);
    });
    await Promise.resolve();
    expect(counters.availableModelsFetches).toBe(1);
    expect(counters.settingsFetches).toBe(1);
  });

  it("does not treat non-boolean custom model remove success as successful", async () => {
    window.history.replaceState({}, "", "/settings");
    let customModelRemoves = 0;
    const counters = mockSettingsRuntime((url) => {
      if (url.startsWith("/api/settings/models/custom?")) {
        customModelRemoves += 1;
        return { ok: true, json: async () => ({ success: "yes" }) };
      }
      return undefined;
    });

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "remove-custom-model" }));

    await waitFor(() => {
      expect(customModelRemoves).toBe(1);
    });
    await Promise.resolve();
    expect(counters.availableModelsFetches).toBe(1);
    expect(counters.settingsFetches).toBe(1);
  });
});
