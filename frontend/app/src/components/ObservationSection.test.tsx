// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ObservationSection from "./ObservationSection";

vi.mock("../api", () => ({
  saveObservationConfig: vi.fn(async () => undefined),
  verifyObservation: vi.fn(async () => ({ success: true, traces: [] })),
}));

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
});
