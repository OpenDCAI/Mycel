// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TabBar } from "./TabBar";

describe("TabBar", () => {
  afterEach(() => cleanup());

  it("does not expose the retired terminal realtime panel", () => {
    render(
      <TabBar
        activeTab="files"
        onTabChange={vi.fn()}
        hasRunningAgents={false}
        hasAgents={false}
      />,
    );

    expect(screen.queryByRole("button", { name: "终端" })).toBeNull();
    expect(screen.getByRole("button", { name: "文件" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Agent" })).toBeTruthy();
  });
});
