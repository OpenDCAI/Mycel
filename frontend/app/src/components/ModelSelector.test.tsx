// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelSelector from "./ModelSelector";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
}));

function response(body: unknown, ok = true, status = ok ? 200 : 500, text = JSON.stringify(body)) {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => text,
  };
}

afterEach(() => {
  cleanup();
  authFetch.mockReset();
});

describe("ModelSelector", () => {
  it("ignores non-string error details", async () => {
    authFetch.mockImplementation(async (url: string) => {
      if (url === "/api/settings") return response({ enabled_models: [] });
      return response({ detail: { message: "not a string" } }, false);
    });

    render(<ModelSelector currentModel="leon:medium" threadId="thread-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Medium/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Mini" }));

    expect(await screen.findByText("更新模型失败")).toBeTruthy();
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("falls back to the requested model when the saved model is not a string", async () => {
    const onModelChange = vi.fn();
    authFetch.mockImplementation(async (url: string) => {
      if (url === "/api/settings") return response({ enabled_models: [] });
      return response({ model: { id: "leon:max" } });
    });

    render(
      <ModelSelector
        currentModel="leon:medium"
        threadId="thread-1"
        onModelChange={onModelChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Medium/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Max" }));

    await waitFor(() => {
      expect(onModelChange).toHaveBeenCalledWith("leon:max");
    });
  });

  it("ignores malformed enabled model lists", async () => {
    authFetch.mockResolvedValue(response({ enabled_models: { bad: true } }));

    render(<ModelSelector currentModel="custom:model" threadId="thread-1" />);

    fireEvent.click(screen.getByRole("button", { name: /custom:model/ }));

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/settings");
    });
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not render custom models from a failed settings response", async () => {
    authFetch.mockResolvedValue(response({ enabled_models: ["custom:model"] }, false, 503, "down"));

    render(<ModelSelector currentModel="leon:medium" threadId="thread-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Medium/ }));
    fireEvent.click(await screen.findByText("自定义"));

    expect(await screen.findByText("加载模型失败：API 503: down")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "custom:model" })).toBeNull();
  });
});
