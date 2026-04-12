// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ObservationSection from "./ObservationSection";

const { verifyObservation } = vi.hoisted(() => ({
  verifyObservation: vi.fn(),
}));

vi.mock("../api", () => ({
  saveObservationConfig: vi.fn(async () => undefined),
  verifyObservation,
}));

afterEach(() => {
  cleanup();
  verifyObservation.mockReset();
});

function renderActiveLangfuse() {
  render(
    <ObservationSection
      config={{ active: "langfuse", langfuse: {} }}
      onUpdate={vi.fn()}
    />,
  );
}

describe("ObservationSection", () => {
  it("does not render non-string provider field values", () => {
    render(
      <ObservationSection
        config={{
          active: "langfuse",
          langfuse: {
            secret_key: "sk-secret",
            public_key: "pk-public",
            host: { value: "https://langfuse.local" },
          },
        }}
        onUpdate={vi.fn()}
      />,
    );

    expect(screen.queryByDisplayValue("[object Object]")).toBeNull();
  });

  it("shows verify API errors", async () => {
    verifyObservation.mockRejectedValue(new Error("Malformed observation verify result"));

    renderActiveLangfuse();

    fireEvent.click(screen.getAllByRole("button", { name: "测试连接" })[0]);

    expect((await screen.findAllByText("连接失败：Malformed observation verify result")).length).toBeGreaterThan(0);
  });

  it("shows failed verification results", async () => {
    verifyObservation.mockResolvedValue({
      success: false,
      error: "Langfuse keys not configured",
      traces: [],
    });

    renderActiveLangfuse();

    fireEvent.click(screen.getAllByRole("button", { name: "测试连接" })[0]);

    await waitFor(() => {
      expect(screen.getAllByText("连接失败：Langfuse keys not configured").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/已连接/)).toBeNull();
  });
});
