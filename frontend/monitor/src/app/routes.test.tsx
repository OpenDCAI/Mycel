import { MemoryRouter } from "react-router-dom";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MonitorRoutes } from "./routes";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        snapshot_at: "2026-04-08T00:00:00Z",
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );
});

describe("MonitorRoutes", () => {
  it("renders the current monitor route set under the app router", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByText("Leon Sandbox Monitor")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /threads/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /resources/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /leases/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /diverged/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /events/i })).toBeInTheDocument();
  });

  it("shows dashboard content for /dashboard", async () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByText("Leon Sandbox Monitor")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("renders the shell with a sidebar and highlights the active route", () => {
    render(
      <MemoryRouter initialEntries={["/leases"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Monitor sections" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /leases/i })).toHaveAttribute("aria-current", "page");
  });
});
