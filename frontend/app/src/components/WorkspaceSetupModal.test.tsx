// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkspaceSetupModal from "./WorkspaceSetupModal";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
}));

vi.mock("./FilesystemBrowser", () => ({
  default: () => <div>filesystem-browser</div>,
}));

afterEach(() => {
  authFetch.mockReset();
});

describe("WorkspaceSetupModal", () => {
  it("ignores non-string error details", async () => {
    authFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: { message: "not a string" } }),
    });

    render(<WorkspaceSetupModal open onClose={vi.fn()} onWorkspaceSet={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("保存失败")).toBeTruthy();
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not accept non-string saved workspace values", async () => {
    const onWorkspaceSet = vi.fn();
    const onClose = vi.fn();
    authFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ workspace: { path: "/workspace" } }),
    });

    render(<WorkspaceSetupModal open onClose={onClose} onWorkspaceSet={onWorkspaceSet} />);

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByText("保存失败")).toBeTruthy();
    });
    expect(onWorkspaceSet).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
