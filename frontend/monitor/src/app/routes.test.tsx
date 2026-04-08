import { MemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
        resources_summary: {
          running_sessions: 0,
          active_providers: 0,
          unavailable_providers: 0,
        },
        infra: {
          providers_active: 0,
          providers_unavailable: 0,
          leases_total: 0,
          leases_diverged: 0,
          leases_orphan: 0,
          leases_healthy: 0,
        },
        workload: {
          db_sessions_total: 0,
          provider_sessions_total: 0,
          running_sessions: 0,
          evaluations_running: 0,
        },
        latest_evaluation: {
          status: "idle",
          kind: "no_recorded_runs",
          tone: "default",
          headline: "No persisted evaluation runs are available yet.",
        },
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
        resources_summary: {
          running_sessions: 4,
          active_providers: 2,
          unavailable_providers: 1,
        },
        infra: {
          providers_active: 2,
          providers_unavailable: 1,
          leases_total: 3,
          leases_diverged: 1,
          leases_orphan: 0,
          leases_healthy: 2,
        },
        workload: {
          db_sessions_total: 7,
          provider_sessions_total: 4,
          running_sessions: 4,
          evaluations_running: 1,
        },
        latest_evaluation: {
          status: "running",
          kind: "running_recorded",
          tone: "warning",
          headline: "Evaluation run is actively recording new metrics.",
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
    expect(screen.getByText("Running Sessions")).toBeInTheDocument();
    expect(screen.getByText("Evaluations Running")).toBeInTheDocument();
    expect(screen.getByText("Tracked Leases")).toBeInTheDocument();
    expect(screen.getByText("Latest Evaluation")).toBeInTheDocument();
    expect(screen.getByText("Evaluation run is actively recording new metrics.")).toBeInTheDocument();
  });

  it("renders leases with a triage summary before the raw table", async () => {
    mockRoutePayloads({
      "/leases": {
        title: "All Leases",
        count: 1,
        summary: {
          healthy: 1,
          diverged: 0,
          orphan: 0,
          orphan_diverged: 0,
          total: 1,
        },
        groups: [],
        triage: {
          summary: {
            active_drift: 1,
            detached_residue: 0,
            orphan_cleanup: 0,
            healthy_capacity: 0,
            total: 1,
          },
          groups: [],
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
    expect(screen.getByText("Active Drift")).toBeInTheDocument();
    expect(screen.getByText("Detached Residue")).toBeInTheDocument();
    expect(screen.getByText("Orphan Cleanup")).toBeInTheDocument();
    expect(screen.getByText("Healthy Capacity")).toBeInTheDocument();
    expect(screen.getByText("Tracked Leases")).toBeInTheDocument();
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

  it("renders thread detail session ids as plain text when monitor has no session route", async () => {
    mockRoutePayloads({
      "/thread/thread-1": {
        thread_id: "thread-1",
        breadcrumb: [
          { label: "Threads", url: "/threads" },
          { label: "thread-1", url: "/thread/thread-1" },
        ],
        sessions: {
          title: "Sessions",
          count: 1,
          items: [
            {
              session_id: "session-1",
              session_url: "/session/session-1",
              status: "running",
              started_ago: "1m",
              ended_ago: null,
              lease: {
                lease_id: "lease-1",
                lease_url: "/lease/lease-1",
              },
              state_badge: {
                color: "green",
                observed: "running",
                desired: "running",
                text: "running",
              },
              error: null,
            },
          ],
        },
        related_leases: {
          title: "Related Leases",
          items: [{ lease_id: "lease-1", lease_url: "/lease/lease-1" }],
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/thread/thread-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: /thread:/i })).toBeInTheDocument();
    expect(screen.getByText("session-")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "session-" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "lease-1" })).toHaveLength(2);
    for (const link of screen.getAllByRole("link", { name: "lease-1" })) {
      expect(link).toHaveAttribute("href", "/lease/lease-1");
    }
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
        status: "idle",
        kind: "no_recorded_runs",
        tone: "default",
        headline: "No persisted evaluation runs are available yet.",
        summary: "Evaluation storage is wired, but there are no recorded runs to report yet.",
        facts: [{ label: "Status", value: "idle" }],
        artifacts: [],
        artifact_summary: {
          present: 0,
          missing: 0,
          total: 0,
        },
        next_steps: ["Run an evaluation to populate the operator surface with persisted runtime truth."],
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
    expect(screen.getByText("No persisted evaluation runs are available yet.")).toBeInTheDocument();
    expect(screen.getByText("Operator Facts")).toBeInTheDocument();
    expect(screen.getByText("Next Steps")).toBeInTheDocument();
    expect(screen.getByText("Run an evaluation to populate the operator surface with persisted runtime truth.")).toBeInTheDocument();
    expect(screen.queryByText("Artifact Coverage")).not.toBeInTheDocument();
    expect(screen.queryByText("Artifacts")).not.toBeInTheDocument();
  });

  it("reads local provider files even when the resource session has no lease id", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 1,
        },
        providers: [
          {
            id: "local",
            name: "local",
            description: "Local provider",
            type: "local",
            status: "active",
            capabilities: {
              filesystem: true,
              terminal: true,
              metrics: true,
              screenshot: false,
              web: false,
              process: false,
              hooks: false,
              mount: false,
            },
            telemetry: {
              running: { used: 1, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 5, limit: 100, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 8, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 20, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: { used: 5, limit: 100, unit: "%", source: "api", freshness: "live" },
            sessions: [
              {
                id: "session-1",
                threadId: "thread-1",
                agentName: "Local Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
              },
            ],
          },
        ],
      },
      "/api/settings/browse?path=~&include_files=true": {
        current_path: "~",
        parent_path: null,
        items: [{ name: "notes.txt", path: "~/notes.txt", is_dir: false }],
      },
      "/api/settings/read?path=~%2Fnotes.txt": {
        content: "hello from local sandbox",
        truncated: false,
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /local agent/i }));
    fireEvent.click((await screen.findByText("notes.txt")).closest("button") as HTMLButtonElement);

    expect(await screen.findByText("hello from local sandbox")).toBeInTheDocument();
  });

  it("does not pretend a remote lease is browsable when runtime session binding is missing", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 1,
        },
        providers: [
          {
            id: "daytona_selfhost",
            name: "daytona_selfhost",
            description: "Self-hosted Daytona",
            type: "cloud",
            status: "active",
            capabilities: {
              filesystem: true,
              terminal: true,
              metrics: true,
              screenshot: false,
              web: false,
              process: false,
              hooks: false,
              mount: true,
            },
            telemetry: {
              running: { used: 1, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 4, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 10, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: null,
              },
            ],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("无 active runtime")).toBeInTheDocument();
    const runtimeGapLabel = screen.getByText("无 runtime");
    expect(runtimeGapLabel).toBeInTheDocument();
    expect(within(runtimeGapLabel.parentElement as HTMLElement).getByText("1")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /remote agent/i }));

    expect(await screen.findByText("当前 lease 没有 active runtime session，无法浏览文件。")).toBeInTheDocument();
  });
});
