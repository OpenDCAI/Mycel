import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type RuntimeDetailPayload = {
  provider?: {
    id?: string | null;
    name?: string | null;
    status?: string | null;
    consoleUrl?: string | null;
  } | null;
  runtime?: {
    runtimeSessionId?: string | null;
    status?: string | null;
    threadId?: string | null;
    leaseId?: string | null;
    agentName?: string | null;
    webUrl?: string | null;
  } | null;
  sandbox_id?: string | null;
  lease_id?: string | null;
  thread_id?: string | null;
};

export function buildRuntimeRelationShell(data: RuntimeDetailPayload) {
  const sandboxId = data.sandbox_id ?? null;
  return {
    sandboxLabel: "Sandbox",
    sandboxHref: sandboxId ? `/sandboxes/${sandboxId}` : null,
  };
}

export default function RuntimeDetailPage() {
  const params = useParams<{ runtimeSessionId: string }>();
  const runtimeSessionId = params.runtimeSessionId ?? "";
  const { data, error } = useMonitorData<RuntimeDetailPayload>(`/runtimes/${runtimeSessionId}`);

  if (error) return <ErrorState title={`Runtime ${runtimeSessionId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const provider = data.provider ?? {};
  const runtime = data.runtime ?? {};
  const relationShell = buildRuntimeRelationShell(data);
  const threadId = data.thread_id ?? runtime.threadId ?? null;

  return (
    <div className="page">
      <h1>{`Runtime ${runtime.runtimeSessionId ?? runtimeSessionId}`}</h1>
      <p className="description">
        {runtime.agentName ?? "Sandbox runtime"} · {runtime.status ?? "-"}
      </p>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Provider</strong>
            <span>
              {provider.id ? <Link to={`/providers/${provider.id}`}>{provider.name ?? provider.id}</Link> : "-"}
            </span>
          </div>
          <div>
            <strong>{relationShell.sandboxLabel}</strong>
            <span>{relationShell.sandboxHref && data.sandbox_id ? <Link to={relationShell.sandboxHref}>{data.sandbox_id}</Link> : "-"}</span>
          </div>
          <div>
            <strong>Thread</strong>
            <span>{threadId ? <Link to={`/threads/${threadId}`}>{threadId}</Link> : "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <span>
              <Link to="/resources">Resources</Link>
            </span>
          </div>
          <div>
            <strong>Web</strong>
            <span>
              {runtime.webUrl ? (
                <a href={runtime.webUrl} target="_blank" rel="noreferrer">
                  Open runtime URL
                </a>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Console</strong>
            <span>
              {provider.consoleUrl ? (
                <a href={provider.consoleUrl} target="_blank" rel="noreferrer">
                  Open provider console
                </a>
              ) : (
                "-"
              )}
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
