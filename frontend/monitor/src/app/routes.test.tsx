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
    expect(screen.getByRole("link", { name: /evaluation/i })).toBeInTheDocument();
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

  it("renders threads with pressure summary before the raw table", async () => {
    mockRoutePayloads({
      "/threads": {
        title: "Threads",
        count: 1,
        items: [
          {
            thread_id: "thread-1",
            thread_url: "/thread/thread-1",
            session_count: 2,
            last_active_ago: "2m",
            lease: {
              lease_id: "lease-1",
              lease_url: "/lease/lease-1",
              provider: "local",
            },
            state_badge: {
              color: "yellow",
              observed: "paused",
              desired: "running",
              text: "paused",
            },
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/threads"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Thread Pressure")).toBeInTheDocument();
    expect(screen.getByText("Raw Thread Table")).toBeInTheDocument();
  });

  it("renders diverged leases with triage before the raw table", async () => {
    mockRoutePayloads({
      "/diverged": {
        title: "Diverged leases",
        description: "Leases whose observed state diverges from desired state.",
        count: 1,
        items: [
          {
            lease_id: "lease-1",
            lease_url: "/lease/lease-1",
            provider: "daytona_selfhost",
            thread: {
              thread_id: "thread-1",
              thread_url: "/thread/thread-1",
            },
            state_badge: {
              color: "red",
              desired: "running",
              observed: "stopped",
              hours_diverged: 5,
            },
            error: "provider unavailable",
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/diverged"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Drift Triage")).toBeInTheDocument();
    expect(screen.getByText("Raw Divergence Table")).toBeInTheDocument();
  });

  it("renders events with signal summary before the raw table", async () => {
    mockRoutePayloads({
      "/events?limit=100": {
        title: "Events",
        description: "Recent monitor events.",
        count: 2,
        items: [
          {
            event_id: "event-1",
            event_url: "/event/event-1",
            event_type: "lease.state.changed",
            source: "monitor",
            provider: "local",
            lease: {
              lease_id: "lease-1",
              lease_url: "/lease/lease-1",
            },
            error: null,
            created_ago: "1m",
          },
          {
            event_id: "event-2",
            event_url: "/event/event-2",
            event_type: "probe.failed",
            source: "probe",
            provider: "daytona_selfhost",
            lease: {
              lease_id: null,
              lease_url: null,
            },
            error: "provider unavailable",
            created_ago: "3m",
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/events"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Signal Feed")).toBeInTheDocument();
    expect(screen.getByText("Raw Event Table")).toBeInTheDocument();
  });

  it("renders evaluation as a truthful operator surface", async () => {
    mockRoutePayloads({
      "/evaluation": {
        status: "unavailable",
        kind: "unavailable",
        tone: "warning",
        headline: "Evaluation operator truth is not wired in this runtime yet.",
        summary: "Monitor can report that evaluation truth is unavailable without pretending nothing is happening.",
        facts: [{ label: "Status", value: "unavailable" }],
        artifacts: [],
        artifact_summary: {
          present: 0,
          missing: 0,
          total: 0,
        },
        next_steps: ["Restore a truthful evaluation runtime source before reviving the monitor evaluation page."],
        raw_notes: null,
      },
    });

    render(
      <MemoryRouter initialEntries={["/evaluation"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Evaluation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /evaluation/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Evaluation operator truth is not wired in this runtime yet.")).toBeInTheDocument();
    expect(screen.getByText("Operator Facts")).toBeInTheDocument();
    expect(screen.getByText("Artifact Coverage")).toBeInTheDocument();
    expect(screen.getByText("Next Steps")).toBeInTheDocument();
    expect(screen.getByText("Restore a truthful evaluation runtime source before reviving the monitor evaluation page.")).toBeInTheDocument();
  });
});
