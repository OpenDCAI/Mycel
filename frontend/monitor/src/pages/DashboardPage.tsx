import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

type DashboardPayload = {
  snapshot_at: string;
  infra: {
    providers_active: number;
    providers_unavailable: number;
    leases_total: number;
    leases_diverged: number;
    leases_orphan: number;
  };
  workload: {
    running_sessions: number;
    evaluations_running: number;
  };
  latest_evaluation: {
    headline: string;
  };
};

export default function DashboardPage() {
  const { data, error } = useMonitorData<DashboardPayload>("/dashboard");

  if (error) return <ErrorState title="Dashboard" error={error} />;
  if (!data) return <div>Loading...</div>;

  const surfaces = [
    { label: "Running Sessions", value: data.workload.running_sessions },
    { label: "Evaluations Running", value: data.workload.evaluations_running },
    { label: "Tracked Leases", value: data.infra.leases_total },
  ];

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p className="count">Snapshot: {data.snapshot_at}</p>
      <section className="surface-section">
        <h2>Runtime Surfaces</h2>
        <div className="surface-grid">
          {surfaces.map((surface) => (
            <article className="surface-card" key={surface.label}>
              <p className="surface-card__eyebrow">{surface.label}</p>
              <p className="surface-card__value">{surface.value}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="surface-section">
        <h2>Operator Attention</h2>
        <div className="surface-grid">
          <article className="surface-card" key="providers">
            <p className="surface-card__eyebrow">Provider Coverage</p>
            <p className="surface-card__body">
              {data.infra.providers_active} active providers, {data.infra.providers_unavailable} unavailable.
            </p>
          </article>
          <article className="surface-card" key="leases">
            <p className="surface-card__eyebrow">Lease Drift</p>
            <p className="surface-card__body">
              {data.infra.leases_diverged} diverged leases, {data.infra.leases_orphan} orphan leases.
            </p>
          </article>
          <article className="surface-card" key="evaluation">
            <p className="surface-card__eyebrow">Latest Evaluation</p>
            <p className="surface-card__body">
              {data.latest_evaluation.headline}
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
