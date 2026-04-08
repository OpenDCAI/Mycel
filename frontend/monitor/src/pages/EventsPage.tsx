import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

export default function EventsPage() {
  const { data, error } = useMonitorData<any>("/events?limit=100");

  if (error) return <ErrorState title="Events" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
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
