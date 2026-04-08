// @vitest-environment jsdom

import { render, waitFor } from "@testing-library/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./SettingsPage";

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
  window.history.replaceState({}, "", "/");
});

describe("SettingsPage", () => {
  it("does not log a failed settings load once navigation already left /settings", async () => {
    window.history.replaceState({}, "", "/settings");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
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
      expect(fetchMock).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
