// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelMappingSection from "./ModelMappingSection";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("ModelMappingSection", () => {
  it("does not log a failed mapping save once navigation already left /settings", async () => {
    window.history.replaceState({}, "", "/settings");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    render(
      <ModelMappingSection
        virtualModels={[{ id: "vm-1", name: "VM 1", description: "virtual", icon: "V" }]}
        availableModels={[{ id: "gpt-5.4", name: "GPT-5.4" }]}
        modelMapping={{}}
        enabledModels={["gpt-5.4"]}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "gpt-5.4" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });

  it("does not update mapping state when persistence fails", async () => {
    window.history.replaceState({}, "", "/settings");
    const onUpdate = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("down", { status: 503 }));

    render(
      <ModelMappingSection
        virtualModels={[{ id: "vm-1", name: "VM 1", description: "virtual", icon: "V" }]}
        availableModels={[{ id: "gpt-5.4", name: "GPT-5.4" }]}
        modelMapping={{}}
        enabledModels={["gpt-5.4"]}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "gpt-5.4" },
    });

    expect(await screen.findByText("保存失败：API 503: down")).toBeTruthy();
    expect(onUpdate).not.toHaveBeenCalled();
    expect(screen.queryByText("已保存")).toBeNull();
  });
});
