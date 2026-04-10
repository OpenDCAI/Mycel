import React from "react";
import { Link, useParams } from "react-router-dom";

import { postMonitorData, useMonitorData } from "../app/fetch";
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
  cleanup?: {
    allowed?: boolean;
    recommended_action?: string | null;
    reason?: string | null;
    operation?: {
      operation_id?: string | null;
      kind?: string | null;
      status?: string | null;
      summary?: string | null;
    } | null;
    recent_operations?: Array<{
      operation_id?: string | null;
      kind?: string | null;
      status?: string | null;
      summary?: string | null;
    }> | null;
  } | null;
};

type LeaseCleanupActionPayload = {
  accepted: boolean;
  message?: string | null;
  operation?: {
    operation_id?: string | null;
    kind?: string | null;
    target_type?: string | null;
    target_id?: string | null;
    status?: string | null;
    summary?: string | null;
  } | null;
  current_truth?: {
    lease_id?: string | null;
    triage_category?: string | null;
  } | null;
};

export default function LeaseDetailPage() {
  const params = useParams<{ leaseId: string }>();
  const leaseId = params.leaseId ?? "";
  const { data, error } = useMonitorData<LeaseDetailPayload>(`/leases/${leaseId}`);
  const [leaseData, setLeaseData] = React.useState<LeaseDetailPayload | null>(null);
  const [cleanupMessage, setCleanupMessage] = React.useState<string | null>(null);
  const [cleanupPending, setCleanupPending] = React.useState(false);

  React.useEffect(() => {
    if (data) {
      setLeaseData(data);
      setCleanupMessage(null);
      setCleanupPending(false);
    }
  }, [data]);

  if (error) return <ErrorState title={`Lease ${leaseId}`} error={error} />;
  if (!leaseData) return <div>Loading...</div>;

  const threads = leaseData.threads ?? [];
  const sessions = leaseData.sessions ?? [];
  const cleanup = leaseData.cleanup ?? {};
  const recentOperations = (cleanup.recent_operations ?? []).filter(
    (operation) => operation.operation_id !== cleanup.operation?.operation_id,
  );

  async function startCleanup() {
    setCleanupPending(true);
    try {
      const result = await postMonitorData<LeaseCleanupActionPayload>(`/leases/${leaseId}/cleanup`);
      setCleanupMessage(result.message ?? null);
      setLeaseData((current) => {
        if (!current) return current;
        const nextOperation = result.operation
          ? {
              operation_id: result.operation.operation_id ?? null,
              kind: result.operation.kind ?? null,
              status: result.operation.status ?? null,
              summary: result.operation.summary ?? result.message ?? null,
            }
          : null;
        const nextRecent = nextOperation
          ? [
              nextOperation,
              ...(current.cleanup?.recent_operations ?? []).filter(
                (item) => item.operation_id !== nextOperation.operation_id,
              ),
            ]
          : current.cleanup?.recent_operations ?? [];
        return {
          ...current,
          cleanup: {
            ...current.cleanup,
            operation: nextOperation,
            recent_operations: nextRecent,
          },
        };
      });
    } finally {
      setCleanupPending(false);
    }
  }

  return (
    <div className="page">
      <h1>{`Lease ${leaseData.lease.lease_id}`}</h1>
      <p className="description">{leaseData.triage?.description ?? "Lease operator truth"}</p>
      <section className="surface-section">
        <h2>Operator Truth</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">State</p>
            <StateBadge badge={leaseData.lease.badge ?? { text: leaseData.lease.observed_state ?? "-" }} />
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Triage</p>
            <p className="surface-card__value">{leaseData.triage?.title ?? "-"}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Cleanup</h2>
        <div className="info-grid">
          <div>
            <strong>Eligibility</strong>
            <span>{cleanup.allowed ? "Ready for managed cleanup" : "Cleanup blocked"}</span>
          </div>
          <div>
            <strong>Recommended action</strong>
            <span>{cleanup.recommended_action ?? "-"}</span>
          </div>
          <div>
            <strong>Latest operation</strong>
            <span>
              {cleanup.operation?.operation_id ? (
                <Link to={`/operations/${cleanup.operation.operation_id}`}>{cleanup.operation.operation_id}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Status</strong>
            <span>{cleanup.operation?.status ?? "-"}</span>
          </div>
          <div>
            <strong>Reason</strong>
            <span>{cleanup.reason ?? "-"}</span>
          </div>
          <div>
            <strong>Action</strong>
            <span>
              <button
                type="button"
                className="monitor-action-button"
                disabled={!cleanup.allowed || cleanupPending}
                onClick={() => void startCleanup()}
              >
                Start lease cleanup
              </button>
            </span>
          </div>
        </div>
        {cleanupMessage ? <p className="description">{cleanupMessage}</p> : null}
        <table>
          <thead>
            <tr>
              <th>Operation</th>
              <th>Status</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {recentOperations.length > 0 ? (
              recentOperations.map((operation) => (
                <tr key={operation.operation_id ?? "missing-operation"}>
                  <td className="mono">
                    {operation.operation_id ? (
                      <Link to={`/operations/${operation.operation_id}`}>{operation.operation_id}</Link>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{operation.status ?? "-"}</td>
                  <td>{operation.summary ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>No recorded cleanup operations.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Provider</strong>
            <span>
              {leaseData.provider?.id ? (
                <Link to={`/providers/${leaseData.provider.id}`}>{leaseData.provider.name ?? leaseData.provider.id}</Link>
              ) : (
                leaseData.provider?.name ?? leaseData.lease.provider_name ?? "-"
              )}
            </span>
          </div>
          <div>
            <strong>Updated</strong>
            <span>{leaseData.lease.updated_ago ?? leaseData.lease.updated_at ?? "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <span>
              <Link to="/leases">Leases</Link>
            </span>
          </div>
          <div>
            <strong>Last error</strong>
            <span>{leaseData.lease.last_error ?? "-"}</span>
          </div>
          <div>
            <strong>Runtime</strong>
            <span>
              {leaseData.runtime?.runtime_session_id ? (
                <Link to={`/runtimes/${leaseData.runtime.runtime_session_id}`}>{leaseData.runtime.runtime_session_id}</Link>
              ) : (
                "-"
              )}
            </span>
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
                  <td className="mono">
                    {thread.thread_id ? <Link to={`/threads/${thread.thread_id}`}>{thread.thread_id}</Link> : "-"}
                  </td>
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
