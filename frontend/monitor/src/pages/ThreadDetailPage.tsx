import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type ThreadDetailPayload = {
  thread?: {
    id?: string | null;
    thread_id?: string | null;
    title?: string | null;
    status?: string | null;
  } | null;
  owner?: {
    user_id?: string | null;
    display_name?: string | null;
    email?: string | null;
  } | null;
  summary?: {
    provider_name?: string | null;
    lease_id?: string | null;
    current_instance_id?: string | null;
    desired_state?: string | null;
    observed_state?: string | null;
  } | null;
  sessions?: Array<{
    chat_session_id?: string | null;
    status?: string | null;
  }> | null;
};

function resolveThreadId(thread: ThreadDetailPayload["thread"], fallback: string): string {
  return String(thread?.thread_id || thread?.id || fallback);
}

export default function ThreadDetailPage() {
  const params = useParams<{ threadId: string }>();
  const threadId = params.threadId ?? "";
  const { data, error } = useMonitorData<ThreadDetailPayload>(`/threads/${threadId}`);

  if (error) return <ErrorState title={`Thread ${threadId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const summary = data.summary ?? {};
  const owner = data.owner ?? {};
  const resolvedThreadId = resolveThreadId(data.thread, threadId);
  const sessions = data.sessions ?? [];

  return (
    <div className="page">
      <h1>{`Thread ${resolvedThreadId}`}</h1>
      <p className="description">
        {data.thread?.title ?? "Operator thread truth"} · {data.thread?.status ?? "-"}
      </p>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Owner</strong>
            <span>{owner.display_name ?? owner.email ?? owner.user_id ?? "-"}</span>
          </div>
          <div>
            <strong>Provider</strong>
            <span>
              {summary.provider_name ? (
                <Link to={`/providers/${summary.provider_name}`}>{summary.provider_name}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Lease</strong>
            <span>
              {summary.lease_id ? <Link to={`/leases/${summary.lease_id}`}>{summary.lease_id}</Link> : "-"}
            </span>
          </div>
          <div>
            <strong>Runtime</strong>
            <span>
              {summary.current_instance_id ? (
                <Link to={`/runtimes/${summary.current_instance_id}`}>{summary.current_instance_id}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Leases</strong>
            <span>
              <Link to="/leases">Back to leases</Link>
            </span>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <h2>Sessions</h2>
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sessions.length > 0 ? (
              sessions.map((session) => (
                <tr key={session.chat_session_id ?? "missing-session"}>
                  <td className="mono">{session.chat_session_id ?? "-"}</td>
                  <td>{session.status ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={2}>No recorded sessions.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
