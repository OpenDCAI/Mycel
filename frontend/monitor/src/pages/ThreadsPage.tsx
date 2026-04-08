import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export default function ThreadsPage() {
  const { data, error } = useMonitorData<any>("/threads");

  if (error) return <ErrorState title="Threads" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <h1>{data.title}</h1>
      <p className="count">Total: {data.count}</p>
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
