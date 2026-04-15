import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { postMonitorData, useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";
import StateBadge from "../components/StateBadge";

export type SandboxDetailPayload = {
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
  }> | null;
};

export function buildSandboxDetailShell(data: SandboxDetailPayload) {
  return {
    title: `Sandbox ${data.sandbox.sandbox_id}`,
    description: data.triage?.description ?? "Sandbox state and current read-only relations.",
    surfaceHref: "/sandboxes",
    cleanupIncluded: true,
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
  const cleanupAllowed = Boolean(data.triage?.category && data.triage.category !== "healthy_capacity");

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
        <h2>Cleanup</h2>
        <div className="surface-grid cleanup-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Action Lane</p>
            <button
              type="button"
              className="monitor-action-button"
              disabled={!cleanupAllowed || cleanupPending}
              onClick={() => void startCleanup()}
            >
              Start sandbox cleanup
            </button>
            <p className="surface-card__body">
              {cleanupAllowed ? "This sandbox can enter the managed cleanup flow." : "This sandbox is not ready for managed cleanup."}
            </p>
          </article>
        </div>
        {cleanupMessage ? <p className="description">{cleanupMessage}</p> : null}
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
            <p className="surface-card__body">Live runtime session linked to this sandbox.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Thread</p>
            <p className="surface-card__value surface-card__value--compact">
              {threads[0]?.thread_id ? <Link to={`/threads/${threads[0].thread_id}`}>{threads[0].thread_id}</Link> : "No related thread"}
            </p>
            <p className="surface-card__body">Primary thread currently linked to this sandbox.</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Session</p>
            <p className="surface-card__value surface-card__value--compact">{latestSession?.chat_session_id ?? "No recorded session"}</p>
            <p className="surface-card__body">Most recent chat session observed for this sandbox.</p>
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
            <strong>Session status</strong>
            <span>{latestSession?.status ?? "-"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
