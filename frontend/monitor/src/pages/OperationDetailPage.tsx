import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type OperationDetailPayload = {
  operation?: {
    operation_id?: string | null;
    kind?: string | null;
    status?: string | null;
    summary?: string | null;
    reason?: string | null;
  } | null;
  target?: {
    target_type?: string | null;
    target_id?: string | null;
    provider_id?: string | null;
    runtime_session_id?: string | null;
    thread_ids?: string[] | null;
  } | null;
  result_truth?: {
    lease_state_before?: string | null;
    lease_state_after?: string | null;
    runtime_state_after?: string | null;
    thread_state_after?: string[] | string | null;
  } | null;
  events?: Array<{
    at?: string | null;
    status?: string | null;
    message?: string | null;
  }> | null;
};

export default function OperationDetailPage() {
  const params = useParams<{ operationId: string }>();
  const operationId = params.operationId ?? "";
  const { data, error } = useMonitorData<OperationDetailPayload>(`/operations/${operationId}`);

  if (error) return <ErrorState title={`Operation ${operationId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const operation = data.operation ?? {};
  const target = data.target ?? {};
  const result = data.result_truth ?? {};
  const events = data.events ?? [];
  const description = operation.reason ?? operation.summary ?? "Monitor operation truth";

  return (
    <div className="page">
      <h1>{`Operation ${operation.operation_id ?? operationId}`}</h1>
      <p className="description">{description}</p>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Kind</strong>
            <span>{operation.kind ?? "-"}</span>
          </div>
          <div>
            <strong>Status</strong>
            <span>{operation.status ?? "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <span>
              <Link to="/leases">Leases</Link>
            </span>
          </div>
          <div>
            <strong>Lease</strong>
            <span>
              {target.target_type === "lease" && target.target_id ? (
                <Link to={`/leases/${target.target_id}`}>{target.target_id}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Runtime</strong>
            <span>
              {target.runtime_session_id ? (
                <Link to={`/runtimes/${target.runtime_session_id}`}>{target.runtime_session_id}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Provider</strong>
            <span>
              {target.provider_id ? <Link to={`/providers/${target.provider_id}`}>{target.provider_id}</Link> : "-"}
            </span>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <h2>Result Truth</h2>
        <div className="info-grid">
          <div>
            <strong>Lease before</strong>
            <span>{result.lease_state_before ?? "-"}</span>
          </div>
          <div>
            <strong>Lease after</strong>
            <span>{result.lease_state_after ?? "-"}</span>
          </div>
          <div>
            <strong>Runtime after</strong>
            <span>{result.runtime_state_after ?? "-"}</span>
          </div>
          <div>
            <strong>Reason</strong>
            <span>{operation.reason ?? "-"}</span>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <h2>Events</h2>
        <table>
          <thead>
            <tr>
              <th>At</th>
              <th>Status</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {events.length > 0 ? (
              events.map((event, index) => (
                <tr key={`${event.at ?? "missing-at"}-${index}`}>
                  <td className="mono">{event.at ?? "-"}</td>
                  <td>{event.status ?? "-"}</td>
                  <td>{event.message ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>No recorded events.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
