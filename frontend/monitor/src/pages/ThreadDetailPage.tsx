import { Link, useParams } from "react-router-dom";

import Breadcrumb from "../components/Breadcrumb";
import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export default function ThreadDetailPage() {
  const { threadId } = useParams();
  const { data, error } = useMonitorData<any>(`/thread/${threadId}`);

  if (error) return <ErrorState title="Thread detail" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Thread: {data.thread_id.slice(0, 8)}</h1>

      <section>
        <h2>
          {data.sessions.title} ({data.sessions.count})
        </h2>
        <table>
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Status</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Lease</th>
              <th>State</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {data.sessions.items.map((s: any) => (
              <tr key={s.session_id}>
                <td>
                  <Link to={s.session_url}>{s.session_id.slice(0, 8)}</Link>
                </td>
                <td>{s.status}</td>
                <td>{s.started_ago}</td>
                <td>{s.ended_ago || "-"}</td>
                <td>{s.lease.lease_id ? <Link to={s.lease.lease_url}>{s.lease.lease_id}</Link> : "-"}</td>
                <td>
                  <StateBadge badge={s.state_badge} />
                </td>
                <td className="error">{s.error || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{data.related_leases.title}</h2>
        <ul>
          {data.related_leases.items.map((l: any) => (
            <li key={l.lease_id}>
              <Link to={l.lease_url}>{l.lease_id}</Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
