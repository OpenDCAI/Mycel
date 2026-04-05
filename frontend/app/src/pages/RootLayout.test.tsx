// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LoginForm } from "./RootLayout";
import { useAuthStore } from "../store/auth-store";

describe("LoginForm", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      user: null,
      agent: null,
      entityId: null,
      setupInfo: null,
      login: vi.fn(async () => {
        useAuthStore.setState({
          token: "token",
          user: { id: "u-1", name: "tester", type: "human", avatar: null },
          agent: null,
          entityId: null,
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

  it("redirects to /threads after a successful login", async () => {
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
          <Route path="/threads" element={<div>threads-page</div>} />
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
      expect(screen.getByText("threads-page")).toBeTruthy();
    });
  });
});
