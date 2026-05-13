// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PanelHeader } from "./PanelHeader";

describe("PanelHeader", () => {
  it("does not render pause or resume controls for remote sandboxes", () => {
    const onClose = vi.fn();

    const { rerender } = render(
      <PanelHeader
        threadId="thread-1"
        onClose={onClose}
      />,
    );

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByTitle("收起视窗")).toBeTruthy();

    rerender(
      <PanelHeader
        threadId="thread-1"
        onClose={onClose}
      />,
    );

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByTitle("收起视窗")).toBeTruthy();
  });
});
