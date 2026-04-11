// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkspaceSection from "./WorkspaceSection";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
}));

afterEach(() => {
  cleanup();
  authFetch.mockReset();
});

describe("WorkspaceSection", () => {
  it("ignores non-string error details", async () => {
    authFetch.mockResolvedValue({
      json: async () => ({ success: false, detail: { message: "not a string" } }),
    });

    render(<WorkspaceSection defaultWorkspace="/workspace" onUpdate={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("保存失败")).toBeTruthy();
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not accept non-string saved workspace values", async () => {
    const onUpdate = vi.fn();
    authFetch.mockResolvedValue({
      json: async () => ({ success: true, workspace: { path: "/workspace" } }),
    });

    render(<WorkspaceSection defaultWorkspace="/workspace" onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByText("保存失败")).toBeTruthy();
    });
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
