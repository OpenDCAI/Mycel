import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { postMonitorData, useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";

export type SandboxDetailPayload = {
  source: string;
  sandbox: {
    sandbox_id: string;
    provider_name?: string | null;
    desired_state?: string | null;
    observed_state?: string | null;
    updated_at?: string | null;
    last_error?: string | null;
    current_instance_id?: string | null;
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
    started_at?: string | null;
    ended_at?: string | null;
    close_reason?: string | null;
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

const CLEANUP_STATUS_CLASS_BY_STATUS: Record<string, string> = {
  pending: "cleanup-status cleanup-status--warning",
  running: "cleanup-status cleanup-status--warning",
  succeeded: "cleanup-status cleanup-status--ok",
  failed: "cleanup-status cleanup-status--danger",
  rejected: "cleanup-status cleanup-status--danger",
};

export function buildSandboxDetailShell(data: SandboxDetailPayload) {
  return {
    title: `Sandbox ${data.sandbox.sandbox_id}`,
    sourceLabel: `Source: ${data.source}`,
    description: data.triage?.description ?? "Sandbox state and current read-only relations.",
    surfaceHref: "/sandboxes",
    cleanupIncluded: true,
    cleanupTitle: "Cleanup",
    cleanupHint: "Canonical sandbox cleanup lane for current operation and recent cleanup history.",
    cleanupButtonLabel: "Start sandbox cleanup",
    cleanupLedgerTitle: "Recent Operations",
    threadActivityTitle: "Thread Activity",
    noThreadActivityLabel: "No recorded thread activity",
    threadActivityBody: "Most recent thread activity observed for this sandbox.",
    threadActivityStatusLabel: "Thread activity status",
  };
}

export default function SandboxDetailPage() {
  const params = useParams<{ sandboxId: string }>();
  const navigate = useNavigate();
  const sandboxId = params.sandboxId ?? "";
  const { data, error } = useMonitorData<SandboxDetailPayload>(`/sandboxes/${sandboxId}`);
  const [cleanupPending, setCleanupPending] = React.useState(false);
  const [cleanupMessage, setCleanupMessage] = React.useState<string | null>(null);

  if (error) return <ErrorState title={`Sandbox ${sandboxId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const shell = buildSandboxDetailShell(data);
  const threads = data.threads ?? [];
  const sessions = data.sessions ?? [];
  const latestSession = sessions[0] ?? null;
  const cleanup = data.cleanup ?? {};
  const cleanupAllowed = Boolean(cleanup.allowed);
  const recentOperations = (cleanup.recent_operations ?? []).filter(
    (operation) => operation.operation_id !== cleanup.operation?.operation_id,
  );
  const cleanupDecision = cleanup.allowed ? "Managed cleanup ready" : "Cleanup blocked";
  const cleanupActionSummary = cleanup.recommended_action ?? "No managed action";
  const cleanupActionHint = cleanup.allowed
    ? "This sandbox can enter the managed cleanup flow."
    : "This sandbox is not ready for managed cleanup.";
  const cleanupOperationStatus = cleanup.operation?.status ?? "idle";
  const cleanupOperationSummary = cleanup.operation?.summary ?? "No active cleanup operation.";
  const cleanupOperationClass = CLEANUP_STATUS_CLASS_BY_STATUS[cleanupOperationStatus] ?? "cleanup-status cleanup-status--muted";

  async function startCleanup() {
    setCleanupPending(true);
    try {
      const result = await postMonitorData<{ accepted?: boolean; message?: string | null; operation?: { operation_id?: string | null } | null }>(
        `/sandboxes/${sandboxId}/cleanup`,
      );
      setCleanupMessage(result.message ?? null);
      if (result.operation?.operation_id) {
        navigate(`/operations/${result.operation.operation_id}`);
      }
    } finally {
      setCleanupPending(false);
    }
  }

  return (
    <div className="page">
      <h1>{shell.title}</h1>
      <p className="description">{shell.description}</p>
      <p className="count">{shell.sourceLabel}</p>
      <section className="surface-section">
        <h2>State</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">State</p>
            <StateBadge badge={data.sandbox.badge ?? { text: data.sandbox.observed_state ?? "-" }} />
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Triage</p>
            <p className="surface-card__value">{data.triage?.title ?? "-"}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>{shell.cleanupTitle}</h2>
        <p className="description">{cleanup.reason ?? shell.cleanupHint}</p>
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
              disabled={!cleanupAllowed || cleanupPending}
              onClick={() => void startCleanup()}
            >
              {shell.cleanupButtonLabel}
            </button>
            <p className="surface-card__body">{cleanupActionHint}</p>
          </article>
        </div>
        {cleanupMessage ? <p className="description">{cleanupMessage}</p> : null}
        <div className="cleanup-ledger">
          <h3>{shell.cleanupLedgerTitle}</h3>
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
              {data.provider?.id ? (
                <Link to={`/providers/${data.provider.id}`}>{data.provider.name ?? data.provider.id}</Link>
              ) : (
                data.provider?.name ?? data.sandbox.provider_name ?? "-"
              )}
            </p>
            <p className="surface-card__body">Provider surface and capacity state.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Runtime</p>
            <p className="surface-card__value surface-card__value--compact">
              {data.runtime?.runtime_session_id ? (
                <Link to={`/runtimes/${data.runtime.runtime_session_id}`}>{data.runtime.runtime_session_id}</Link>
              ) : (
                "-"
              )}
            </p>
            <p className="surface-card__body">Live runtime linked to this sandbox.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Thread</p>
            <p className="surface-card__value surface-card__value--compact">
              {threads[0]?.thread_id ? <Link to={`/threads/${threads[0].thread_id}`}>{threads[0].thread_id}</Link> : "No related thread"}
            </p>
            <p className="surface-card__body">Primary thread currently linked to this sandbox.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">{shell.threadActivityTitle}</p>
            <p className="surface-card__value surface-card__value--compact">
              {latestSession?.chat_session_id ?? shell.noThreadActivityLabel}
            </p>
            <p className="surface-card__body">{shell.threadActivityBody}</p>
          </article>
        </div>
        <h3>Context</h3>
        <div className="info-grid">
          <div>
            <strong>Updated</strong>
            <span>{data.sandbox.updated_at ?? "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <span>
              <Link to={shell.surfaceHref}>Sandboxes</Link>
            </span>
          </div>
          <div>
            <strong>Last error</strong>
            <span>{data.sandbox.last_error ?? "-"}</span>
          </div>
          <div>
            <strong>{shell.threadActivityStatusLabel}</strong>
            <span>{latestSession?.status ?? "-"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
