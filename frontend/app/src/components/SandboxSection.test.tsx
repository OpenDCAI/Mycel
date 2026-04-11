// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SandboxSection from "./SandboxSection";

vi.mock("../api", () => ({
  saveSandboxConfig: vi.fn(async () => undefined),
}));

afterEach(() => {
  cleanup();
});

describe("SandboxSection", () => {
  it("does not render non-string field values", () => {
    render(
      <SandboxSection
        sandboxes={{
          daytona: {
            provider: "daytona",
            daytona: {
              api_key: "sk-daytona",
              api_url: { value: "https://daytona.local" },
            },
          },
        }}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Daytona/ }));

    expect(screen.queryByDisplayValue("[object Object]")).toBeNull();
  });

  it("falls back to the config name when provider is not a string", () => {
    render(
      <SandboxSection
        sandboxes={{
          daytona: {
            provider: { type: "daytona" },
            daytona: { api_url: "https://daytona.local" },
          },
        }}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Daytona/ }));

    expect(screen.getByPlaceholderText("https://app.daytona.io/api")).toBeTruthy();
  });
});
