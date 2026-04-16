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
  } | null;
  sandbox_id?: string | null;
  result_truth?: {
    sandbox_state_before?: string | null;
    sandbox_state_after?: string | null;
    runtime_state_after?: string | null;
  } | null;
  events?: Array<{
    at?: string | null;
    status?: string | null;
    message?: string | null;
  }> | null;
};

const OPERATION_STATUS_CLASS_BY_STATUS: Record<string, string> = {
  pending: "cleanup-status cleanup-status--warning",
  running: "cleanup-status cleanup-status--warning",
  succeeded: "cleanup-status cleanup-status--ok",
  failed: "cleanup-status cleanup-status--danger",
  rejected: "cleanup-status cleanup-status--danger",
};

export function buildOperationDetailShell(data: OperationDetailPayload) {
  const sandboxId = data.sandbox_id ?? null;
  return {
    surfaceHref: "/sandboxes",
    targetLabel: "Sandbox",
    targetHref: sandboxId ? `/sandboxes/${sandboxId}` : null,
    beforeLabel: "Sandbox Before",
    afterLabel: "Sandbox After",
    runtimeBody: "Runtime session linked to the target sandbox.",
    providerBody: "Provider surface responsible for the target sandbox runtime.",
  };
}

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
  const shell = buildOperationDetailShell(data);
  const description = operation.reason ?? operation.summary ?? "Monitor operation state";
  const operationStatus = operation.status ?? "idle";
  const operationStatusClass = OPERATION_STATUS_CLASS_BY_STATUS[operationStatus] ?? "cleanup-status cleanup-status--muted";
  const latestEventMessage = events[events.length - 1]?.message ?? null;
  const operationSummary =
    operation.summary && operation.summary !== latestEventMessage ? operation.summary : "Status is tracked in the timeline below.";

  return (
    <div className="page">
      <h1>{`Operation ${operation.operation_id ?? operationId}`}</h1>
      <p className="description">{description}</p>
      <section className="surface-section">
        <h2>Operation State</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Kind</p>
            <p className="surface-card__value surface-card__value--compact">{operation.kind ?? "-"}</p>
            <p className="surface-card__body">Managed cleanup action currently being tracked.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Status</p>
            <div className="cleanup-current-op">
              <span className={operationStatusClass}>{operationStatus}</span>
            </div>
            <p className="surface-card__body">{operationSummary}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Surface</p>
            <p className="surface-card__value surface-card__value--compact">
              <Link to={shell.surfaceHref}>Sandboxes</Link>
            </p>
            <p className="surface-card__body">Sandbox workbench currently owning this action.</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Target</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">{shell.targetLabel}</p>
            <p className="surface-card__value surface-card__value--compact">
              {shell.targetHref && data.sandbox_id ? (
                <Link to={shell.targetHref}>{data.sandbox_id}</Link>
              ) : (
                "-"
              )}
            </p>
            <p className="surface-card__body">Primary sandbox read surface touched by this action.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Runtime</p>
            <p className="surface-card__value surface-card__value--compact">
              {target.runtime_session_id ? (
                <Link to={`/runtimes/${target.runtime_session_id}`}>{target.runtime_session_id}</Link>
              ) : (
                "-"
              )}
            </p>
            <p className="surface-card__body">{shell.runtimeBody}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Provider</p>
            <p className="surface-card__value surface-card__value--compact">
              {target.provider_id ? <Link to={`/providers/${target.provider_id}`}>{target.provider_id}</Link> : "-"}
            </p>
            <p className="surface-card__body">{shell.providerBody}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Result State</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">{shell.beforeLabel}</p>
            <p className="surface-card__value surface-card__value--compact">{result.sandbox_state_before ?? "-"}</p>
            <p className="surface-card__body">Observed sandbox state when the operation started.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">{shell.afterLabel}</p>
            <p className="surface-card__value surface-card__value--compact">{result.sandbox_state_after ?? "-"}</p>
            <p className="surface-card__body">Most recent post-operation sandbox state.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Runtime After</p>
            <p className="surface-card__value surface-card__value--compact">{result.runtime_state_after ?? "-"}</p>
            <p className="surface-card__body">{operation.reason ?? "No operation reason recorded."}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Event Timeline</h2>
        {events.length > 0 ? (
          <div className="cleanup-ledger__list">
            {events.map((event, index) => {
              const eventStatus = event.status ?? "unknown";
              const eventStatusClass =
                OPERATION_STATUS_CLASS_BY_STATUS[eventStatus] ?? "cleanup-status cleanup-status--muted";
              return (
                <article className="cleanup-ledger__item" key={`${event.at ?? "missing-at"}-${index}`}>
                  <div className="cleanup-ledger__header">
                    <span className={eventStatusClass}>{eventStatus}</span>
                    <span className="mono">{event.at ?? "-"}</span>
                  </div>
                  <p className="cleanup-ledger__summary">{event.message ?? "-"}</p>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="cleanup-ledger__empty">No recorded events.</p>
        )}
      </section>
    </div>
  );
}
