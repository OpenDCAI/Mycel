import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

type EvaluationPayload = {
  status?: string | null;
  kind?: string | null;
  headline?: string | null;
  summary?: string | null;
};

export default function EvaluationPage() {
  const { data, error } = useMonitorData<EvaluationPayload>("/evaluation");

  if (error) return <ErrorState title="Evaluation" error={error} />;
  if (!data) return <div>Loading...</div>;

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
    </div>
  );
}
