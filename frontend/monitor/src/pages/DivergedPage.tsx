import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export default function DivergedPage() {
  const { data, error } = useMonitorData<any>("/diverged");

  if (error) return <ErrorState title="Diverged leases" error={error} />;
  if (!data) return <div>Loading...</div>;

  const items = data.items ?? [];
  const triageCards = [
    { label: "Total Diverged", value: data.count ?? items.length },
    {
      label: "Critical",
      value: items.filter((item: any) => item.state_badge?.color === "red").length,
    },
    {
      label: "Orphans",
      value: items.filter((item: any) => !item.thread?.thread_id).length,
    },
  ];

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <section className="surface-section">
        <h2>Drift Triage</h2>
        <div className="surface-grid">
          {triageCards.map((card) => (
            <article className="surface-card" key={card.label}>
              <p className="surface-card__eyebrow">{card.label}</p>
              <p className="surface-card__value">{card.value}</p>
            </article>
          ))}
        </div>
      </section>
      <h2>Raw Divergence Table</h2>
      <table>
        <thead>
          <tr>
            <th>Lease ID</th>
            <th>Provider</th>
            <th>Thread</th>
            <th>Desired</th>
            <th>Observed</th>
            <th>Hours Diverged</th>
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
              <td>
                {item.thread.thread_id ? (
                  <Link to={item.thread.thread_url}>{item.thread.thread_id.slice(0, 8)}</Link>
                ) : (
                  <span className="orphan">orphan</span>
                )}
              </td>
              <td>{item.state_badge.desired}</td>
              <td>{item.state_badge.observed}</td>
              <td className={item.state_badge.color === "red" ? "error" : ""}>{item.state_badge.hours_diverged}h</td>
              <td className="error">{item.error || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
