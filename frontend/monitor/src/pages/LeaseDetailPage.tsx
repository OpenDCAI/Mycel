import { Link, useParams } from "react-router-dom";

import Breadcrumb from "../components/Breadcrumb";
import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";
import { useMonitorData } from "../app/fetch";

export default function LeaseDetailPage() {
  const { leaseId } = useParams();
  const { data, error } = useMonitorData<any>(`/lease/${leaseId}`);

  if (error) return <ErrorState title="Lease detail" error={error} />;
  if (!data) return <div>Loading...</div>;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Lease: {data.lease_id}</h1>

      <section className="info-grid">
        <div>
          <strong>Provider:</strong> {data.info.provider}
        </div>
        <div>
          <strong>Instance ID:</strong> <span className="mono">{data.info.instance_id || "-"}</span>
        </div>
        <div>
          <strong>Created:</strong> {data.info.created_ago}
        </div>
        <div>
          <strong>Updated:</strong> {data.info.updated_ago}
        </div>
      </section>

      <section>
        <h2>State</h2>
        <div className="state-info">
          <div>
            <strong>Desired:</strong> {data.state.desired}
          </div>
          <div>
            <strong>Observed:</strong> {data.state.observed}
          </div>
          <div>
            <strong>Status:</strong> <StateBadge badge={data.state} />
          </div>
          {data.state.error && (
            <div className="error">
              <strong>Error:</strong> {data.state.error}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2>{data.related_threads.title}</h2>
        <ul>
          {data.related_threads.items.map((t: any) => (
            <li key={t.thread_id}>
              <Link to={t.thread_url}>{t.thread_id}</Link>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>
          {data.lease_events.title} ({data.lease_events.count})
        </h2>
        <table>
          <thead>
            <tr>
              <th>Event ID</th>
              <th>Type</th>
              <th>Source</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {data.lease_events.items.map((e: any) => (
              <tr key={e.event_id}>
                <td>
                  <Link to={e.event_url}>{e.event_id}</Link>
                </td>
                <td>{e.event_type}</td>
                <td>{e.source}</td>
                <td>{e.created_ago}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
