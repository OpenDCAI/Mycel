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

function RelatedIdSection({ title, ids, href }: { title: string; ids: string[]; href: (id: string) => string }) {
  return (
    <section className="surface-section">
      <h2>{title}</h2>
      {ids.length > 0 ? (
        <div className="info-grid">
          {ids.map((id) => (
            <Link key={id} className="mono" to={href(id)}>
              {id}
            </Link>
          ))}
        </div>
      ) : (
        <p>No related {title.toLowerCase()}.</p>
      )}
    </section>
  );
}

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
      <p className="description">{provider.description ?? "Provider state, related leases, runtimes, and threads."}</p>
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
      <RelatedIdSection title="Leases" ids={leases} href={(id) => `/leases/${id}`} />
      <RelatedIdSection title="Runtimes" ids={runtimes} href={(id) => `/runtimes/${id}`} />
      <RelatedIdSection title="Threads" ids={threads} href={(id) => `/threads/${id}`} />
    </div>
  );
}
