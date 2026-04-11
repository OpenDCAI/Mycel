import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchAPI, postMonitorData, type MonitorFetchError, useMonitorData } from "../app/fetch";
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
};

const CLEANUP_STATUS_CLASS_BY_STATUS: Record<string, string> = {
  pending: "cleanup-status cleanup-status--warning",
  running: "cleanup-status cleanup-status--warning",
  succeeded: "cleanup-status cleanup-status--ok",
  failed: "cleanup-status cleanup-status--danger",
  rejected: "cleanup-status cleanup-status--danger",
};

export default function LeaseDetailPage() {
  const params = useParams<{ leaseId: string }>();
  const leaseId = params.leaseId ?? "";
  const navigate = useNavigate();
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
  const latestSession = sessions[0] ?? null;
  const cleanupDecision = cleanup.allowed ? "Managed cleanup ready" : "Cleanup blocked";
  const cleanupActionSummary = cleanup.recommended_action ?? "No managed action";
  const cleanupActionHint = cleanup.allowed
    ? "This lease can enter the managed destroy flow."
    : "This lease cannot enter the managed flow until its state changes.";
  const cleanupOperationStatus = cleanup.operation?.status ?? "idle";
  const cleanupOperationSummary = cleanup.operation?.summary ?? "No active cleanup operation.";
  const cleanupOperationClass = CLEANUP_STATUS_CLASS_BY_STATUS[cleanupOperationStatus] ?? "cleanup-status cleanup-status--muted";
  const cleanupFeedbackMessage =
    cleanupMessage && cleanupMessage !== cleanupOperationSummary ? cleanupMessage : null;

  async function startCleanup() {
    setCleanupPending(true);
    try {
      const result = await postMonitorData<LeaseCleanupActionPayload>(`/leases/${leaseId}/cleanup`);
      setCleanupMessage(result.message ?? null);
      if (result.accepted && result.operation?.status === "succeeded" && result.operation.operation_id) {
        navigate(`/operations/${result.operation.operation_id}`);
        return;
      }
      try {
        const refreshed = await fetchAPI<LeaseDetailPayload>(`/leases/${leaseId}`);
        setLeaseData(refreshed);
      } catch (err: unknown) {
        const fetchError = err as MonitorFetchError;
        if (fetchError?.status === 404 && result.operation?.operation_id) {
          navigate(`/operations/${result.operation.operation_id}`);
          return;
        }
        throw err;
      }
    } finally {
      setCleanupPending(false);
    }
  }

  return (
    <div className="page">
      <h1>{`Lease ${leaseData.lease.lease_id}`}</h1>
      <p className="description">{leaseData.triage?.description ?? "Lease state and cleanup readiness."}</p>
      <section className="surface-section">
        <h2>State</h2>
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
        <p className="description">{cleanup.reason ?? "Managed cleanup readiness for this lease."}</p>
        <div className="surface-grid cleanup-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Decision</p>
            <p className="surface-card__value surface-card__value--compact">{cleanupDecision}</p>
            <p className="surface-card__body">{cleanupActionSummary}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Current Operation</p>
            <div className="cleanup-current-op">
              <span className={cleanupOperationClass}>{cleanupOperationStatus}</span>
              {cleanup.operation?.operation_id ? (
                <Link to={`/operations/${cleanup.operation.operation_id}`} className="cleanup-operation-link">
                  {cleanup.operation.operation_id}
                </Link>
              ) : null}
            </div>
            <p className="surface-card__body">{cleanupOperationSummary}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Action Lane</p>
            <button
              type="button"
              className="monitor-action-button"
              disabled={!cleanup.allowed || cleanupPending}
              onClick={() => void startCleanup()}
            >
              Start lease cleanup
            </button>
            <p className="surface-card__body">{cleanupActionHint}</p>
          </article>
        </div>
        {cleanupFeedbackMessage ? <p className="description">{cleanupFeedbackMessage}</p> : null}
        <div className="cleanup-ledger">
          <h3>Recent Operations</h3>
          {recentOperations.length > 0 ? (
            <div className="cleanup-ledger__list">
              {recentOperations.map((operation) => {
                const operationStatus = operation.status ?? "unknown";
                const operationClass =
                  CLEANUP_STATUS_CLASS_BY_STATUS[operationStatus] ?? "cleanup-status cleanup-status--muted";
                return (
                  <article className="cleanup-ledger__item" key={operation.operation_id ?? "missing-operation"}>
                    <div className="cleanup-ledger__header">
                      <span className={operationClass}>{operationStatus}</span>
                      {operation.operation_id ? (
                        <Link to={`/operations/${operation.operation_id}`} className="cleanup-operation-link mono">
                          {operation.operation_id}
                        </Link>
                      ) : (
                        <span className="mono">-</span>
                      )}
                    </div>
                    <p className="cleanup-ledger__summary">{operation.summary ?? "-"}</p>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="cleanup-ledger__empty">No recorded cleanup operations.</p>
          )}
        </div>
      </section>
      <section className="surface-section">
        <h2>Relations</h2>
        <h3>Object Links</h3>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Provider</p>
            <p className="surface-card__value surface-card__value--compact">
              {leaseData.provider?.id ? (
                <Link to={`/providers/${leaseData.provider.id}`}>{leaseData.provider.name ?? leaseData.provider.id}</Link>
              ) : (
                leaseData.provider?.name ?? leaseData.lease.provider_name ?? "-"
              )}
            </p>
            <p className="surface-card__body">Provider surface and capacity state.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Runtime</p>
            <p className="surface-card__value surface-card__value--compact">
              {leaseData.runtime?.runtime_session_id ? (
                <Link to={`/runtimes/${leaseData.runtime.runtime_session_id}`}>{leaseData.runtime.runtime_session_id}</Link>
              ) : (
                "-"
              )}
            </p>
            <p className="surface-card__body">Live sandbox/runtime session for this lease.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Thread</p>
            <p className="surface-card__value surface-card__value--compact">
              {threads[0]?.thread_id ? <Link to={`/threads/${threads[0].thread_id}`}>{threads[0].thread_id}</Link> : "No related thread"}
            </p>
            <p className="surface-card__body">Primary thread currently linked to this lease.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Session</p>
            <p className="surface-card__value surface-card__value--compact">{latestSession?.chat_session_id ?? "No recorded session"}</p>
            <p className="surface-card__body">Most recent chat session observed for this lease.</p>
          </article>
        </div>
        <h3>Context</h3>
        <div className="info-grid">
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
            <strong>Session status</strong>
            <span>{latestSession?.status ?? "-"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
