// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelMappingSection from "./ModelMappingSection";

afterEach(() => {
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
});
