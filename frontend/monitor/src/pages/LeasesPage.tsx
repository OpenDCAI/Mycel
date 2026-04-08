import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export default function LeasesPage() {
  const { data, error } = useMonitorData<any>("/leases");

  if (error) return <ErrorState title="Leases" error={error} />;
  if (!data) return <div>Loading...</div>;

  const triage = data.triage ?? {};
  const triageCards = [
    { label: "Active", value: triage.active ?? 0 },
    { label: "Residue", value: triage.residue ?? 0 },
    { label: "Total", value: data.count ?? 0 },
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
              <td>
                <Link to={item.lease_url}>{item.lease_id}</Link>
              </td>
              <td>{item.provider}</td>
              <td className="mono">{item.instance_id?.slice(0, 12) || "-"}</td>
              <td>
                {item.thread.thread_id ? (
                  <Link to={item.thread.thread_url}>{item.thread.thread_id.slice(0, 8)}</Link>
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
