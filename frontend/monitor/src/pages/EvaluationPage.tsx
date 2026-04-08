import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

type EvaluationPayload = {
  status?: string | null;
  kind?: string | null;
  headline?: string | null;
  summary?: string | null;
  facts?: Array<{ label?: string | null; value?: string | null }>;
  artifacts?: Array<{ label?: string | null; path?: string | null; status?: string | null }>;
  artifact_summary?: {
    present?: number | null;
    missing?: number | null;
    total?: number | null;
  } | null;
  next_steps?: string[] | null;
  raw_notes?: string | null;
};

export default function EvaluationPage() {
  const { data, error } = useMonitorData<EvaluationPayload>("/evaluation");

  if (error) return <ErrorState title="Evaluation" error={error} />;
  if (!data) return <div>Loading...</div>;

  const facts = data.facts ?? [];
  const artifacts = data.artifacts ?? [];
  const summary = data.artifact_summary ?? {};
  const nextSteps = data.next_steps ?? [];
  const hasArtifactSignal = artifacts.length > 0 || (summary.total ?? 0) > 0;

  return (
    <div className="page">
      <h1>Evaluation</h1>
      <p className="description">{data.headline ?? "No evaluation operator headline."}</p>
      <section className="surface-section">
        <h2>Operator Truth</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Status</p>
            <p className="surface-card__value">{data.status ?? "-"}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Kind</p>
            <p className="surface-card__value">{data.kind ?? "-"}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Current Summary</h2>
        <p className="surface-card__body">{data.summary ?? "No evaluation summary available."}</p>
      </section>
      {hasArtifactSignal ? (
        <section className="surface-section">
          <h2>Artifact Coverage</h2>
          <div className="surface-grid">
            <article className="surface-card">
              <p className="surface-card__eyebrow">Present</p>
              <p className="surface-card__value">{summary.present ?? 0}</p>
            </article>
            <article className="surface-card">
              <p className="surface-card__eyebrow">Missing</p>
              <p className="surface-card__value">{summary.missing ?? 0}</p>
            </article>
            <article className="surface-card">
              <p className="surface-card__eyebrow">Total</p>
              <p className="surface-card__value">{summary.total ?? 0}</p>
            </article>
          </div>
        </section>
      ) : null}
      <section className="surface-section">
        <h2>Operator Facts</h2>
        <div className="info-grid">
          {facts.map((fact) => (
            <div key={`${fact.label}-${fact.value}`}>
              <strong>{fact.label ?? "-"}</strong>
              <span>{fact.value ?? "-"}</span>
            </div>
          ))}
        </div>
      </section>
      {hasArtifactSignal ? (
        <section className="surface-section">
          <h2>Artifacts</h2>
          <table>
            <thead>
              <tr>
                <th>Label</th>
                <th>Path</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.length > 0 ? (
                artifacts.map((artifact) => (
                  <tr key={`${artifact.label}-${artifact.path}`}>
                    <td>{artifact.label ?? "-"}</td>
                    <td className="mono">{artifact.path ?? "-"}</td>
                    <td>{artifact.status ?? "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>No artifacts reported.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      ) : null}
      <section className="surface-section">
        <h2>Next Steps</h2>
        <ol className="surface-list">
          {nextSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
      {data.raw_notes ? (
        <section className="surface-section">
          <h2>Raw Notes</h2>
          <pre className="json-payload">{data.raw_notes}</pre>
        </section>
      ) : null}
    </div>
  );
}
