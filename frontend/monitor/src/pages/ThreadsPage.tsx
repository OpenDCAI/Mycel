import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export default function ThreadsPage() {
  const { data, error } = useMonitorData<any>("/threads");

  if (error) return <ErrorState title="Threads" error={error} />;
  if (!data) return <div>Loading...</div>;

  const items = data.items ?? [];
  const threadCards = [
    { label: "Active Threads", value: data.count ?? items.length },
    {
      label: "Attached Leases",
      value: items.filter((item: any) => item.lease?.lease_id).length,
    },
    {
      label: "Pressure Sessions",
      value: items.reduce((total: number, item: any) => total + (item.session_count ?? 0), 0),
    },
  ];

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
      <section className="surface-section">
        <h2>Thread Pressure</h2>
        <div className="surface-grid">
          {threadCards.map((card) => (
            <article className="surface-card" key={card.label}>
              <p className="surface-card__eyebrow">{card.label}</p>
              <p className="surface-card__value">{card.value}</p>
            </article>
          ))}
        </div>
      </section>
      <h2>Raw Thread Table</h2>
      <table>
        <thead>
          <tr>
            <th>Thread ID</th>
            <th>Sessions</th>
            <th>Last Active</th>
            <th>Lease</th>
            <th>Provider</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.thread_id}>
              <td>
                <Link to={item.thread_url}>{item.thread_id.slice(0, 8)}</Link>
              </td>
              <td>{item.session_count}</td>
              <td>{item.last_active_ago}</td>
              <td>
                {item.lease.lease_id ? <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link> : "-"}
              </td>
              <td>{item.lease.provider || "-"}</td>
              <td>
                <StateBadge badge={item.state_badge} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
