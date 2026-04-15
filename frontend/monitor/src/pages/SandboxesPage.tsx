import React from "react";
import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export type SandboxesPayload = {
  title: string;
  count: number;
  triage?: {
    summary?: {
      active_drift?: number;
      detached_residue?: number;
      orphan_cleanup?: number;
      healthy_capacity?: number;
      total?: number;
    };
  };
  items: Array<{
    sandbox_id: string;
    provider: string;
    instance_id?: string | null;
    triage?: {
      category?: string | null;
      title?: string | null;
    };
    thread: {
      thread_id?: string | null;
    };
    state_badge: Record<string, unknown>;
    updated_ago?: string | null;
    error?: string | null;
  }>;
};

type TriageFilter = "all" | "active_drift" | "detached_residue" | "orphan_cleanup" | "healthy_capacity";

export function buildSandboxWorkbenchShell(data: SandboxesPayload) {
  const triage = data.triage?.summary ?? {};
  const triageCards = [
    { key: "active_drift" as const, label: "Active Drift", value: triage.active_drift ?? 0 },
    { key: "detached_residue" as const, label: "Detached Residue", value: triage.detached_residue ?? 0 },
    { key: "orphan_cleanup" as const, label: "Orphan Cleanup", value: triage.orphan_cleanup ?? 0 },
    { key: "healthy_capacity" as const, label: "Healthy Capacity", value: triage.healthy_capacity ?? 0 },
  ] satisfies Array<{ key: TriageFilter; label: string; value: number }>;

  return {
    triageTitle: "Sandbox Triage",
    workbenchTitle: "Sandbox Workbench",
    triageCards,
    rows: data.items.map((item) => ({
      ...item,
      href: `/sandboxes/${item.sandbox_id}`,
    })),
  };
}

export default function SandboxesPage() {
  const { data, error } = useMonitorData<SandboxesPayload>("/sandboxes");
  const [selectedFilter, setSelectedFilter] = React.useState<TriageFilter>("all");

  if (error) return <ErrorState title="Sandboxes" error={error} />;
  if (!data) return <div>Loading...</div>;

  const shell = buildSandboxWorkbenchShell(data);
  const visibleRows =
    selectedFilter === "all"
      ? shell.rows
      : shell.rows.filter((item) => (item.triage?.category ?? "") === selectedFilter);
  const activeCard = shell.triageCards.find((card) => card.key === selectedFilter);

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
      <section className="surface-section">
        <h2>{shell.triageTitle}</h2>
        <div className="surface-grid">
          <button
            type="button"
            className={`surface-card lease-triage-card ${selectedFilter === "all" ? "lease-triage-card--active" : ""}`}
            onClick={() => setSelectedFilter("all")}
          >
            <p className="surface-card__eyebrow">All Triage</p>
            <p className="surface-card__value">{data.count}</p>
          </button>
          {shell.triageCards.map((card) => (
            <button
              type="button"
              className={`surface-card lease-triage-card ${selectedFilter === card.key ? "lease-triage-card--active" : ""}`}
              key={card.label}
              onClick={() => setSelectedFilter(card.key)}
            >
              <p className="surface-card__eyebrow">{card.label}</p>
              <p className="surface-card__value">{card.value}</p>
            </button>
          ))}
        </div>
      </section>
      <div className="leases-workbench-header">
        <div>
          <h2>{shell.workbenchTitle}</h2>
          <p className="description">
            {activeCard ? `Showing ${activeCard.label}` : "Showing All Triage"}
          </p>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Sandbox ID</th>
            <th>Topology</th>
            <th>Triage</th>
            <th>State</th>
            <th>Updated</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((item) => (
            <tr key={item.sandbox_id}>
              <td className="mono">
                <Link to={item.href}>{item.sandbox_id}</Link>
              </td>
              <td>
                <div className="lease-topology">
                  <div className="lease-topology__row">
                    <span className="lease-topology__label">provider</span>
                    {item.provider ? <Link to={`/providers/${item.provider}`}>{item.provider}</Link> : <span>-</span>}
                  </div>
                  <div className="lease-topology__row">
                    <span className="lease-topology__label">runtime</span>
                    {item.instance_id ? (
                      <Link className="mono" to={`/runtimes/${item.instance_id}`}>
                        {item.instance_id.slice(0, 12)}
                      </Link>
                    ) : (
                      <span>-</span>
                    )}
                  </div>
                  <div className="lease-topology__row">
                    <span className="lease-topology__label">thread</span>
                    {item.thread.thread_id ? (
                      <Link className="mono" to={`/threads/${item.thread.thread_id}`}>
                        {item.thread.thread_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="orphan">orphan</span>
                    )}
                  </div>
                </div>
              </td>
              <td>
                <span className="lease-triage-chip">{item.triage?.title ?? "-"}</span>
              </td>
              <td>
                <StateBadge badge={item.state_badge} />
              </td>
              <td>{item.updated_ago}</td>
              <td className="error">{item.error || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
