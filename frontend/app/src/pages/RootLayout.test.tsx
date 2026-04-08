// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import RootLayout, { LoginForm } from "./RootLayout";
import { useAuthStore } from "../store/auth-store";

vi.mock("zustand/middleware", async () => {
  const actual = await vi.importActual<typeof import("zustand/middleware")>("zustand/middleware");
  return {
    ...actual,
    persist: ((initializer: unknown) => initializer) as typeof actual.persist,
  };
});

vi.mock("@/api/client", () => ({
  uploadUserAvatar: vi.fn(),
}));

vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: { children: ReactNode }) => <>{children}</>,
  PopoverTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/CreateMemberDialog", () => ({
  default: () => null,
}));

vi.mock("@/components/NewChatDialog", () => ({
  default: () => null,
}));

vi.mock("@/components/MemberAvatar", () => ({
  default: () => null,
}));

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
});

describe("RootLayout setup-name contract", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const storage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal("localStorage", storage);
    Object.defineProperty(window, "localStorage", {
      value: storage,
      configurable: true,
    });
    useAuthStore.setState({
      token: "token-1",
      user: { id: "user-1", name: "old", type: "human", avatar: null },
      agent: null,
      setupInfo: { userId: "agent-1", defaultName: "old" },
      login: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn(),
      completeRegister: vi.fn(),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("submits setup-name updates through /api/panel/agents", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <RootLayout />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText("显示名称");
    fireEvent.change(input, { target: { value: "renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "开始使用" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/panel/agents/agent-1",
        expect.objectContaining({
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer token-1",
          },
          body: JSON.stringify({ name: "renamed" }),
        }),
      );
    });
  });
});

describe("RootLayout agent wording contract", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const storage = {
      getItem: vi.fn(() => "true"),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal("localStorage", storage);
    Object.defineProperty(window, "localStorage", {
      value: storage,
      configurable: true,
    });
    useAuthStore.setState({
      token: "token-1",
      user: { id: "user-1", name: "tester", type: "human", avatar: null },
      agent: null,
      setupInfo: null,
      login: vi.fn(),
      sendOtp: vi.fn(),
      verifyOtp: vi.fn(),
      completeRegister: vi.fn(),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("uses Agent wording in the create dropdown", async () => {
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route path="*" element={<RootLayout />}>
            <Route path="chat" element={<div>chat-page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "新建" }));

    expect(await screen.findByRole("button", { name: "新建 Agent" })).toBeTruthy();
  });
});

describe("LoginForm", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      user: null,
      agent: null,
      setupInfo: null,
      login: vi.fn(async () => {
        useAuthStore.setState({
          token: "token",
          user: { id: "u-1", name: "tester", type: "human", avatar: null },
          agent: null,
          setupInfo: null,
        });
      }),
      sendOtp: vi.fn(async () => undefined),
      verifyOtp: vi.fn(async () => ({ tempToken: "temp" })),
      completeRegister: vi.fn(async () => undefined),
      clearSetupInfo: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("redirects to /chat after a successful login", async () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route
            path="/login"
            element={
              <>
                <LoginForm />
                <div>login-page</div>
              </>
            }
          />
          <Route path="/chat" element={<div>chat-page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText("邮箱或 Mycel ID"), {
      target: { value: "otpfull_1775371370@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("密码"), {
      target: { value: "LeonFull123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("chat-page")).toBeTruthy();
    });
  });
});
