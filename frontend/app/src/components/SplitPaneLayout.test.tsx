// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SplitPaneLayout from "./SplitPaneLayout";

beforeEach(() => {
  window.innerWidth = 1024;
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

afterEach(cleanup);

function renderLayout({ hasDetail, sidebarCollapsed }: { hasDetail: boolean; sidebarCollapsed?: boolean }) {
  return render(
    <MemoryRouter initialEntries={["/chat/thread-1"]}>
      <Routes>
        <Route
          path="/chat/:threadId"
          element={
            <SplitPaneLayout
              sidebar={<aside data-testid="sidebar">对话列表</aside>}
              hasDetail={hasDetail}
              sidebarCollapsed={sidebarCollapsed}
            />
          }
        >
          <Route index element={<main>对话详情</main>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("SplitPaneLayout", () => {
  it("hides the desktop sidebar when a detail page is collapsed", () => {
    renderLayout({ hasDetail: true, sidebarCollapsed: true });

    expect(screen.getByTestId("sidebar").parentElement?.className).toContain("hidden");
    expect(screen.getByText("对话详情")).toBeTruthy();
  });

  it("keeps the sidebar visible when no detail page is active", () => {
    renderLayout({ hasDetail: false, sidebarCollapsed: true });

    expect(screen.getByTestId("sidebar").parentElement?.className).not.toContain("hidden");
    expect(screen.getByText("选择一项查看详情")).toBeTruthy();
  });
});
