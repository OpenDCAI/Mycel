import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

type EvaluationPayload = {
  status?: string | null;
  kind?: string | null;
  headline?: string | null;
  summary?: string | null;
  source?: {
    kind?: string | null;
    label?: string | null;
  } | null;
  subject?: {
    thread_id?: string | null;
    run_id?: string | null;
    user_message?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
  } | null;
  facts?: Array<{ label?: string | null; value?: string | null }>;
  artifacts?: Array<{ label?: string | null; path?: string | null; status?: string | null }>;
  artifact_summary?: {
    present?: number | null;
    missing?: number | null;
    total?: number | null;
  } | null;
  limitations?: string[] | null;
  raw_notes?: string | null;
};

export default function EvaluationPage() {
  const { data, error } = useMonitorData<EvaluationPayload>("/evaluation");

  if (error) return <ErrorState title="Evaluation" error={error} />;
  if (!data) return <div>Loading...</div>;

  const source = data.source ?? {};
  const subject = data.subject ?? {};
  const facts = data.facts ?? [];
  const artifacts = data.artifacts ?? [];
  const summary = data.artifact_summary ?? {};
  const limitations = data.limitations ?? [];
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
          <article className="surface-card">
            <p className="surface-card__eyebrow">Source</p>
            <p className="surface-card__value">{source.label ?? "-"}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <h2>Run Subject</h2>
        <div className="info-grid">
          <div>
            <strong>Thread</strong>
            {subject.thread_id ? <Link to={`/threads/${subject.thread_id}`}>{subject.thread_id}</Link> : <span>-</span>}
          </div>
          <div>
            <strong>Run ID</strong>
            <span className="mono">{subject.run_id ?? "-"}</span>
          </div>
          <div>
            <strong>Started At</strong>
            <span>{subject.started_at ?? "-"}</span>
          </div>
          <div>
            <strong>Finished At</strong>
            <span>{subject.finished_at ?? "-"}</span>
          </div>
          <div>
            <strong>User Message</strong>
            <span>{subject.user_message ?? "-"}</span>
          </div>
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
      {limitations.length > 0 ? (
        <section className="surface-section">
          <h2>Truth Boundary</h2>
          <ul className="surface-list">
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {data.raw_notes ? (
        <section className="surface-section">
          <h2>Raw Notes</h2>
          <pre className="json-payload">{data.raw_notes}</pre>
        </section>
      ) : null}
    </div>
  );
}
