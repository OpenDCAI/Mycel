import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

type LeasesPayload = {
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
    lease_id: string;
    provider: string;
    instance_id?: string | null;
    thread: {
      thread_id?: string | null;
    };
    state_badge: Record<string, unknown>;
    updated_ago?: string | null;
    error?: string | null;
  }>;
};

export default function LeasesPage() {
  const { data, error } = useMonitorData<LeasesPayload>("/leases");

  if (error) return <ErrorState title="Leases" error={error} />;
  if (!data) return <div>Loading...</div>;

  const triage = data.triage?.summary ?? {};
  const triageCards = [
    { label: "Active Drift", value: triage.active_drift ?? 0 },
    { label: "Detached Residue", value: triage.detached_residue ?? 0 },
    { label: "Orphan Cleanup", value: triage.orphan_cleanup ?? 0 },
    { label: "Healthy Capacity", value: triage.healthy_capacity ?? 0 },
  ];

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
      <section className="surface-section">
        <h2>Lease Triage</h2>
        <div className="surface-grid">
          {triageCards.map((card) => (
            <article className="surface-card" key={card.label}>
              <p className="surface-card__eyebrow">{card.label}</p>
              <p className="surface-card__value">{card.value}</p>
            </article>
          ))}
        </div>
      </section>
      <h2>Raw Lease Table</h2>
      <table>
        <thead>
          <tr>
            <th>Lease ID</th>
            <th>Provider</th>
            <th>Instance ID</th>
            <th>Thread</th>
            <th>State</th>
            <th>Updated</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.lease_id}>
              <td className="mono">
                <Link to={`/leases/${item.lease_id}`}>{item.lease_id}</Link>
              </td>
              <td>{item.provider ? <Link to={`/providers/${item.provider}`}>{item.provider}</Link> : "-"}</td>
              <td className="mono">
                {item.instance_id ? <Link to={`/runtimes/${item.instance_id}`}>{item.instance_id.slice(0, 12)}</Link> : "-"}
              </td>
              <td>
                {item.thread.thread_id ? (
                  <Link className="mono" to={`/threads/${item.thread.thread_id}`}>
                    {item.thread.thread_id.slice(0, 8)}
                  </Link>
                ) : (
                  <span className="orphan">orphan</span>
                )}
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
