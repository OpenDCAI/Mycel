import { MemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
        infra: {
          providers_active: 0,
          providers_unavailable: 0,
          leases_total: 0,
          leases_diverged: 0,
          leases_orphan: 0,
        },
        workload: {
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
    expect(screen.getByRole("link", { name: /resources/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /leases/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /evaluation/i })).toBeInTheDocument();
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

  it("keeps sidebar copy focused on operator surfaces", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByText("Resource truth, lease workbench, and evaluation.")).toBeInTheDocument();
    expect(screen.queryByText("Current monitor routes, unified under one console shell.")).not.toBeInTheDocument();
  });

  it("lets the operator collapse the monitor sidebar", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));

    expect(screen.getByRole("button", { name: /expand sidebar/i })).toBeInTheDocument();
  });

  it("renders dashboard as a switchboard surface", async () => {
    mockRoutePayloads({
      "/dashboard": {
        snapshot_at: "2026-04-08T00:00:00Z",
        infra: {
          providers_active: 2,
          providers_unavailable: 1,
          leases_total: 3,
          leases_diverged: 1,
          leases_orphan: 0,
        },
        workload: {
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

  it("routes dashboard cards to their owning surfaces", async () => {
    mockRoutePayloads({
      "/dashboard": {
        snapshot_at: "2026-04-08T00:00:00Z",
        infra: {
          providers_active: 2,
          providers_unavailable: 1,
          leases_total: 3,
          leases_diverged: 1,
          leases_orphan: 2,
        },
        workload: {
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

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /running sessions/i })).toHaveAttribute("href", "/resources");
    expect(screen.getByRole("link", { name: /tracked leases/i })).toHaveAttribute("href", "/leases");
    expect(screen.getByRole("link", { name: /provider coverage/i })).toHaveAttribute("href", "/resources");
    expect(screen.getByRole("link", { name: /lease drift/i })).toHaveAttribute("href", "/leases");
    expect(screen.getByRole("link", { name: /latest evaluation/i })).toHaveAttribute("href", "/evaluation");
  });

  it("renders leases with triage categories but without a duplicate tracked-leases card", async () => {
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
            provider: "local",
            instance_id: "instance-1",
            thread: {
              thread_id: "thread-1",
            },
            triage: {
              category: "active_drift",
              title: "Active Drift",
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
    expect(screen.getAllByText("Active Drift").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Detached Residue").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Orphan Cleanup").length).toBeGreaterThan(0);
    expect(screen.getByText("Healthy Capacity")).toBeInTheDocument();
    expect(screen.getByText("Total: 1")).toBeInTheDocument();
    expect(screen.queryByText("Tracked Leases")).not.toBeInTheDocument();
    expect(screen.getByText("Lease Workbench")).toBeInTheDocument();
    expect(screen.getByText("Topology")).toBeInTheDocument();
    expect(screen.queryByText("Provider")).not.toBeInTheDocument();
    expect(screen.queryByText("Instance ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Thread")).not.toBeInTheDocument();
  });

  it("filters the lease table by triage card selection", async () => {
    mockRoutePayloads({
      "/leases": {
        title: "All Leases",
        count: 2,
        summary: {
          healthy: 0,
          diverged: 1,
          orphan: 0,
          orphan_diverged: 1,
          total: 2,
        },
        groups: [],
        triage: {
          summary: {
            active_drift: 0,
            detached_residue: 1,
            orphan_cleanup: 1,
            healthy_capacity: 0,
            total: 2,
          },
          groups: [],
        },
        items: [
          {
            lease_id: "lease-detached",
            provider: "local",
            instance_id: null,
            thread: {
              thread_id: "thread-a",
            },
            triage: {
              category: "detached_residue",
              title: "Detached Residue",
            },
            state_badge: {
              color: "yellow",
              observed: "detached",
              desired: "running",
              text: "detached -> running",
            },
            updated_ago: "14h ago",
            error: null,
          },
          {
            lease_id: "lease-orphan",
            provider: "local",
            instance_id: null,
            thread: {
              thread_id: null,
            },
            triage: {
              category: "orphan_cleanup",
              title: "Orphan Cleanup",
            },
            state_badge: {
              color: "yellow",
              observed: "detached",
              desired: "running",
              text: "detached -> running",
            },
            updated_ago: "2d ago",
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

    expect(await screen.findByRole("heading", { name: "All Leases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "lease-detached" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "lease-orphan" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /detached residue/i }));

    expect(screen.getByRole("link", { name: "lease-detached" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "lease-orphan" })).not.toBeInTheDocument();
    expect(screen.getByText("Showing Detached Residue")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /all triage/i }));

    expect(screen.getByRole("link", { name: "lease-detached" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "lease-orphan" })).toBeInTheDocument();
  });

  it("renders lease detail under the leases surface", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { current: "page", name: /leases/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Healthy Capacity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "runtime-1" })).toBeInTheDocument();
    expect(screen.getAllByText("thread-1").length).toBeGreaterThan(0);
  });

  it("keeps lease detail description focused on triage prose instead of repeating provider and state", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByText("Lease is converged and ready.")).toBeInTheDocument();
    expect(screen.queryByText("Provider daytona · observed running · desired running")).not.toBeInTheDocument();
  });

  it("links lease relations into the hidden detail routes", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "daytona" })).toHaveAttribute("href", "/providers/daytona");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
    expect(screen.getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
  });

  it("keeps lease detail runtime truth in relations instead of repeating it in the operator summary", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getAllByText("runtime-1")).toHaveLength(1);
  });

  it("keeps lease detail relations compact instead of splitting threads and sessions into separate tables", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "detached",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "yellow",
            observed: "detached",
            desired: "running",
            text: "detached -> running",
          },
        },
        triage: {
          category: "detached_residue",
          title: "Detached Residue",
          description: "Lease is detached residue and can enter managed cleanup.",
          tone: "danger",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
        cleanup: {
          allowed: true,
          recommended_action: "lease_cleanup",
          reason: "Lease is detached residue and can enter managed cleanup.",
          operation: null,
          recent_operations: [],
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Threads" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sessions" })).not.toBeInTheDocument();
    const relationsHeading = screen.getByRole("heading", { name: "Relations" });
    const relationsSection = relationsHeading.closest("section");
    if (!relationsSection) {
      throw new Error("Expected lease detail relations section");
    }
    expect(within(relationsSection).getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
    expect(within(relationsSection).getByText("session-1")).toBeInTheDocument();
    expect(within(relationsSection).getByText("active")).toBeInTheDocument();
  });

  it("keeps lease detail object jumps prominent inside the relations surface", async () => {
    mockRoutePayloads({
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Object Links" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Context" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "daytona" })).toHaveAttribute("href", "/providers/daytona");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
    expect(screen.getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
  });

  it("redirects to operation detail when cleanup removes the lease", async () => {
    let leaseDetailReads = 0;

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : String(input.url);
      const method =
        init?.method ?? (typeof input === "object" && input !== null && "method" in input ? String(input.method) : "GET");

      if (url.endsWith("/leases/lease-1") && method === "GET") {
        leaseDetailReads += 1;
        if (leaseDetailReads === 1) {
          return new Response(
            JSON.stringify({
              lease: {
                lease_id: "lease-1",
                provider_name: "daytona",
                desired_state: "running",
                observed_state: "detached",
                updated_at: "2026-04-08T00:00:00Z",
                updated_ago: "1m ago",
                last_error: null,
                badge: {
                  color: "yellow",
                  observed: "detached",
                  desired: "running",
                  text: "detached -> running",
                },
              },
              triage: {
                category: "orphan_cleanup",
                title: "Orphan Cleanup",
                description: "Lease lost its active thread binding.",
                tone: "warning",
              },
              provider: {
                id: "daytona",
                name: "daytona",
              },
              runtime: {
                runtime_session_id: "runtime-1",
              },
              threads: [],
              sessions: [],
              cleanup: {
                allowed: true,
                recommended_action: "lease_cleanup",
                reason: "Lease is orphan cleanup residue and can enter managed cleanup.",
                operation: {
                  operation_id: "op-1",
                  kind: "lease_cleanup",
                  status: "running",
                  summary: "Destroy flow started",
                },
                recent_operations: [
                  {
                    operation_id: "op-1",
                    kind: "lease_cleanup",
                    status: "running",
                    summary: "Destroy flow started",
                  },
                ],
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify({ detail: "Lease lease-1 not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.endsWith("/leases/lease-1/cleanup") && method === "POST") {
        return new Response(
          JSON.stringify({
            accepted: true,
            message: "Lease cleanup completed.",
            operation: {
              operation_id: "op-2",
              kind: "lease_cleanup",
              target_type: "lease",
              target_id: "lease-1",
              status: "succeeded",
              summary: "Lease cleanup completed.",
            },
            current_truth: {
              lease_id: "lease-1",
              triage_category: "orphan_cleanup",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/operations/op-2") && method === "GET") {
        return new Response(
          JSON.stringify({
            operation: {
              operation_id: "op-2",
              kind: "lease_cleanup",
              status: "succeeded",
              summary: "Lease cleanup completed.",
              reason: "Lease is orphan cleanup residue and can enter managed cleanup.",
            },
            target: {
              target_type: "lease",
              target_id: "lease-1",
              provider_id: "daytona",
              runtime_session_id: "runtime-1",
              thread_ids: [],
            },
            result_truth: {
              lease_state_before: "detached",
              lease_state_after: null,
              runtime_state_after: null,
              thread_state_after: null,
            },
            events: [
              { at: "2026-04-10T10:00:00Z", status: "pending", message: "Cleanup queued" },
              { at: "2026-04-10T10:00:05Z", status: "running", message: "Destroy flow started" },
              { at: "2026-04-10T10:00:06Z", status: "succeeded", message: "Lease cleanup completed." },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cleanup" })).toBeInTheDocument();
    expect(screen.getByText("Lease is orphan cleanup residue and can enter managed cleanup.")).toBeInTheDocument();
    expect(screen.getByText("Decision")).toBeInTheDocument();
    expect(screen.getByText("Current Operation")).toBeInTheDocument();
    expect(screen.getByText("Action Lane")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent Operations" })).toBeInTheDocument();
    expect(screen.getByText("Managed cleanup ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start lease cleanup" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "op-1" })).toHaveAttribute("href", "/operations/op-1");

    fireEvent.click(screen.getByRole("button", { name: "Start lease cleanup" }));

    expect(await screen.findByRole("heading", { name: "Operation op-2" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Lease lease-1" })).not.toBeInTheDocument();
    expect(screen.getByText("Lease cleanup completed.")).toBeInTheDocument();
  });

  it("renders operation detail under the leases surface", async () => {
    mockRoutePayloads({
      "/operations/op-1": {
        operation: {
          operation_id: "op-1",
          kind: "lease_cleanup",
          status: "running",
          summary: "Destroy flow started",
          reason: "Lease is orphan cleanup residue and can enter managed cleanup.",
        },
        target: {
          target_type: "lease",
          target_id: "lease-1",
          provider_id: "daytona",
          runtime_session_id: "runtime-1",
          thread_ids: [],
        },
        result_truth: {
          lease_state_before: "detached",
          lease_state_after: null,
          runtime_state_after: null,
          thread_state_after: null,
        },
        events: [
          { at: "2026-04-10T10:00:00Z", status: "pending", message: "Cleanup queued" },
          { at: "2026-04-10T10:00:05Z", status: "running", message: "Destroy flow started" },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/operations/op-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Operation op-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { current: "page", name: /leases/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Operation Truth" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Result Truth" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Event Timeline" })).toBeInTheDocument();
    expect(screen.getByText("Destroy flow started")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "lease-1" })).toHaveAttribute("href", "/leases/lease-1");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
    expect(screen.getByRole("link", { name: "daytona" })).toHaveAttribute("href", "/providers/daytona");
  });

  it("renders provider detail under the resources surface", async () => {
    mockRoutePayloads({
      "/providers/daytona": {
        provider: {
          id: "daytona",
          name: "daytona",
          description: "Self-hosted Daytona",
          type: "cloud",
          status: "active",
          sessions: [],
        },
        lease_ids: ["lease-1", "lease-2"],
        thread_ids: ["thread-1"],
        runtime_session_ids: ["runtime-1"],
      },
    });

    render(
      <MemoryRouter initialEntries={["/providers/daytona"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Provider daytona" })).toBeInTheDocument();
    expect(screen.getByRole("link", { current: "page", name: /resources/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "lease-1" })).toHaveAttribute("href", "/leases/lease-1");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
    expect(screen.getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
  });

  it("keeps provider detail relations focused on provider truth instead of repeating object counts", async () => {
    mockRoutePayloads({
      "/providers/daytona": {
        provider: {
          id: "daytona",
          name: "daytona",
          description: "Self-hosted Daytona",
          type: "cloud",
          status: "active",
          sessions: [],
        },
        lease_ids: ["lease-1", "lease-2"],
        thread_ids: ["thread-1"],
        runtime_session_ids: ["runtime-1"],
      },
    });

    render(
      <MemoryRouter initialEntries={["/providers/daytona"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Provider daytona" })).toBeInTheDocument();
    const relationsHeading = screen.getByRole("heading", { name: "Relations" });
    const relationsSection = relationsHeading.closest("section");
    if (!relationsSection) {
      throw new Error("Expected provider detail relations section");
    }
    expect(within(relationsSection).queryByText("Leases")).not.toBeInTheDocument();
    expect(within(relationsSection).queryByText("Runtimes")).not.toBeInTheDocument();
    expect(within(relationsSection).queryByText("Threads")).not.toBeInTheDocument();
  });

  it("keeps provider detail description focused on description instead of repeating type and status", async () => {
    mockRoutePayloads({
      "/providers/daytona": {
        provider: {
          id: "daytona",
          name: "daytona",
          description: "Self-hosted Daytona",
          type: "cloud",
          status: "active",
          sessions: [],
        },
        lease_ids: ["lease-1"],
        thread_ids: ["thread-1"],
        runtime_session_ids: ["runtime-1"],
      },
    });

    render(
      <MemoryRouter initialEntries={["/providers/daytona"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Provider daytona" })).toBeInTheDocument();
    expect(screen.getByText("Self-hosted Daytona")).toBeInTheDocument();
    expect(screen.queryByText("Self-hosted Daytona · cloud · active")).not.toBeInTheDocument();
  });

  it("renders runtime detail under the resources surface", async () => {
    mockRoutePayloads({
      "/runtimes/runtime-1": {
        provider: {
          id: "daytona",
          name: "daytona",
          status: "active",
          consoleUrl: "https://console.example/runtime-1",
        },
        runtime: {
          runtimeSessionId: "runtime-1",
          status: "running",
          threadId: "thread-1",
          leaseId: "lease-1",
          agentName: "Planner",
          webUrl: "https://sandbox.example/runtime-1",
        },
        lease_id: "lease-1",
        thread_id: "thread-1",
      },
    });

    render(
      <MemoryRouter initialEntries={["/runtimes/runtime-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Runtime runtime-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { current: "page", name: /resources/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "daytona" })).toHaveAttribute("href", "/providers/daytona");
    expect(screen.getByRole("link", { name: "lease-1" })).toHaveAttribute("href", "/leases/lease-1");
    expect(screen.getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
  });

  it("uses a consistent surface backlink label across hidden detail pages", async () => {
    mockRoutePayloads({
      "/runtimes/runtime-1": {
        provider: {
          id: "daytona",
          name: "daytona",
          status: "active",
          consoleUrl: "https://console.example/runtime-1",
        },
        runtime: {
          runtimeSessionId: "runtime-1",
          status: "running",
          threadId: "thread-1",
          leaseId: "lease-1",
          agentName: "Planner",
          webUrl: "https://sandbox.example/runtime-1",
        },
        lease_id: "lease-1",
        thread_id: "thread-1",
      },
      "/threads/thread-1": {
        thread: {
          id: "thread-1",
          thread_id: "thread-1",
          title: "Investigate sandbox drift",
          status: "active",
        },
        owner: {
          user_id: "user-1",
          display_name: "Ada",
        },
        summary: {
          provider_name: "daytona",
          lease_id: "lease-1",
          current_instance_id: "runtime-1",
          desired_state: "running",
          observed_state: "running",
        },
        sessions: [{ chat_session_id: "session-1", status: "active" }],
      },
      "/leases/lease-1": {
        lease: {
          lease_id: "lease-1",
          provider_name: "daytona",
          desired_state: "running",
          observed_state: "running",
          updated_at: "2026-04-08T00:00:00Z",
          updated_ago: "1m ago",
          last_error: null,
          badge: {
            color: "green",
            observed: "running",
            desired: "running",
            text: "running",
          },
        },
        triage: {
          category: "healthy_capacity",
          title: "Healthy Capacity",
          description: "Lease is converged and ready.",
          tone: "success",
        },
        provider: {
          id: "daytona",
          name: "daytona",
        },
        runtime: {
          runtime_session_id: "runtime-1",
        },
        threads: [{ thread_id: "thread-1" }],
        sessions: [{ chat_session_id: "session-1", thread_id: "thread-1", status: "active" }],
      },
    });

    const runtimeView = render(
      <MemoryRouter initialEntries={["/runtimes/runtime-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Runtime runtime-1" })).toBeInTheDocument();
    expect(screen.getByText("Surface")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Resources" }).some((link) => link.getAttribute("href") === "/resources")).toBe(true);

    runtimeView.unmount();

    const threadView = render(
      <MemoryRouter initialEntries={["/threads/thread-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Thread thread-1" })).toBeInTheDocument();
    expect(screen.getByText("Surface")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Leases" })).toHaveAttribute("href", "/leases");

    threadView.unmount();

    render(
      <MemoryRouter initialEntries={["/leases/lease-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Lease lease-1" })).toBeInTheDocument();
    expect(screen.getByText("Surface")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Leases" })).toHaveAttribute("href", "/leases");
  });

  it("renders thread detail under the leases surface", async () => {
    mockRoutePayloads({
      "/threads/thread-1": {
        thread: {
          id: "thread-1",
          title: "Investigate sandbox drift",
          status: "active",
        },
        owner: {
          user_id: "user-1",
          display_name: "Ada",
        },
        summary: {
          provider_name: "daytona",
          lease_id: "lease-1",
          current_instance_id: "runtime-1",
          desired_state: "running",
          observed_state: "running",
        },
        sessions: [{ chat_session_id: "session-1", status: "active" }],
        trajectory: {
          run_id: "run-1",
          conversation: [
            { role: "human", text: "Please inspect the sandbox drift." },
            { role: "tool_call", tool: "terminal", args: "{'cmd': 'pwd'}" },
            { role: "tool_result", tool: "terminal", text: "/workspace" },
            { role: "assistant", text: "The sandbox is healthy now." },
          ],
          events: [
            { seq: 1, event_type: "tool_call", actor: "tool", summary: "terminal" },
            { seq: 2, event_type: "status", actor: "runtime", summary: "state=active calls=1" },
          ],
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/threads/thread-1"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Thread thread-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { current: "page", name: /leases/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "daytona" })).toHaveAttribute("href", "/providers/daytona");
    expect(screen.getByRole("link", { name: "lease-1" })).toHaveAttribute("href", "/leases/lease-1");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
    expect(screen.getByRole("heading", { name: "Trajectory" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conversation Ledger" })).toBeInTheDocument();
    expect(screen.getByText("Please inspect the sandbox drift.")).toBeInTheDocument();
    expect(screen.getByText("The sandbox is healthy now.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run Event Timeline" }));

    expect(screen.getByText("tool_call")).toBeInTheDocument();
    expect(screen.getByText("state=active calls=1")).toBeInTheDocument();
  });

  it("renders evaluation as a truthful operator surface", async () => {
    mockRoutePayloads({
      "/evaluation": {
        status: "idle",
        kind: "no_recorded_runs",
        tone: "default",
        headline: "No persisted evaluation runs are available yet.",
        summary: "Evaluation storage is wired, but there are no recorded runs to report yet.",
        source: {
          kind: "persisted_latest_run",
          label: "Latest Persisted Run",
        },
        subject: {
          thread_id: "thread-eval",
          run_id: "run-1",
          user_message: "leave a hello note",
          started_at: "2026-04-08T00:00:00Z",
          finished_at: "2026-04-08T00:03:00Z",
        },
        facts: [{ label: "Status", value: "idle" }],
        artifacts: [],
        artifact_summary: {
          present: 0,
          missing: 0,
          total: 0,
        },
        limitations: ["This page is showing the latest persisted evaluation run, not a live event stream."],
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
    expect(screen.getByText("Latest Persisted Run")).toBeInTheDocument();
    expect(screen.getByText("Run Subject")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "thread-eval" })).toHaveAttribute("href", "/threads/thread-eval");
    expect(screen.getByText("Operator Facts")).toBeInTheDocument();
    expect(screen.getByText("Truth Boundary")).toBeInTheDocument();
    expect(screen.getByText("This page is showing the latest persisted evaluation run, not a live event stream.")).toBeInTheDocument();
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

  it("links resource objects into the hidden detail routes", async () => {
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
            id: "daytona",
            name: "daytona",
            description: "Self-hosted Daytona",
            type: "cloud",
            status: "active",
            capabilities: {
              filesystem: true,
              terminal: true,
              metrics: true,
              screenshot: false,
              web: true,
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
                runtimeSessionId: "runtime-1",
                threadId: "thread-1",
                agentName: "Planner",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                  webUrl: "https://sandbox.example/runtime-1",
                },
              },
            ],
          },
        ],
      },
      "/sandbox/lease-1/browse?path=%2F": {
        current_path: "/",
        parent_path: null,
        items: [],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Resources" })).toBeInTheDocument();
    expect(screen.queryByText("Global Resource Surface")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "daytona detail" })).toHaveAttribute("href", "/providers/daytona");
    fireEvent.click(await screen.findByRole("button", { name: /planner/i }));
    expect(await screen.findByRole("link", { name: "lease-1" })).toHaveAttribute("href", "/leases/lease-1");
    expect(screen.getByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/threads/thread-1");
    expect(screen.getByRole("link", { name: "runtime-1" })).toHaveAttribute("href", "/runtimes/runtime-1");
  });

  it("keeps provider cards provider-scoped and moves concrete metrics into sandbox detail", async () => {
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
            id: "daytona",
            name: "daytona",
            description: "Self-hosted Daytona",
            type: "cloud",
            status: "active",
            capabilities: {
              filesystem: true,
              terminal: true,
              metrics: true,
              screenshot: false,
              web: true,
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
                runtimeSessionId: "runtime-1",
                threadId: "thread-1",
                agentName: "Planner",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                  webUrl: "https://sandbox.example/runtime-1",
                },
              },
            ],
          },
        ],
      },
      "/sandbox/lease-1/browse?path=%2F": {
        current_path: "/",
        parent_path: null,
        items: [],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    const providerCard = await screen.findByRole("button", { name: /daytona/i });
    expect(within(providerCard).getByText("运行中沙盒")).toBeInTheDocument();
    expect(within(providerCard).queryByText("CPU")).not.toBeInTheDocument();
    expect(within(providerCard).queryByText("RAM")).not.toBeInTheDocument();
    expect(within(providerCard).queryByText("Disk")).not.toBeInTheDocument();
    expect(within(providerCard).queryByText("FS")).not.toBeInTheDocument();
    expect(within(providerCard).getByLabelText("filesystem enabled")).toBeInTheDocument();
    expect(within(providerCard).getByLabelText("terminal enabled")).toBeInTheDocument();
    expect(within(providerCard).getByText("5/8")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /planner/i }));

    expect(await screen.findByText("实时指标")).toBeInTheDocument();
    expect(screen.getByText("工作区文件")).toBeInTheDocument();
    expect(screen.getByText("CPU")).toBeInTheDocument();
    expect(screen.getByText("RAM")).toBeInTheDocument();
    expect(screen.getByText("Disk")).toBeInTheDocument();
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

    expect(await screen.findByRole("button", { name: /daytona_selfhost/i })).toHaveTextContent("1 未连上沙盒");
    expect(await screen.findByText("未连上运行时")).toBeInTheDocument();
    const runtimeGapLabel = screen.getByText("未连上沙盒");
    expect(runtimeGapLabel).toBeInTheDocument();
    expect(within(runtimeGapLabel.parentElement as HTMLElement).getByText("1")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /remote agent/i }));

    expect(await screen.findByText("当前 lease 没有 active runtime session，无法浏览文件。")).toBeInTheDocument();
  });

  it("does not attempt file browsing for paused remote sandboxes", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 0,
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
              running: { used: 0, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 4, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 10, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: { used: null, limit: null, unit: "%", source: "unknown", freshness: "live" },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "paused",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 0.5,
                  memoryLimit: 1,
                  disk: 0.2,
                  diskLimit: 3,
                  networkIn: null,
                  networkOut: null,
                },
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

    fireEvent.click(await screen.findByRole("button", { name: /remote agent/i }));

    expect(await screen.findByText("沙盒已暂停，恢复运行后才能浏览文件。")).toBeInTheDocument();
  });

  it("uses live session rows as the provider-card running truth when telemetry count lags", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 2,
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
                agentName: "Local Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
              },
              {
                id: "session-2",
                threadId: "thread-2",
                agentName: "Local Agent 2",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
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

    const providerCard = (await screen.findAllByRole("button", { name: /local/i })).find((element) =>
      element.className.includes("provider-card"),
    ) as HTMLElement;
    expect(within(providerCard).getByText("2")).toBeInTheDocument();
    expect(within(providerCard).queryByText(/^1$/)).not.toBeInTheDocument();
  });

  it("uses provider session rows as the summary running truth when summary count lags", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 2,
          active_providers: 2,
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
                agentName: "Local Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
              },
              {
                id: "session-2",
                threadId: "thread-2",
                agentName: "Local Agent 2",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
              },
            ],
          },
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
              running: { used: 0, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 4, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 10, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
            sessions: [
              {
                id: "lease-1:thread-3",
                leaseId: "lease-1",
                threadId: "thread-3",
                runtimeSessionId: "runtime-3",
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

    expect(await screen.findByText("3 运行中")).toBeInTheDocument();
  });

  it("surfaces when provider-card cpu is only meaningful at the sandbox level", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: null,
                  memoryLimit: null,
                  disk: null,
                  diskLimit: null,
                  networkIn: null,
                  networkOut: null,
                },
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

    const providerCard = await screen.findByRole("button", { name: /daytona_selfhost/i });
    expect(within(providerCard).queryByText("CPU 沙盒级")).not.toBeInTheDocument();
    expect(within(providerCard).queryByText("CPU")).not.toBeInTheDocument();
    const sandboxCard = (await screen.findAllByRole("button", { name: /remote agent/i })).find((element) =>
      element.className.includes("sandbox-card"),
    );
    if (!sandboxCard) {
      throw new Error("Expected remote sandbox card");
    }
    fireEvent.click(sandboxCard);
    expect(await screen.findByText("实时指标")).toBeInTheDocument();
    expect(screen.getByText("CPU")).toBeInTheDocument();
  });

  it("keeps live memory and disk telemetry inside the sandbox detail when present", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: null,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                },
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

    const providerCard = await screen.findByRole("button", { name: /daytona_selfhost/i });
    expect(within(providerCard).queryByText("RAM")).not.toBeInTheDocument();
    expect(within(providerCard).queryByText("Disk")).not.toBeInTheDocument();
    const sandboxCard = (await screen.findAllByRole("button", { name: /remote agent/i })).find((element) =>
      element.className.includes("sandbox-card"),
    );
    if (!sandboxCard) {
      throw new Error("Expected remote sandbox card");
    }
    fireEvent.click(sandboxCard);
    expect(await screen.findByText("实时指标")).toBeInTheDocument();
    expect(screen.getByText("RAM")).toBeInTheDocument();
    expect(screen.getByText("Disk")).toBeInTheDocument();
    expect(screen.getByText("1GB")).toBeInTheDocument();
    expect(screen.getByText("2GB")).toBeInTheDocument();
  });









  it("surfaces quota-only sandbox metrics instead of pretending they are fully missing", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: null,
                  memory: null,
                  memoryLimit: 1,
                  memoryNote: null,
                  disk: null,
                  diskLimit: 3,
                  diskNote: "disk usage not measurable inside container; showing quota only",
                  networkIn: null,
                  networkOut: null,
                  probeError: null,
                },
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

    const sandboxCard = await screen.findByRole("button", { name: /remote agent/i });
    expect(within(sandboxCard).getByText("RAM limit 1GB")).toBeInTheDocument();
    expect(within(sandboxCard).getByText("Disk limit 3GB")).toBeInTheDocument();
  });

  it("surfaces sandbox metric notes when only quota is available", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: null,
                  memory: null,
                  memoryLimit: 1,
                  memoryNote: null,
                  disk: null,
                  diskLimit: 3,
                  diskNote: "disk usage not measurable inside container; showing quota only",
                  networkIn: null,
                  networkOut: null,
                  probeError: null,
                },
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

    fireEvent.click(await screen.findByRole("button", { name: /remote agent/i }));
    expect(await screen.findByText("disk usage not measurable inside container; showing quota only")).toBeInTheDocument();
  });


  it("surfaces quota-only disk truth directly on the sandbox card", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: null,
                  memory: null,
                  memoryLimit: 1,
                  memoryNote: null,
                  disk: null,
                  diskLimit: 3,
                  diskNote: "disk usage not measurable inside container; showing quota only",
                  networkIn: null,
                  networkOut: null,
                  probeError: null,
                },
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

    const sandboxCard = await screen.findByRole("button", { name: /remote agent/i });
    expect(within(sandboxCard).getByText("仅有磁盘配额")).toBeInTheDocument();
  });

  it("speaks plainly when a running sandbox has not reported live metrics yet", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "lease-1:thread-1",
                leaseId: "lease-1",
                threadId: "thread-1",
                runtimeSessionId: "runtime-1",
                agentName: "Remote Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: null,
              },
            ],
          },
        ],
      },
      "/sandbox/lease-1/browse?path=%2F": {
        current_path: "/",
        parent_path: null,
        items: [],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    const sandboxCard = await screen.findByRole("button", { name: /remote agent/i });
    expect(within(sandboxCard).getByText("等待运行中的沙盒上报指标")).toBeInTheDocument();
  });










  it("keeps detached residue out of the resources summary strip", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 3,
        },
        triage: {
          summary: {
            detached_residue: 38,
          },
        },
        providers: [
          {
            id: "local",
            name: "local",
            description: "Local runtime",
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
              running: { used: 3, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "session-1",
                threadId: "thread-1",
                agentName: "Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
                runtimeSessionId: "runtime-1",
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

    expect(await screen.findByRole("heading", { name: "Resources" })).toBeInTheDocument();
    expect(screen.queryByText("38 历史残留")).not.toBeInTheDocument();
  });

  it("keeps orphan cleanup out of the resources summary strip", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 0,
        },
        triage: {
          summary: {
            orphan_cleanup: 3,
          },
        },
        providers: [
          {
            id: "local",
            name: "local",
            description: "Local runtime",
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
              running: { used: 0, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Resources" })).toBeInTheDocument();
    expect(screen.queryByText("3 Orphan Cleanup")).not.toBeInTheDocument();
  });

  it("keeps active drift out of the resources summary strip", async () => {
    mockRoutePayloads({
      "/resources": {
        summary: {
          snapshot_at: "2026-04-08T00:00:00Z",
          total_providers: 1,
          active_providers: 1,
          unavailable_providers: 0,
          running_sessions: 0,
        },
        triage: {
          summary: {
            active_drift: 2,
          },
        },
        providers: [
          {
            id: "local",
            name: "local",
            description: "Local runtime",
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
              running: { used: 0, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={["/resources"]}>
        <MonitorRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Resources" })).toBeInTheDocument();
    expect(screen.queryByText("2 Active Drift")).not.toBeInTheDocument();
  });

  it("surfaces detached residue in the provider detail overview", async () => {
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
            description: "Local runtime",
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
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "running-1",
                threadId: "thread-running",
                agentName: "Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
                runtimeSessionId: "runtime-1",
              },
              {
                id: "stopped-residue",
                threadId: "thread-stopped",
                agentName: "Agent 2",
                status: "stopped",
                startedAt: "2026-04-07T00:00:00Z",
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

    const detailLabel = (await screen.findAllByText("历史残留")).find((node) =>
      node.classList.contains("inline-metric__label"),
    );
    expect(detailLabel).toBeDefined();
    if (!detailLabel) {
      throw new Error("Expected provider detail detached residue metric");
    }
    expect(detailLabel.nextElementSibling).toHaveTextContent("1");
  });

  it("surfaces detached residue on the provider card footer", async () => {
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
            description: "Local runtime",
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
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "running-1",
                threadId: "thread-running",
                agentName: "Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
                runtimeSessionId: "runtime-1",
              },
              {
                id: "stopped-residue",
                threadId: "thread-stopped",
                agentName: "Agent 2",
                status: "stopped",
                startedAt: "2026-04-07T00:00:00Z",
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

    const providerCard = (await screen.findAllByRole("button", { name: /local/i })).find((element) =>
      element.className.includes("provider-card"),
    );
    expect(providerCard).toBeDefined();
    if (!providerCard) {
      throw new Error("Expected provider card");
    }
    expect(within(providerCard).getByText("1 历史残留")).toBeInTheDocument();
  });

  it("keeps provider card activity in one compact runtime-state line", async () => {
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
              hooks: true,
              mount: true,
            },
            telemetry: {
              running: { used: 1, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 4, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 10, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "running-1",
                leaseId: "lease-running",
                threadId: "thread-running",
                runtimeSessionId: "runtime-running",
                agentName: "Running Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                },
              },
              {
                id: "paused-1",
                leaseId: "lease-paused",
                threadId: "thread-paused",
                runtimeSessionId: "runtime-paused",
                agentName: "Paused Agent",
                status: "paused",
                startedAt: "2026-04-07T00:00:00Z",
                metrics: {
                  cpu: 0.5,
                  memory: 0.5,
                  memoryLimit: 1,
                  disk: 0.2,
                  diskLimit: 3,
                  networkIn: null,
                  networkOut: null,
                },
              },
              {
                id: "stopped-1",
                leaseId: "lease-stopped",
                threadId: "thread-stopped",
                agentName: "Stopped Agent",
                status: "stopped",
                startedAt: "2026-04-06T00:00:00Z",
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

    const providerCard = await screen.findByRole("button", { name: /daytona_selfhost/i });
    expect(within(providerCard).getByText("1 运行中 · 1 已暂停 · 1 已结束")).toBeInTheDocument();
  });

  it("keeps provider cards focused on one running-sandbox stat", async () => {
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
              hooks: true,
              mount: true,
            },
            telemetry: {
              running: { used: 1, limit: null, unit: "sandbox", source: "sandbox_db", freshness: "cached" },
              cpu: { used: 1.5, limit: null, unit: "%", source: "api", freshness: "live" },
              memory: { used: 1, limit: 4, unit: "GB", source: "api", freshness: "live" },
              disk: { used: 2, limit: 10, unit: "GB", source: "api", freshness: "live" },
            },
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
            },
            sessions: [
              {
                id: "running-1",
                leaseId: "lease-running",
                threadId: "thread-running",
                runtimeSessionId: "runtime-running",
                agentName: "Running Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                },
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

    const providerCard = await screen.findByRole("button", { name: /daytona_selfhost/i });
    expect(within(providerCard).getByText("运行中沙盒")).toBeInTheDocument();
    expect(within(providerCard).getByText("1")).toBeInTheDocument();
  });

  it("renders a truthful fallback avatar when monitor sessions have no avatar image", async () => {
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
            description: "Local runtime",
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
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "running-1",
                threadId: "thread-running",
                agentName: "Running Agent",
                avatarUrl: null,
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
                runtimeSessionId: "runtime-1",
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

    expect(await screen.findByLabelText("Running Agent avatar")).toHaveTextContent("RA");
  });

  it("surfaces detached residue directly on the sandbox card", async () => {
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
            description: "Local runtime",
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
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "running-1",
                leaseId: "lease-running",
                threadId: "thread-running",
                agentName: "Agent 1",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
                runtimeSessionId: "runtime-1",
              },
              {
                id: "stopped-residue",
                leaseId: "lease-residue",
                threadId: "thread-stopped",
                agentName: "Agent 2",
                status: "stopped",
                startedAt: "2026-04-07T00:00:00Z",
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

    fireEvent.click(await screen.findByRole("button", { name: "已结束 1" }));
    const sandboxCard = await screen.findByRole("button", { name: /agent 2/i });
    expect(within(sandboxCard).getByText("历史残留")).toBeInTheDocument();
  });

  it("lets the operator filter provider sandboxes by status", async () => {
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
            cardCpu: {
              used: null,
              limit: null,
              unit: "%",
              source: "unknown",
              freshness: "live",
              error: "CPU usage is per-sandbox, not a provider-level quota.",
            },
            sessions: [
              {
                id: "running-1",
                leaseId: "lease-running",
                threadId: "thread-running",
                runtimeSessionId: "runtime-running",
                agentName: "Running Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 1.5,
                  memory: 1,
                  memoryLimit: 4,
                  disk: 2,
                  diskLimit: 10,
                  networkIn: null,
                  networkOut: null,
                },
              },
              {
                id: "paused-1",
                leaseId: "lease-paused",
                threadId: "thread-paused",
                runtimeSessionId: "runtime-paused",
                agentName: "Paused Agent",
                status: "paused",
                startedAt: "2026-04-07T00:00:00Z",
                metrics: {
                  cpu: 0.5,
                  memory: 0.5,
                  memoryLimit: 1,
                  disk: 0.2,
                  diskLimit: 3,
                  networkIn: null,
                  networkOut: null,
                },
              },
              {
                id: "stopped-1",
                leaseId: "lease-stopped",
                threadId: "thread-stopped",
                agentName: "Stopped Agent",
                status: "stopped",
                startedAt: "2026-04-06T00:00:00Z",
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

    expect(await screen.findByText("Running Agent")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Paused Agent")).not.toBeInTheDocument();
      expect(screen.queryByText("Stopped Agent")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "已暂停 1" }));

    expect(screen.queryByText("Running Agent")).not.toBeInTheDocument();
    expect(screen.getByText("Paused Agent")).toBeInTheDocument();
    expect(screen.queryByText("Stopped Agent")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部 3" }));

    expect(screen.getByText("Running Agent")).toBeInTheDocument();
    expect(screen.getByText("Paused Agent")).toBeInTheDocument();
    expect(screen.getByText("Stopped Agent")).toBeInTheDocument();
  });

  it("defaults provider detail to live sandboxes before historical residue", async () => {
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
            description: "Local runtime",
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
              cpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
              memory: { used: 5, limit: 32, unit: "GB", source: "direct", freshness: "live" },
              disk: { used: 40, limit: 100, unit: "GB", source: "direct", freshness: "live" },
            },
            cardCpu: { used: 12, limit: null, unit: "%", source: "direct", freshness: "live" },
            sessions: [
              {
                id: "running-1",
                leaseId: "lease-running",
                threadId: "thread-running",
                runtimeSessionId: "runtime-1",
                agentName: "Running Agent",
                status: "running",
                startedAt: "2026-04-08T00:00:00Z",
                metrics: {
                  cpu: 12,
                  memory: 5,
                  memoryLimit: 32,
                  disk: 40,
                  diskLimit: 100,
                  networkIn: null,
                  networkOut: null,
                },
              },
              {
                id: "stopped-1",
                leaseId: "lease-stopped",
                threadId: "thread-stopped",
                agentName: "Stopped Agent",
                status: "stopped",
                startedAt: "2026-04-06T00:00:00Z",
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

    expect(await screen.findByText("Running Agent")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Stopped Agent")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "运行中 1" })).toHaveClass("provider-filter-chip--active");
  });
});
