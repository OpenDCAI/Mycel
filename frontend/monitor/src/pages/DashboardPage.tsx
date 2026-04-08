import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export default function DashboardPage() {
  const { data, error } = useMonitorData<any>("/dashboard");

  if (error) return <ErrorState title="Dashboard" error={error} />;
  if (!data) return <div>Loading...</div>;

  const summary = data.summary ?? {};
  const surfaces = [
    { label: "Active Threads", value: summary.active_threads ?? 0 },
    { label: "Active Leases", value: summary.active_leases ?? 0 },
    { label: "Resources Ready", value: summary.resources_ready ?? 0 },
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
          <article className="surface-card" key="coverage">
            <p className="surface-card__eyebrow">Coverage</p>
            <p className="surface-card__body">
              {summary.resources_ready ?? 0} resource surfaces reporting against {summary.active_leases ?? 0} active
              leases.
            </p>
          </article>
          <article className="surface-card" key="focus">
            <p className="surface-card__eyebrow">Immediate Focus</p>
            <p className="surface-card__body">
              Check leases that drift away from running state before moving deeper into thread or resource drilldown.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
