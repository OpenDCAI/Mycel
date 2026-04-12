// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchInviteCodes } from "@/api/client";
import SettingsPage from "./SettingsPage";
import { toast } from "sonner";

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
      <button onClick={() => void onAddCustomModel("custom:model", "openai").catch(() => undefined)}>add-custom-model</button>
      <button onClick={() => void onRemoveCustomModel("custom:model").catch(() => undefined)}>remove-custom-model</button>
    </div>
  ),
}));
vi.mock("../components/ProvidersSection", () => ({ default: () => null }));

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
  handleMutation: (url: string) => {
    ok: boolean;
    status?: number;
    text?: () => Promise<string>;
    json: () => Promise<unknown>;
  } | undefined,
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
    const mutation = handleMutation(url);
    if (mutation) return mutation;
    throw new Error(`unexpected url: ${url}`);
  });
  return counters;
}

afterEach(() => {
  cleanup();
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
      expect(authFetch).not.toHaveBeenCalledWith("/api/settings/sandboxes");
      expect(authFetch).not.toHaveBeenCalledWith("/api/settings/observation");
      expect(screen.queryByRole("button", { name: /追踪/ })).toBeNull();
      expect(screen.queryByRole("button", { name: /沙箱/ })).toBeNull();
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

  it("does not refresh custom models when add persistence fails", async () => {
    window.history.replaceState({}, "", "/settings");
    let customModelAdds = 0;
    const counters = mockSettingsRuntime((url) => {
      if (url === "/api/settings/models/custom") {
        customModelAdds += 1;
        return {
          ok: false,
          status: 503,
          text: async () => "unavailable",
          json: async () => ({ success: true }),
        };
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
      expect(toast.error).toHaveBeenCalledWith("自定义模型保存失败：API 503: unavailable");
    });
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

  it("does not refresh custom models when remove persistence fails", async () => {
    window.history.replaceState({}, "", "/settings");
    let customModelRemoves = 0;
    const counters = mockSettingsRuntime((url) => {
      if (url.startsWith("/api/settings/models/custom?")) {
        customModelRemoves += 1;
        return {
          ok: false,
          status: 503,
          text: async () => "unavailable",
          json: async () => ({ success: true }),
        };
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
      expect(toast.error).toHaveBeenCalledWith("自定义模型移除失败：API 503: unavailable");
    });
    expect(counters.availableModelsFetches).toBe(1);
    expect(counters.settingsFetches).toBe(1);
  });

  it("loads account resource limits from the backend resource contract", async () => {
    window.history.replaceState({}, "", "/settings");
    let accountResourceFetches = 0;
    mockSettingsRuntime((url) => {
      if (url === "/api/settings/account-resources") {
        accountResourceFetches += 1;
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                resource: "sandbox",
                provider_name: "local",
                label: "Local",
                limit: 999,
                used: 1,
                remaining: 998,
                can_create: true,
              },
              {
                resource: "sandbox",
                provider_name: "daytona_selfhost",
                label: "Self-host Daytona",
                limit: 2,
                used: 2,
                remaining: 0,
                can_create: false,
              },
              {
                resource: "token",
                provider_name: "platform_tokens",
                label: "平台 Token",
                limit: 100_000_000,
                used: 0,
                remaining: 100_000_000,
                can_create: true,
                period: "weekly",
                unit: "tokens",
              },
            ],
          }),
        };
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

    fireEvent.click(await screen.findByRole("button", { name: /账号资源/ }));

    expect(await screen.findByText("Self-host Daytona")).toBeTruthy();
    expect(screen.getByText("平台 Token")).toBeTruthy();
    expect(screen.getByText("每周")).toBeTruthy();
    expect(screen.getByText("100,000,000")).toBeTruthy();
    expect(screen.getByText("999")).toBeTruthy();
    expect(screen.getByText("已达上限")).toBeTruthy();
    expect(accountResourceFetches).toBe(1);
  });

  it("shows a user-facing settings bootstrap error instead of raw API wording", async () => {
    window.history.replaceState({}, "", "/settings");
    authFetch.mockImplementation(async (url: string) => {
      if (url === "/api/settings/available-models") {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      if (url === "/api/settings") {
        return { ok: true, status: 200, json: async () => settingsResponse() };
      }
      throw new Error(`unexpected url: ${url}`);
    });

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>,
    );

    expect(await screen.findByText("设置暂时无法加载，请稍后重试。")).toBeTruthy();
    expect(screen.queryByText(/API 请求失败/)).toBeNull();
  });

  it("shows a user-facing invite load error instead of malformed payload wording", async () => {
    window.history.replaceState({}, "", "/settings");
    mockSettingsRuntime(() => undefined);
    vi.mocked(fetchInviteCodes).mockRejectedValue(new Error("Malformed invite codes"));

    render(
      <BrowserRouter>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /邀请码/ }));

    expect(await screen.findByText("邀请码暂时无法加载，请稍后重试。")).toBeTruthy();
    expect(screen.getAllByText("邀请码暂时无法加载，请稍后重试。")).toHaveLength(1);
    expect(screen.queryByText(/Malformed invite codes/)).toBeNull();
  });

  it("does not show a new default model as selected when saving fails", async () => {
    window.history.replaceState({}, "", "/settings");
    let defaultModelSaves = 0;
    mockSettingsRuntime((url) => {
      if (url === "/api/settings/default-model") {
        defaultModelSaves += 1;
        return {
          ok: false,
          status: 503,
          text: async () => "unavailable",
          json: async () => ({}),
        };
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

    const miniButton = await screen.findByRole("button", { name: "Mini" });
    fireEvent.click(miniButton);

    await waitFor(() => {
      expect(defaultModelSaves).toBe(1);
      expect(toast.error).toHaveBeenCalledWith("默认模型保存失败：API 503: unavailable");
    });
    expect(miniButton.className).not.toContain("bg-primary/10");
  });
});
