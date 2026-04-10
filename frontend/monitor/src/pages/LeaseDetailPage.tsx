import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";

type LeaseDetailPayload = {
  lease: {
    lease_id: string;
    provider_name?: string | null;
    desired_state?: string | null;
    observed_state?: string | null;
    updated_at?: string | null;
    updated_ago?: string | null;
    last_error?: string | null;
    badge?: Record<string, unknown>;
  };
  triage?: {
    category?: string | null;
    title?: string | null;
    description?: string | null;
    tone?: string | null;
  } | null;
  provider?: {
    id?: string | null;
    name?: string | null;
  } | null;
  runtime?: {
    runtime_session_id?: string | null;
  } | null;
  threads?: Array<{
    thread_id?: string | null;
  }> | null;
  sessions?: Array<{
    chat_session_id?: string | null;
    thread_id?: string | null;
    status?: string | null;
  }> | null;
};

export default function LeaseDetailPage() {
  const params = useParams<{ leaseId: string }>();
  const leaseId = params.leaseId ?? "";
  const { data, error } = useMonitorData<LeaseDetailPayload>(`/leases/${leaseId}`);

  if (error) return <ErrorState title={`Lease ${leaseId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const threads = data.threads ?? [];
  const sessions = data.sessions ?? [];

  return (
    <div className="page">
      <h1>{`Lease ${data.lease.lease_id}`}</h1>
      <p className="description">
        Provider {data.provider?.name ?? data.lease.provider_name ?? "-"} · observed {data.lease.observed_state ?? "-"} · desired{" "}
        {data.lease.desired_state ?? "-"}
      </p>
      <section className="surface-section">
        <h2>Operator Truth</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">State</p>
            <StateBadge badge={data.lease.badge ?? { text: data.lease.observed_state ?? "-" }} />
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Triage</p>
            <p className="surface-card__value">{data.triage?.title ?? "-"}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Runtime</p>
            <p className="surface-card__value mono">{data.runtime?.runtime_session_id ?? "-"}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Provider</strong>
            <span>{data.provider?.name ?? data.lease.provider_name ?? "-"}</span>
          </div>
          <div>
            <strong>Updated</strong>
            <span>{data.lease.updated_ago ?? data.lease.updated_at ?? "-"}</span>
          </div>
          <div>
            <strong>Lease list</strong>
            <span>
              <Link to="/leases">Back to leases</Link>
            </span>
          </div>
          <div>
            <strong>Last error</strong>
            <span>{data.lease.last_error ?? "-"}</span>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <h2>Threads</h2>
        <table>
          <thead>
            <tr>
              <th>Thread</th>
            </tr>
          </thead>
          <tbody>
            {threads.length > 0 ? (
              threads.map((thread) => (
                <tr key={thread.thread_id ?? "missing-thread"}>
                  <td className="mono">{thread.thread_id ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td>No related threads.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      <section className="surface-section">
        <h2>Sessions</h2>
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Thread</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sessions.length > 0 ? (
              sessions.map((session) => (
                <tr key={session.chat_session_id ?? "missing-session"}>
                  <td className="mono">{session.chat_session_id ?? "-"}</td>
                  <td className="mono">{session.thread_id ?? "-"}</td>
                  <td>{session.status ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>No recorded sessions.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
