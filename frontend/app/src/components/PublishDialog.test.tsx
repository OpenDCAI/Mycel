// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PublishDialog from "./PublishDialog";
import { toast } from "sonner";

const { publishAgent, publishAgentUserToMarketplace } = vi.hoisted(() => ({
  publishAgent: vi.fn(),
  publishAgentUserToMarketplace: vi.fn(),
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogHeader: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogTitle: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogDescription: ({ children }: { children: ReactNode }) => <>{children}</>,
  DialogFooter: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string }) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

vi.mock("@/components/ui/label", () => ({
  Label: ({ children }: { children: ReactNode }) => <label>{children}</label>,
}));

vi.mock("@/store/app-store", () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      getAgentById: () => ({
        id: "agent-1",
        name: "Morel",
        version: "1.0.0",
      }),
      publishAgent,
    }),
}));

vi.mock("@/store/marketplace-store", () => ({
  useMarketplaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      publishAgentUserToMarketplace,
    }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PublishDialog", () => {
  it("fails loudly when marketplace publish fails", async () => {
    publishAgent.mockResolvedValue(undefined);
    publishAgentUserToMarketplace.mockRejectedValue(new Error("Marketplace Hub unavailable"));

    render(<PublishDialog open onOpenChange={vi.fn()} agentId="agent-1" />);

    fireEvent.click(screen.getByRole("button", { name: "发布 v1.0.1" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("发布失败：Marketplace Hub unavailable");
    });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("publishes agent users without exposing the hub member type to the dialog", async () => {
    publishAgent.mockResolvedValue(undefined);
    publishAgentUserToMarketplace.mockResolvedValue({});

    render(<PublishDialog open onOpenChange={vi.fn()} agentId="agent-1" />);

    fireEvent.click(screen.getByRole("button", { name: "发布 v1.0.1" }));

    await waitFor(() => {
      expect(publishAgentUserToMarketplace).toHaveBeenCalledWith("agent-1", "patch", "", [], "public");
    });
  });
});
