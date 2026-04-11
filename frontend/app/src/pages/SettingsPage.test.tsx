// @vitest-environment jsdom

import { render, waitFor } from "@testing-library/react";
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
vi.mock("../components/ModelPoolSection", () => ({ default: () => null }));
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
});
