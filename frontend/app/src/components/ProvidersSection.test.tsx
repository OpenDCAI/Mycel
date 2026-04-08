// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProvidersSection from "./ProvidersSection";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("ProvidersSection", () => {
  it("does not log a failed provider save once navigation already left /settings", async () => {
    window.history.replaceState({}, "", "/settings");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, base_url: null } }}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("输入 Anthropic API 密钥"), {
      target: { value: "sk-test" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
