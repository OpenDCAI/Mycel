// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../api";
import BashRenderer from "./BashRenderer";

function renderBashRenderer(step: ToolStep) {
  return render(<BashRenderer step={step} expanded={false} />);
}

describe("BashRenderer", () => {
  it("ignores non-string command fields instead of rendering invalid labels", () => {
    renderBashRenderer({
      id: "tool-1",
      name: "Bash",
      args: { command: 123, description: "display description" },
      status: "done",
      timestamp: 1,
    });

    expect(screen.getByText("display description")).toBeTruthy();
    expect(screen.queryByText("123")).toBeNull();
  });
});
