import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type EvaluationRunDetailPayload = {
  run?: {
    run_id?: string | null;
    thread_id?: string | null;
    status?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    user_message?: string | null;
  } | null;
  facts?: Array<{ label?: string | null; value?: string | null }> | null;
  batch_run?: {
    batch_run_id?: string | null;
    batch_id?: string | null;
    scenario_id?: string | null;
  } | null;
  limitations?: string[] | null;
};

export default function EvaluationRunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId ?? "";
  const { data, error } = useMonitorData<EvaluationRunDetailPayload>(`/evaluation/runs/${runId}`);

  if (error) return <ErrorState title={`Evaluation run ${runId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const run = data.run ?? {};
  const facts = data.facts ?? [];
  const batchRun = data.batch_run ?? {};
  const limitations = data.limitations ?? [];

  return (
    <div className="page">
      <h1>{`Evaluation Run ${run.run_id ?? runId}`}</h1>
      <p className="description">Persisted evaluation run state and thread linkage.</p>
      <section className="surface-section">
        <h2>Run State</h2>
        <div className="info-grid">
          <div>
            <strong>Thread</strong>
            {run.thread_id ? <Link to={`/threads/${run.thread_id}`}>{run.thread_id}</Link> : <span>-</span>}
          </div>
          <div>
            <strong>Status</strong>
            <span>{run.status ?? "-"}</span>
          </div>
          <div>
            <strong>Started At</strong>
            <span>{run.started_at ?? "-"}</span>
          </div>
          <div>
            <strong>Finished At</strong>
            <span>{run.finished_at ?? "-"}</span>
          </div>
          <div>
            <strong>User Message</strong>
            <span>{run.user_message ?? "-"}</span>
          </div>
          <div>
            <strong>Batch</strong>
            {batchRun.batch_id ? <Link to={`/evaluation/batches/${batchRun.batch_id}`}>{batchRun.batch_id}</Link> : <span>-</span>}
          </div>
          <div>
            <strong>Scenario</strong>
            <span>{batchRun.scenario_id ?? "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <Link to="/evaluation">Evaluation</Link>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <h2>Run Facts</h2>
        <div className="info-grid">
          {facts.map((fact) => (
            <div key={`${fact.label}-${fact.value}`}>
              <strong>{fact.label ?? "-"}</strong>
              <span>{fact.value ?? "-"}</span>
            </div>
          ))}
        </div>
      </section>
      {limitations.length > 0 ? (
        <section className="surface-section">
          <h2>Notes</h2>
          <ul className="surface-list">
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
