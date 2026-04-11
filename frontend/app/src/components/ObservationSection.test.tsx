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

  it("ignores non-string verify errors", async () => {
    verifyObservation.mockResolvedValue({
      success: false,
      error: { message: "not a string" },
    });

    renderActiveLangfuse();

    fireEvent.click(screen.getAllByRole("button", { name: "测试连接" })[0]);

    expect((await screen.findAllByText("连接失败：验证失败")).length).toBeGreaterThan(0);
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not treat non-boolean verify success as connected", async () => {
    verifyObservation.mockResolvedValue({
      success: "yes",
      traces: [],
    });

    renderActiveLangfuse();

    fireEvent.click(screen.getAllByRole("button", { name: "测试连接" })[0]);

    await waitFor(() => {
      expect(screen.getAllByText("连接失败：验证失败").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/已连接/)).toBeNull();
  });
});
