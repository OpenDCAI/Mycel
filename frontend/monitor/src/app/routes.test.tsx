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

function mockRoutePayloads(routes: Record<string, unknown>) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : String(input.url);
    const match = Object.entries(routes).find(([path]) => url.endsWith(path));
    if (!match) {
      throw new Error(`Unexpected fetch: ${url}`);
    }
    return new Response(JSON.stringify(match[1]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

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

  it("renders dashboard as a switchboard surface", async () => {
    mockRoutePayloads({
      "/dashboard": {
        snapshot_at: "2026-04-08T00:00:00Z",
        summary: {
          active_threads: 7,
          active_leases: 3,
          resources_ready: 4,
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Runtime Surfaces")).toBeInTheDocument();
    expect(screen.getByText("Operator Attention")).toBeInTheDocument();
  });

  it("renders leases with a triage summary before the raw table", async () => {
    mockRoutePayloads({
      "/leases": {
        title: "Leases",
        count: 1,
        triage: {
          active: 1,
          residue: 0,
        },
        items: [
          {
            lease_id: "lease-1",
            lease_url: "/lease/lease-1",
            provider: "local",
            instance_id: "instance-1",
            thread: {
              thread_id: "thread-1",
              thread_url: "/thread/thread-1",
            },
            state_badge: {
              color: "green",
              observed: "running",
              desired: "running",
              text: "running",
            },
            updated_ago: "1m",
            error: null,
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Lease Triage")).toBeInTheDocument();
    expect(screen.getByText("Raw Lease Table")).toBeInTheDocument();
  });
});
