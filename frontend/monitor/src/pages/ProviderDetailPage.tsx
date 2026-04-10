import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type ProviderDetailPayload = {
  provider: {
    id?: string | null;
    name?: string | null;
    description?: string | null;
    type?: string | null;
    status?: string | null;
    consoleUrl?: string | null;
  };
  lease_ids?: string[] | null;
  thread_ids?: string[] | null;
  runtime_session_ids?: string[] | null;
};

export default function ProviderDetailPage() {
  const params = useParams<{ providerId: string }>();
  const providerId = params.providerId ?? "";
  const { data, error } = useMonitorData<ProviderDetailPayload>(`/providers/${providerId}`);

  if (error) return <ErrorState title={`Provider ${providerId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const provider = data.provider ?? {};
  const leases = data.lease_ids ?? [];
  const runtimes = data.runtime_session_ids ?? [];
  const threads = data.thread_ids ?? [];

  return (
    <div className="page">
      <h1>{`Provider ${provider.name ?? provider.id ?? providerId}`}</h1>
      <p className="description">{provider.description ?? "Provider operator truth"}</p>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Type</strong>
            <span>{provider.type ?? "-"}</span>
          </div>
          <div>
            <strong>Status</strong>
            <span>{provider.status ?? "-"}</span>
          </div>
          <div>
            <strong>Resources</strong>
            <span>
              <Link to="/resources">Back to resources</Link>
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
      <section className="surface-section">
        <h2>Leases</h2>
        {leases.length > 0 ? (
          <div className="info-grid">
            {leases.map((leaseId) => (
              <Link key={leaseId} className="mono" to={`/leases/${leaseId}`}>
                {leaseId}
              </Link>
            ))}
          </div>
        ) : (
          <p>No related leases.</p>
        )}
      </section>
      <section className="surface-section">
        <h2>Runtimes</h2>
        {runtimes.length > 0 ? (
          <div className="info-grid">
            {runtimes.map((runtimeSessionId) => (
              <Link key={runtimeSessionId} className="mono" to={`/runtimes/${runtimeSessionId}`}>
                {runtimeSessionId}
              </Link>
            ))}
          </div>
        ) : (
          <p>No related runtimes.</p>
        )}
      </section>
      <section className="surface-section">
        <h2>Threads</h2>
        {threads.length > 0 ? (
          <div className="info-grid">
            {threads.map((threadId) => (
              <Link key={threadId} className="mono" to={`/threads/${threadId}`}>
                {threadId}
              </Link>
            ))}
          </div>
        ) : (
          <p>No related threads.</p>
        )}
      </section>
    </div>
  );
}
