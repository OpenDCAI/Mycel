// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SandboxDetailSheet from "./SandboxDetailSheet";

vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children: ReactNode }) => <>{children}</>,
  SheetContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SheetHeader: ({ children }: { children: ReactNode }) => <>{children}</>,
  SheetTitle: ({ children }: { children: ReactNode }) => <>{children}</>,
  SheetDescription: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/SandboxFileBrowser", () => ({
  SandboxFileBrowser: () => null,
}));

vi.mock("@/components/MemberAvatar", () => ({
  default: () => null,
}));

afterEach(() => {
  cleanup();
});

describe("SandboxDetailSheet wording contract", () => {
  it("uses Agent wording for the session section header", () => {
    render(
      <SandboxDetailSheet
        open
        onClose={vi.fn()}
        providerType="local"
        group={{
          leaseId: "lease-1",
          status: "running",
          startedAt: "2026-04-08T00:00:00Z",
          metrics: null,
          sessions: [
            {
              id: "session-1",
              agentName: "Agent One",
              avatarUrl: null,
              threadId: "thread-1",
              status: "running",
              startedAt: "2026-04-08T00:00:00Z",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Agent")).toBeTruthy();
  });
});
