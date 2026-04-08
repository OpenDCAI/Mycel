import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export default function EventsPage() {
  const { data, error } = useMonitorData<any>("/events?limit=100");

  if (error) return <ErrorState title="Events" error={error} />;
  if (!data) return <div>Loading...</div>;

  const items = data.items ?? [];
  const signalCards = [
    { label: "Recent Events", value: data.count ?? items.length },
    {
      label: "Errors",
      value: items.filter((item: any) => item.error).length,
    },
    {
      label: "Lease-linked",
      value: items.filter((item: any) => item.lease?.lease_id).length,
    },
  ];

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <section className="surface-section">
        <h2>Signal Feed</h2>
        <div className="surface-grid">
          {signalCards.map((card) => (
            <article className="surface-card" key={card.label}>
              <p className="surface-card__eyebrow">{card.label}</p>
              <p className="surface-card__value">{card.value}</p>
            </article>
          ))}
        </div>
      </section>
      <h2>Raw Event Table</h2>
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Source</th>
            <th>Provider</th>
            <th>Lease</th>
            <th>Error</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.event_id}>
              <td>
                <Link to={item.event_url}>{item.event_type}</Link>
              </td>
              <td>{item.source}</td>
              <td>{item.provider}</td>
              <td>{item.lease.lease_id ? <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link> : "-"}</td>
              <td className="error">{item.error || "-"}</td>
              <td>{item.created_ago}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
