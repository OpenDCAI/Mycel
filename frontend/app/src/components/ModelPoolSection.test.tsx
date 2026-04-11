// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelPoolSection from "./ModelPoolSection";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
}));

function response(body: unknown) {
  return {
    json: async () => body,
  };
}

function renderModelPool() {
  return render(
    <ModelPoolSection
      models={[{ id: "custom:model", name: "Custom", custom: true }]}
      enabledModels={["custom:model"]}
      customConfig={{}}
      providers={{ openai: { api_key: null, base_url: null } }}
      onToggle={vi.fn()}
      onAddCustomModel={vi.fn()}
      onRemoveCustomModel={vi.fn()}
    />,
  );
}

afterEach(() => {
  cleanup();
  authFetch.mockReset();
});

describe("ModelPoolSection", () => {
  it("ignores non-string model test errors", async () => {
    authFetch.mockResolvedValue(response({
      success: false,
      error: { message: "not a string" },
    }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "测试" }));

    expect(await screen.findByText("测试失败")).toBeTruthy();
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not accept non-boolean model test success values", async () => {
    authFetch.mockResolvedValue(response({ success: "yes" }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "测试" }));

    await waitFor(() => {
      expect(screen.getByText("测试失败")).toBeTruthy();
    });
    expect(screen.queryByText("✓")).toBeNull();
  });
});
