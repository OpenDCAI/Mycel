import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export type DashboardPayload = {
  snapshot_at: string;
  infra: {
    providers_active: number;
    providers_unavailable: number;
    sandboxes_total: number;
    sandboxes_diverged: number;
    sandboxes_orphan: number;
  };
  workload: {
    running_sessions: number;
    evaluations_running: number;
  };
  latest_evaluation: {
    headline: string;
  };
};

export function buildDashboardSurfaces(data: DashboardPayload) {
  return [
    { label: "Running Sandboxes", value: data.workload.running_sessions, to: "/resources" },
    { label: "Evaluations Running", value: data.workload.evaluations_running, to: "/evaluation" },
    { label: "Tracked Sandboxes", value: data.infra.sandboxes_total, to: "/sandboxes" },
  ];
}

export function buildDashboardAttentionLinks(data: DashboardPayload) {
  return [
    {
      label: "Provider Coverage",
      body: `${data.infra.providers_active} active providers, ${data.infra.providers_unavailable} unavailable.`,
      to: "/resources",
    },
    {
      label: "Sandbox Drift",
      body: `${data.infra.sandboxes_diverged} diverged sandboxes, ${data.infra.sandboxes_orphan} orphan sandboxes.`,
      to: "/sandboxes",
    },
    {
      label: "Latest Evaluation",
      body: data.latest_evaluation.headline,
      to: "/evaluation",
    },
  ];
}

export default function DashboardPage() {
  const { data, error } = useMonitorData<DashboardPayload>("/dashboard");

  if (error) return <ErrorState title="Dashboard" error={error} />;
  if (!data) return <div>Loading...</div>;

  const surfaces = buildDashboardSurfaces(data);
  const attentionLinks = buildDashboardAttentionLinks(data);

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p className="count">Snapshot: {data.snapshot_at}</p>
      <section className="surface-section">
        <h2>Runtime Surfaces</h2>
        <div className="surface-grid">
          {surfaces.map((surface) => (
            <Link className="surface-card" key={surface.label} to={surface.to}>
              <p className="surface-card__eyebrow">{surface.label}</p>
              <p className="surface-card__value">{surface.value}</p>
            </Link>
          ))}
        </div>
      </section>
      <section className="surface-section">
        <h2>Operator Attention</h2>
        <div className="surface-grid">
          {attentionLinks.map((item) => (
            <Link className="surface-card" key={item.label} to={item.to}>
              <p className="surface-card__eyebrow">{item.label}</p>
              <p className="surface-card__body">{item.body}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
